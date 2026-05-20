from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.htmx_navigation import render_page_or_shell

from dashboard.cloudflare_token_crypto import decrypt_cloudflare_token, encrypt_cloudflare_token
from dashboard.forms import CloudflareDomainForm, apply_cloudflare_domain_form
from dashboard.helpers.cloudflare_zone import verify_cloudflare_zone
from dashboard.models import UserCloudflareDomain
from tools.services.cloudflare_sync_service import DomainSyncResult, sync_domain

_CF_DOMAINS = "tools:cloudflare_domains"


def _cf_zone_defaults() -> UserCloudflareDomain:
    return UserCloudflareDomain()


def _flash_sync_result(request, result: DomainSyncResult) -> None:
    label = result.domain_name
    if result.ok:
        if result.status == UserCloudflareDomain.SYNC_ERROR:
            messages.error(request, f"{label}: {result.message}")
        elif result.status == UserCloudflareDomain.SYNC_WARNING:
            messages.warning(request, f"{label}: {result.message}")
        elif result.skipped:
            messages.info(request, f"{label}: {result.message}")
        else:
            messages.success(request, f"{label}: {result.message}")
    else:
        messages.error(request, f"{label}: {result.message}")


@login_required
def cloudflare_domains_view(request):
    domains = UserCloudflareDomain.objects.filter(user=request.user).order_by(
        "domain_name"
    )
    return render_page_or_shell(
        request,
        full_template="tools/cloudflare_domains.html",
        shell_template="tools/partials/shell/cloudflare_domains.html",
        context={
            "domains": domains,
            "cf_zone_defaults": _cf_zone_defaults(),
        },
    )


@login_required
@require_POST
def cloudflare_domain_add(request):
    form = CloudflareDomainForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Domain name, zone ID, and API token are required.")
        return redirect(_CF_DOMAINS)

    token = (form.cleaned_data.get("api_token") or "").strip()
    if not token:
        messages.error(request, "API token is required when adding a domain.")
        return redirect(_CF_DOMAINS)

    ok, err, resolved_zone_id = verify_cloudflare_zone(
        form.cleaned_data["zone_id"],
        token,
        domain_name=form.cleaned_data["domain_name"],
    )
    if not ok:
        messages.error(request, f"Cloudflare verification failed: {err}")
        return redirect(_CF_DOMAINS)

    if UserCloudflareDomain.objects.filter(
        user=request.user,
        domain_name=form.cleaned_data["domain_name"],
    ).exists():
        messages.error(request, "This domain is already registered.")
        return redirect(_CF_DOMAINS)

    domain = UserCloudflareDomain(
        user=request.user,
        domain_name=form.cleaned_data["domain_name"],
        zone_id=resolved_zone_id or form.cleaned_data["zone_id"],
        api_token_ciphertext=encrypt_cloudflare_token(request.user.id, token),
        is_active=form.cleaned_data.get("is_active", True),
    )
    apply_cloudflare_domain_form(
        domain, form.cleaned_data, include_identity=False
    )
    domain.save()
    messages.success(request, "Cloudflare domain added.")
    return redirect(_CF_DOMAINS)


@login_required
@require_POST
def cloudflare_domain_delete(request, domain_id: int):
    domain = get_object_or_404(
        UserCloudflareDomain,
        pk=domain_id,
        user=request.user,
    )
    domain.delete()
    messages.success(request, "Domain removed.")
    return redirect(_CF_DOMAINS)


@login_required
@require_POST
def cloudflare_domain_toggle(request, domain_id: int):
    domain = get_object_or_404(
        UserCloudflareDomain,
        pk=domain_id,
        user=request.user,
    )
    domain.is_active = not domain.is_active
    domain.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Domain status updated.")
    return redirect(_CF_DOMAINS)


@login_required
@require_POST
def cloudflare_domain_update(request, domain_id: int):
    domain = get_object_or_404(
        UserCloudflareDomain,
        pk=domain_id,
        user=request.user,
    )
    form = CloudflareDomainForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid domain data.")
        return redirect(_CF_DOMAINS)

    apply_cloudflare_domain_form(domain, form.cleaned_data)

    token = (form.cleaned_data.get("api_token") or "").strip()
    verify_token = token or None
    if not verify_token:
        try:
            verify_token = decrypt_cloudflare_token(
                request.user.id,
                domain.api_token_ciphertext,
            )
        except ValueError:
            messages.error(request, "Stored token invalid; provide a new API token.")
            return redirect(_CF_DOMAINS)

    ok, err, resolved_zone_id = verify_cloudflare_zone(
        domain.zone_id,
        verify_token,
        domain_name=domain.domain_name,
    )
    if not ok:
        messages.error(request, f"Cloudflare verification failed: {err}")
        return redirect(_CF_DOMAINS)

    if resolved_zone_id:
        domain.zone_id = resolved_zone_id

    if token:
        domain.api_token_ciphertext = encrypt_cloudflare_token(request.user.id, token)

    domain.save()
    messages.success(request, "Domain updated.")
    return redirect(_CF_DOMAINS)


@login_required
@require_POST
def cloudflare_domain_sync(request, domain_id: int):
    domain = get_object_or_404(
        UserCloudflareDomain,
        pk=domain_id,
        user=request.user,
    )
    result = sync_domain(domain)
    _flash_sync_result(request, result)
    return redirect(_CF_DOMAINS)
