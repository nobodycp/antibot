from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.decorators import superuser_required
from core.htmx_navigation import is_htmx_get, render_page_or_shell

from ..forms import WhatsAppCheckForm
from ..models import WhatsAppCheckJob
from ..services import whatsapp_service as wa

def _wa_url(**query) -> str:
    base = reverse("tools:whatsapp_check")
    if not query:
        return base
    parts = "&".join(f"{k}={v}" for k, v in query.items())
    return f"{base}?{parts}"


def _linked_account_names() -> list[str]:
    return [a.name for a in wa.list_accounts() if a.has_session]


def _parse_status_interval(request) -> int:
    raw = request.GET.get("seconds") or request.GET.get("interval") or "30"
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 30
    return max(5, min(300, value))


def _accounts_table_rows(*, max_age_seconds: int = 30, probe: bool = True) -> list[dict]:
    accounts = wa.list_accounts()
    names = [a.name for a in accounts]
    if probe and names:
        wa.refresh_accounts_connection_status(names, max_age_seconds=max_age_seconds)
    return [
        {
            "account": account,
            "status": wa.get_account_status(
                account.name, max_age_seconds=max_age_seconds, probe_if_stale=False
            ),
        }
        for account in accounts
    ]


def _build_check_form(data=None) -> WhatsAppCheckForm:
    linked = _linked_account_names()
    return WhatsAppCheckForm(data, account_choices=linked)


