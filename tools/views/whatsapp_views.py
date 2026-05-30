import shutil
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from django.contrib.auth.decorators import login_required
from core.htmx_navigation import is_htmx_get, render_page_or_shell

from ..forms import WhatsAppCheckForm
from ..models import WhatsAppCheckJob
from ..services import whatsapp_accounts as wa_accounts
from ..services import whatsapp_service as wa

def _wa_url(**query) -> str:
    base = reverse("tools:whatsapp_check")
    if not query:
        return base
    parts = "&".join(f"{k}={v}" for k, v in query.items())
    return f"{base}?{parts}"


def _whatsapp_node_ready() -> bool:
    node_bin = settings.WHATSAPP_NODE_BIN
    if Path(node_bin).is_file():
        node_ok = True
    else:
        node_ok = shutil.which(node_bin) is not None
    return node_ok and (wa.whatsapp_root() / "node_modules").is_dir()


def _linked_account_names(user) -> list[str]:
    return wa_accounts.linked_account_names_for_user(user)


def _parse_status_interval(request) -> int:
    raw = request.GET.get("seconds") or request.GET.get("interval") or "30"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 30
    return max(30, min(300, value))


def _accounts_table_rows(
    user, *, max_age_seconds: int = 30, probe: bool = True
) -> list[dict]:
    accounts = wa_accounts.disk_accounts_for_user(user)
    names = [a.name for a in accounts]
    if probe and names:
        wa.refresh_accounts_connection_status(names, max_age_seconds=max_age_seconds)
    is_admin = wa_accounts.is_wa_admin(user)
    rows = []
    for account in accounts:
        row = {
            "account": account,
            "status": wa.get_account_status(
                account.name, max_age_seconds=max_age_seconds, probe_if_stale=False
            ),
        }
        if is_admin:
            row["owner_username"] = wa_accounts.owner_username_for(account.name)
        rows.append(row)
    return rows


def _build_check_form(user, data=None) -> WhatsAppCheckForm:
    choices = wa_accounts.account_choices_for_form(user)
    return WhatsAppCheckForm(data, account_choices=choices)


def _recent_jobs_for_user(
    user,
    *,
    sync_from_disk: bool = True,
    sync_pending_failed: bool = False,
):
    if not _jobs_schema_ready():
        return [], None
    jobs_qs = wa_accounts.jobs_queryset_for_user(user)
    jobs = list(jobs_qs[:20])
    if sync_from_disk:
        for job in jobs:
            if job.status == WhatsAppCheckJob.STATUS_RUNNING:
                wa.sync_job_from_disk(job)
                job.save()
            elif sync_pending_failed and job.status in (
                WhatsAppCheckJob.STATUS_PENDING,
                WhatsAppCheckJob.STATUS_FAILED,
            ):
                wa.sync_job_from_disk(job)
                job.save()
    # Re-query after disk sync — stale in-memory status may block the UI.
    active = jobs_qs.filter(status=WhatsAppCheckJob.STATUS_RUNNING).first()
    return jobs, active


def _get_job(user, job_id):
    return get_object_or_404(wa_accounts.jobs_queryset_for_user(user), pk=job_id)


def _user_has_running_job(user) -> bool:
    if not wa_accounts.whatsapp_job_line_counts_schema_ready():
        return False
    return WhatsAppCheckJob.objects.filter(
        user=user,
        status=WhatsAppCheckJob.STATUS_RUNNING,
    ).exists()


def _jobs_schema_ready() -> bool:
    return wa_accounts.whatsapp_job_line_counts_schema_ready()


def _warn_jobs_schema_pending(request) -> None:
    if not _jobs_schema_ready():
        messages.warning(request, wa_accounts.WA_JOBS_MIGRATE_HINT)


