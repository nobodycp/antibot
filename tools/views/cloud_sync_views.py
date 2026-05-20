import threading

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import superuser_required
from core.htmx_navigation import render_page_or_shell

from dashboard.models import CloudflareSyncRun, UserCloudflareDomain

from ..services.cloudflare_sync_service import sync_all_domains, sync_domain
from .cloudflare_domains_views import _flash_sync_result

_CLOUD_SYNC = "tools:cloud_sync"


def _run_sync_in_background(run_id: int) -> None:
    run = CloudflareSyncRun.objects.get(pk=run_id)
    lines: list[str] = []
    ok_count = 0
    fail_count = 0

    try:
        results = sync_all_domains()
        for r in results:
            tag = "SKIP" if r.skipped else ("OK" if r.ok else "FAIL")
            line = f"[{tag}] {r.domain_name}: {r.message}"
            lines.append(line)
            if r.ok:
                ok_count += 1
            else:
                fail_count += 1
    except Exception as exc:
        logger_msg = f"Sync aborted: {exc}"
        lines.append(logger_msg)
        run.status = CloudflareSyncRun.STATUS_FAILED
        run.domains_ok = ok_count
        run.domains_failed = fail_count
        run.log_text = "\n".join(lines)
        run.finished_at = timezone.now()
        run.save()
        return

    if fail_count == 0:
        status = CloudflareSyncRun.STATUS_SUCCESS
    elif ok_count == 0:
        status = CloudflareSyncRun.STATUS_FAILED
    else:
        status = CloudflareSyncRun.STATUS_PARTIAL

    run.status = status
    run.domains_ok = ok_count
    run.domains_failed = fail_count
    run.log_text = "\n".join(lines)
    run.finished_at = timezone.now()
    run.save()


@superuser_required
def cloud_sync_view(request):
    active_domain_rows = list(
        UserCloudflareDomain.objects.filter(is_active=True)
        .select_related("user")
        .order_by("user__username", "domain_name")
    )
    active_domains = len(active_domain_rows)
    total_domains = UserCloudflareDomain.objects.count()
    latest_run = CloudflareSyncRun.objects.first()
    recent_runs = CloudflareSyncRun.objects.all()[:10]

    ctx = {
        "active_domains": active_domains,
        "active_domain_rows": active_domain_rows,
        "total_domains": total_domains,
        "latest_run": latest_run,
        "recent_runs": recent_runs,
    }
    return render_page_or_shell(
        request,
        full_template="tools/cloud_sync.html",
        shell_template="tools/partials/shell/cloud_sync.html",
        context=ctx,
    )


@superuser_required
@require_POST
def cloud_sync_start(request):
    running = CloudflareSyncRun.objects.filter(
        status=CloudflareSyncRun.STATUS_RUNNING
    ).exists()
    if running:
        messages.warning(request, "A sync is already running.")
        return redirect(_CLOUD_SYNC)

    run = CloudflareSyncRun.objects.create(
        triggered_by=request.user,
        status=CloudflareSyncRun.STATUS_RUNNING,
        log_text="Sync started…\n",
    )
    thread = threading.Thread(
        target=_run_sync_in_background,
        args=(run.pk,),
        daemon=True,
    )
    thread.start()
    messages.success(request, "Cloudflare sync started for all active domains.")
    return redirect(_CLOUD_SYNC)


@superuser_required
@require_POST
def cloud_sync_domain_sync(request, domain_id: int):
    domain = get_object_or_404(UserCloudflareDomain, pk=domain_id)
    result = sync_domain(domain, include_subnet=False)
    _flash_sync_result(request, result)
    return redirect(_CLOUD_SYNC)


@superuser_required
def cloud_sync_status_partial(request):
    latest_run = CloudflareSyncRun.objects.first()
    html = render_to_string(
        "tools/partials/cloud_sync_status.html",
        {"latest_run": latest_run},
        request=request,
    )
    return HttpResponse(html)