@superuser_required
def whatsapp_check_view(request):
    tab = request.GET.get("tab", "check")
    if tab not in ("check", "accounts"):
        tab = "check"

    pairing_account = (request.GET.get("pairing") or "").strip()
    if pairing_account:
        try:
            pairing_account = wa.validate_account_name(pairing_account)
        except ValueError:
            pairing_account = ""
    accounts = wa.list_accounts()
    jobs_qs = WhatsAppCheckJob.objects.filter(user=request.user)
    jobs = list(jobs_qs[:20])

    for job in jobs:
        if job.status in (
            WhatsAppCheckJob.STATUS_RUNNING,
            WhatsAppCheckJob.STATUS_PENDING,
        ):
            wa.sync_job_from_disk(job)
            job.save()

    active_job = jobs_qs.filter(status=WhatsAppCheckJob.STATUS_RUNNING).first()

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "start_check":
            form = _build_check_form(request.POST)
            if not form.is_valid():
                messages.error(request, "Fix the form errors and try again.")
                return redirect(_wa_url(tab="check"))

            linked = _linked_account_names()
            if not linked:
                messages.error(request, "Link at least one WhatsApp account first.")
                return redirect(_wa_url(tab="accounts"))

            selected = form.cleaned_data.get("accounts") or linked
            selected = [a for a in selected if a in linked]
            if not selected:
                messages.error(request, "Select at least one linked account.")
                return redirect(_wa_url(tab="check"))

            numbers = wa.parse_numbers_text(form.cleaned_data["numbers"])
            if not numbers:
                messages.error(request, "Enter at least one valid phone number.")
                return redirect(_wa_url(tab="check"))

            if WhatsAppCheckJob.objects.filter(
                user=request.user,
                status=WhatsAppCheckJob.STATUS_RUNNING,
            ).exists():
                messages.warning(request, "A check is already running. Wait or cancel it.")
                return redirect(_wa_url(tab="check"))

            trunk_cc = wa.normalize_country_prefix(
                form.cleaned_data.get("country_prefix") or ""
            )

            job = WhatsAppCheckJob.objects.create(
                user=request.user,
                numbers_text=form.cleaned_data["numbers"],
                local_trunk_country=trunk_cc,
                account_names=selected,
                speed=form.cleaned_data["speed"],
                fetch_presence=form.cleaned_data["fetch_presence"],
                status=WhatsAppCheckJob.STATUS_PENDING,
            )
            job.run_dir = str(wa.job_run_dir(job.id))
            job.save(update_fields=["run_dir"])

            try:
                proc = wa.start_check_job(
                    job_id=job.id,
                    numbers=numbers,
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

            job.pid = proc.pid
            job.status = WhatsAppCheckJob.STATUS_RUNNING
            job.started_at = timezone.now()
            job.save()
            messages.success(
                request,
                f"Started check for {len(numbers)} number(s) on {len(selected)} account(s).",
            )
            return redirect(_wa_url(tab="check", job=job.id))

        if action == "cancel_job":
            job = get_object_or_404(
                WhatsAppCheckJob,
                pk=request.POST.get("job_id"),
                user=request.user,
            )
            wa.terminate_process(job.pid)
            job.status = WhatsAppCheckJob.STATUS_CANCELLED
            job.finished_at = timezone.now()
            job.pid = None
            job.save()
            messages.info(request, "Check cancelled.")
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

            try:
                proc = wa.start_pairing(name)
            except (FileNotFoundError, ValueError) as exc:
                messages.error(request, str(exc))
                return redirect(_wa_url(tab="accounts"))

            request.session[f"wa_pair_pid_{name}"] = proc.pid
            messages.success(request, f"Pairing started for {name}. Scan the QR code below.")
            return redirect(_wa_url(tab="accounts", pairing=name))

        if action == "delete_account":
            name = (request.POST.get("account_name") or "").strip()
            if WhatsAppCheckJob.objects.filter(
                user=request.user,
                status=WhatsAppCheckJob.STATUS_RUNNING,
            ).exists():
                messages.error(request, "Cannot delete accounts while a check is running.")
                return redirect(_wa_url(tab="accounts"))
            try:
                wa.delete_account(name)
                messages.success(request, f"Removed account {name}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect(_wa_url(tab="accounts"))

    if pairing_account and tab == "accounts" and request.method == "GET":
        creds_path = wa.sessions_dir() / pairing_account / "creds.json"
        pairing_status_early = wa.get_pairing_status(pairing_account)
        pair_pid = request.session.get(f"wa_pair_pid_{pairing_account}")
        if (
            not creds_path.is_file()
            and pairing_status_early.get("status") not in ("qr", "connecting")
            and not wa.is_process_running(pair_pid)
        ):
            try:
                proc = wa.start_pairing(pairing_account)
                request.session[f"wa_pair_pid_{pairing_account}"] = proc.pid
            except (FileNotFoundError, ValueError) as exc:
                messages.error(request, str(exc))

    check_form = _build_check_form()
    highlight_job = None
    job_snapshot: dict | None = None
    job_id = request.GET.get("job")
    if job_id:
        try:
            highlight_job = WhatsAppCheckJob.objects.get(pk=int(job_id), user=request.user)
            wa.sync_job_from_disk(highlight_job)
            highlight_job.save()
            job_snapshot = wa.build_job_snapshot(highlight_job)
        except (WhatsAppCheckJob.DoesNotExist, ValueError):
            highlight_job = None

    poll_job = highlight_job or active_job
    if poll_job and job_snapshot is None:
        job_snapshot = wa.build_job_snapshot(poll_job)
    if job_snapshot is None:
        job_snapshot = {
            "total_count": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "error_count": 0,
            "valid_numbers": [],
            "error_numbers": [],
        }

    pairing_status = (
        wa.get_pairing_status(pairing_account) if pairing_account else None
    )

    status_interval = _parse_status_interval(request) if tab == "accounts" else 30

    ctx = {
        "tab": tab,
        "check_form": check_form,
        "accounts": accounts,
        "account_rows": _accounts_table_rows(
            max_age_seconds=status_interval, probe=False
        ),
        "status_interval": status_interval,
        "jobs": jobs,
        "active_job": active_job,
        "highlight_job": highlight_job,
        "poll_job": poll_job,
        "job_snapshot": job_snapshot,
        "pairing_account": pairing_account,
        "pairing": pairing_status,
        "linked_accounts": _linked_account_names(),
        "node_available": (wa.whatsapp_root() / "index.js").is_file(),
    }
    return render_page_or_shell(
        request,
        full_template="tools/whatsapp_check.html",
        shell_template="tools/partials/shell/whatsapp_check.html",
        context=ctx,
    )


@superuser_required
@require_GET
def whatsapp_check_status_partial(request, job_id: int):
    job = get_object_or_404(WhatsAppCheckJob, pk=job_id, user=request.user)
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
    return HttpResponse(html)


@superuser_required
@require_GET
def whatsapp_accounts_status_partial(request):
    interval = _parse_status_interval(request)
    html = render_to_string(
        "tools/partials/whatsapp_accounts_table_body.html",
        {
            "account_rows": _accounts_table_rows(
                max_age_seconds=interval, probe=True
            ),
            "request": request,
        },
        request=request,
    )
    return HttpResponse(html)


@superuser_required
@require_GET
def whatsapp_pairing_status_partial(request, account_name: str):
    try:
        wa.validate_account_name(account_name)
    except ValueError:
        return HttpResponseForbidden("Invalid account name.")
    status = wa.get_pairing_status(account_name)
    html = render_to_string(
        "tools/partials/whatsapp_pairing_status.html",
        {"account_name": account_name, "pairing": status},
        request=request,
    )
    response = HttpResponse(html)
    if status.get("status") in ("qr", "connecting") and is_htmx_get(request):
        response["HX-Trigger"] = "waPairPoll"
    return response