@login_required
def whatsapp_check_view(request):
    user = request.user
    jobs_schema_ready = _jobs_schema_ready()
    if not jobs_schema_ready:
        _warn_jobs_schema_pending(request)
    is_admin = wa_accounts.is_wa_admin(user)
    tab = request.GET.get("tab", "check")
    if tab not in ("check", "accounts"):
        tab = "check"

    pairing_account = (request.GET.get("pairing") or "").strip()
    if pairing_account:
        try:
            pairing_account = wa.validate_account_name(pairing_account)
        except ValueError:
            pairing_account = ""
        if pairing_account and not wa_accounts.user_can_access_account(
            user, pairing_account
        ):
            pairing_account = ""

    accounts = wa_accounts.disk_accounts_for_user(user)
    skip_job_disk_sync = is_htmx_get(request) and not request.GET.get("job")
    jobs, active_job = _recent_jobs_for_user(
        user,
        sync_from_disk=not skip_job_disk_sync,
    )

    if request.method == "POST":
        action = request.POST.get("action", "")

        if not jobs_schema_ready:
            messages.error(request, wa_accounts.WA_JOBS_MIGRATE_HINT)
            return redirect(_wa_url(tab=tab))

        if action == "start_check":
            form = _build_check_form(user, request.POST)
            if not form.is_valid():
                messages.error(request, "Fix the form errors and try again.")
                return redirect(_wa_url(tab="check"))

            linked = _linked_account_names(user)
            if not linked:
                messages.error(request, "Link at least one WhatsApp account first.")
                return redirect(_wa_url(tab="accounts"))

            selected = form.cleaned_data.get("accounts") or []
            if is_admin and not selected:
                selected = linked
            elif not selected:
                selected = linked
            allowed = set(linked)
            selected = [a for a in selected if a in allowed]
            if not selected:
                messages.error(request, "Select at least one linked account.")
                return redirect(_wa_url(tab="check"))

            numbers = wa.parse_numbers_text(form.cleaned_data["numbers"])
            if not numbers:
                messages.error(request, "Enter at least one valid phone number.")
                return redirect(_wa_url(tab="check"))

            trunk_cc = wa.normalize_country_prefix(
                form.cleaned_data.get("country_prefix") or ""
            )
            split = wa.split_numbers_by_verified_history(numbers, trunk_cc)
            to_check = split.to_check
            already_verified = split.already_verified

            if not to_check and not already_verified:
                messages.error(
                    request,
                    "No valid phone numbers after parsing. Check format and country prefix.",
                )
                return redirect(_wa_url(tab="check"))

            if _user_has_running_job(user):
                messages.warning(request, "A check is already running. Wait or cancel it.")
                return redirect(_wa_url(tab="check"))

            input_line_count, unique_number_count = wa.compute_job_line_counts(
                form.cleaned_data["numbers"], trunk_cc
            )
            job = WhatsAppCheckJob.objects.create(
                user=user,
                numbers_text=form.cleaned_data["numbers"],
                input_line_count=input_line_count,
                unique_number_count=unique_number_count,
                local_trunk_country=trunk_cc,
                account_names=selected,
                speed=form.cleaned_data["speed"],
                fetch_presence=form.cleaned_data["fetch_presence"],
                status=WhatsAppCheckJob.STATUS_PENDING,
                previously_checked_numbers=already_verified,
            )
            job.run_dir = str(wa.job_run_dir(job.id))
            job.save(update_fields=["run_dir"])

            if not to_check:
                job.status = WhatsAppCheckJob.STATUS_COMPLETED
                job.started_at = timezone.now()
                job.finished_at = timezone.now()
                job.save()
                messages.success(
                    request,
                    f"All {len(already_verified)} number(s) were already verified — nothing to check.",
                )
                return redirect(_wa_url(tab="check", job=job.id))

            try:
                proc = wa.start_check_job(
                    job_id=job.id,
                    numbers=to_check,
                    account_names=selected,
                    speed=job.speed,
                    fetch_presence=job.fetch_presence,
                    local_trunk_country=trunk_cc,
                )
            except (FileNotFoundError, ValueError) as exc:
                job.status = WhatsAppCheckJob.STATUS_FAILED
                job.error_message = str(exc)
                job.finished_at = timezone.now()
                job.save()
                messages.error(request, str(exc))
                return redirect(_wa_url(tab="check"))

            wa.register_job_validator_pid(job, proc)
            job.status = WhatsAppCheckJob.STATUS_RUNNING
            job.started_at = timezone.now()
            job.save()
            skipped_msg = ""
            if already_verified:
                skipped_msg = f" ({len(already_verified)} previously verified, skipped)"
            messages.success(
                request,
                f"Started check for {len(to_check)} number(s) on {len(selected)} account(s){skipped_msg}.",
            )
            return redirect(_wa_url(tab="check", job=job.id))

        if action == "cancel_job":
            job = _get_job(user, request.POST.get("job_id"))
            wa.sync_job_from_disk(job)
            pid = wa.resolve_validator_pid(job) or job.pid
            wa.terminate_process(pid)
            job.pid = None
            wa.clear_validator_pid(job.id)
            if job.status in (
                WhatsAppCheckJob.STATUS_RUNNING,
                WhatsAppCheckJob.STATUS_PENDING,
            ):
                job.status = WhatsAppCheckJob.STATUS_CANCELLED
            job.finished_at = job.finished_at or timezone.now()
            remaining = wa.remaining_numbers_for_job(job)
            if remaining:
                run_path = wa.job_run_dir(job.id)
                run_path.mkdir(parents=True, exist_ok=True)
                (run_path / "pending_numbers.txt").write_text(
                    "\n".join(remaining) + "\n", encoding="utf-8"
                )
            job.save()
            messages.info(request, "Check cancelled. You can continue it later.")
            job_id = request.POST.get("job_id")
            if job_id:
                return redirect(_wa_url(tab="check", job=job_id))
            return redirect(_wa_url(tab="check"))

        if action == "add_account":
            raw_name = (request.POST.get("account_name") or "").strip()
            try:
                name = wa.validate_account_name(raw_name) if raw_name else wa.suggest_next_account_name()
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(_wa_url(tab="accounts"))

            if any(a.name == name for a in accounts):
                messages.warning(request, f"Account “{name}” already exists.")
            else:
                (wa.sessions_dir() / name).mkdir(parents=True, exist_ok=True)
                wa_accounts.register_account(name, user)

            try:
                pair_pid = wa.start_pairing(name)
            except (FileNotFoundError, ValueError) as exc:
                messages.error(request, str(exc))
                return redirect(_wa_url(tab="accounts"))

            request.session[f"wa_pair_pid_{name}"] = pair_pid
            messages.success(request, f"Pairing started for {name}. Scan the QR code below.")
            return redirect(_wa_url(tab="accounts", pairing=name))

        if action == "delete_account":
            name = (request.POST.get("account_name") or "").strip()
            if not wa_accounts.user_can_access_account(user, name):
                messages.error(request, "You do not have permission to delete this account.")
                return redirect(_wa_url(tab="accounts"))
            if _user_has_running_job(user):
                messages.error(request, "Cannot delete accounts while a check is running.")
                return redirect(_wa_url(tab="accounts"))
            try:
                wa.delete_account(name)
                wa_accounts.unregister_account(name)
                messages.success(request, f"Removed account {name}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(_wa_url(tab="accounts"))

    if pairing_account and tab == "accounts" and request.method == "GET":
        creds_path = wa.sessions_dir() / pairing_account / "creds.json"
        pair_pid = wa.resolve_pairing_pid(
            pairing_account,
            request.session.get(f"wa_pair_pid_{pairing_account}"),
        )
        if pair_pid:
            request.session[f"wa_pair_pid_{pairing_account}"] = pair_pid
        pairing_status_early = wa.get_pairing_status(
            pairing_account, pair_pid=pair_pid
        )
        if (
            not creds_path.is_file()
            and pairing_status_early.get("status") not in ("qr", "connecting")
            and not wa.is_process_running(pair_pid)
        ):
            try:
                pair_pid = wa.start_pairing(pairing_account)
                request.session[f"wa_pair_pid_{pairing_account}"] = pair_pid
            except (FileNotFoundError, ValueError) as exc:
                messages.error(request, str(exc))

    check_form = _build_check_form(user)
    highlight_job = None
    job_snapshot: dict | None = None
    job_id = request.GET.get("job")
    if job_id:
        try:
            highlight_job = _get_job(user, int(job_id))
            wa.sync_job_from_disk(highlight_job)
            highlight_job.save()
            job_snapshot = wa.build_job_snapshot(highlight_job)
        except (WhatsAppCheckJob.DoesNotExist, ValueError):
            highlight_job = None

    poll_job = highlight_job or active_job
    continue_job = None
    if poll_job and poll_job.is_resumable:
        continue_job = poll_job
    if poll_job and job_snapshot is None:
        job_snapshot = wa.build_job_snapshot(poll_job)
    if job_snapshot is None:
        job_snapshot = {
            "total_count": 0,
            "checked_count": 0,
            "pending_count": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "error_count": 0,
            "skipped_count": 0,
            "valid_numbers": [],
            "error_numbers": [],
            "previously_checked_numbers": [],
        }

    pairing_status = None
    if pairing_account:
        pair_pid = wa.resolve_pairing_pid(
            pairing_account,
            request.session.get(f"wa_pair_pid_{pairing_account}"),
        )
        if pair_pid:
            request.session[f"wa_pair_pid_{pairing_account}"] = pair_pid
        pairing_status = wa.get_pairing_status(
            pairing_account, pair_pid=pair_pid
        )

    status_interval = _parse_status_interval(request) if tab == "accounts" else 30

    ctx = {
        "tab": tab,
        "check_form": check_form,
        "accounts": accounts,
        "account_rows": _accounts_table_rows(
            user, max_age_seconds=status_interval, probe=False
        ),
        "is_wa_admin": is_admin,
        "status_interval": status_interval,
        "jobs": jobs,
        "active_job": active_job,
        "highlight_job": highlight_job,
        "poll_job": poll_job,
        "continue_job": continue_job,
        "job_snapshot": job_snapshot,
        "pairing_account": pairing_account,
        "pairing": pairing_status,
        "linked_accounts": _linked_account_names(user),
        "node_available": _whatsapp_node_ready(),
        "wa_jobs_schema_ready": jobs_schema_ready,
    }
    return render_page_or_shell(
        request,
        full_template="tools/whatsapp_check.html",
        shell_template="tools/partials/shell/whatsapp_check.html",
        context=ctx,
    )


@login_required
@require_POST
def whatsapp_check_continue(request, job_id: int):
    if not _jobs_schema_ready():
        messages.error(request, wa_accounts.WA_JOBS_MIGRATE_HINT)
        return redirect(_wa_url(tab="check", job=job_id))
    job = _get_job(request.user, job_id)
    wa.sync_job_from_disk(job)
    job.save()

    if not job.is_resumable:
        messages.error(request, "This job cannot be continued.")
        return redirect(_wa_url(tab="check", job=job.id))

    if (
        WhatsAppCheckJob.objects.filter(
            user=request.user,
            status=WhatsAppCheckJob.STATUS_RUNNING,
        )
        .exclude(pk=job.pk)
        .exists()
    ):
        messages.warning(
            request, "A check is already running. Wait or cancel it before continuing."
        )
        return redirect(_wa_url(tab="check", job=job.id))

    remaining = wa.remaining_numbers_for_job(job)
    try:
        proc = wa.resume_check_job(job)
    except (FileNotFoundError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect(_wa_url(tab="check", job=job.id))

    wa.register_job_validator_pid(job, proc)
    job.status = WhatsAppCheckJob.STATUS_RUNNING
    job.started_at = job.started_at or timezone.now()
    job.finished_at = None
    job.error_message = ""
    job.save(
        update_fields=[
            "pid",
            "status",
            "started_at",
            "finished_at",
            "error_message",
        ]
    )
    messages.success(
        request,
        f"Continued check for {len(remaining)} remaining number(s) on job #{job.id}.",
    )
    return redirect(_wa_url(tab="check", job=job.id))


@login_required
@require_GET
def whatsapp_check_status_partial(request, job_id: int):
    if not _jobs_schema_ready():
        return HttpResponse(
            '<p class="text-sm ds-text-warning">'
            + wa_accounts.WA_JOBS_MIGRATE_HINT
            + "</p>"
        )
    job = _get_job(request.user, job_id)
    wa.sync_job_from_disk(job)
    job.save()
    snapshot = wa.build_job_snapshot(job)
    html = render_to_string(
        "tools/partials/whatsapp_check_results_wrapper.html",
        {
            "job": job,
            "snapshot": snapshot,
            "request": request,
        },
        request=request,
    )
    response = HttpResponse(html)
    if job.status != WhatsAppCheckJob.STATUS_RUNNING:
        response["HX-Trigger"] = "waRecentJobsRefresh"
    return response


@login_required
@require_GET
def whatsapp_check_recent_jobs_partial(request):
    if not _jobs_schema_ready():
        return HttpResponse("")
    jobs, active_job = _recent_jobs_for_user(
        request.user,
        sync_pending_failed=True,
    )
    html = render_to_string(
        "tools/partials/whatsapp_check_recent_jobs.html",
        {
            "jobs": jobs,
            "active_job": active_job,
            "is_wa_admin": wa_accounts.is_wa_admin(request.user),
            "request": request,
        },
        request=request,
    )
    return HttpResponse(html)


@login_required
@require_GET
def whatsapp_accounts_status_partial(request):
    interval = _parse_status_interval(request)
    html = render_to_string(
        "tools/partials/whatsapp_accounts_table_body.html",
        {
            "account_rows": _accounts_table_rows(
                request.user, max_age_seconds=interval, probe=True
            ),
            "is_wa_admin": wa_accounts.is_wa_admin(request.user),
            "request": request,
        },
        request=request,
    )
    return HttpResponse(html)


@login_required
@require_GET
def whatsapp_pairing_status_partial(request, account_name: str):
    try:
        wa.validate_account_name(account_name)
    except ValueError:
        return HttpResponseForbidden("Invalid account name.")
    if not wa_accounts.user_can_access_account(request.user, account_name):
        return HttpResponseForbidden("You do not have access to this account.")
    pair_pid = wa.resolve_pairing_pid(
        account_name,
        request.session.get(f"wa_pair_pid_{account_name}"),
    )
    if pair_pid:
        request.session[f"wa_pair_pid_{account_name}"] = pair_pid
    status = wa.get_pairing_status(account_name, pair_pid=pair_pid)
    html = render_to_string(
        "tools/partials/whatsapp_pairing_status.html",
        {
            "account_name": account_name,
            "pairing": status,
            "node_available": _whatsapp_node_ready(),
        },
        request=request,
    )
    response = HttpResponse(html)
    if status.get("status") in ("qr", "connecting", "idle") and is_htmx_get(request):
        response["HX-Trigger"] = "waPairPoll"
    return response
