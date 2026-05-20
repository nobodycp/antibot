from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.decorators import superuser_required
from core.htmx_navigation import render_page_or_shell

from ..cloudflare_token_crypto import encrypt_cloudflare_token
from ..forms import CloudflareDomainForm, apply_cloudflare_domain_form
from ..helpers.cloudflare_zone import verify_cloudflare_zone
from ..models import UserCloudflareDomain
from tools.services.cloudflare_sync_service import DomainSyncResult, sync_domain


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


def _domains_context(target_user: User):
    return {
        "target_user": target_user,
        "domains": UserCloudflareDomain.objects.filter(user=target_user).order_by(
            "domain_name"
        ),
        "cf_zone_defaults": UserCloudflareDomain(),
    }


@superuser_required
def user_domains_view(request, user_id: int):
    target_user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            form = CloudflareDomainForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Domain name, zone ID, and API token are required.")
                return redirect("dashboard:user_domains", user_id=user_id)

            token = (form.cleaned_data.get("api_token") or "").strip()
            if not token:
                messages.error(request, "API token is required when adding a domain.")
                return redirect("dashboard:user_domains", user_id=user_id)

            ok, err, resolved_zone_id = verify_cloudflare_zone(
                form.cleaned_data["zone_id"],
                token,
                domain_name=form.cleaned_data["domain_name"],
            )
            if not ok:
                messages.error(request, f"Cloudflare verification failed: {err}")
                return redirect("dashboard:user_domains", user_id=user_id)

            if UserCloudflareDomain.objects.filter(
                user=target_user,
                domain_name=form.cleaned_data["domain_name"],
            ).exists():
                messages.error(request, "This domain is already registered for this user.")
                return redirect("dashboard:user_domains", user_id=user_id)

            domain = UserCloudflareDomain(
                user=target_user,
                domain_name=form.cleaned_data["domain_name"],
                zone_id=resolved_zone_id or form.cleaned_data["zone_id"],
                api_token_ciphertext=encrypt_cloudflare_token(target_user.id, token),
                is_active=form.cleaned_data.get("is_active", True),
            )
            apply_cloudflare_domain_form(
                domain, form.cleaned_data, include_identity=False
            )
            domain.save()
            messages.success(request, "Domain added.")
            return redirect("dashboard:user_domains", user_id=user_id)

        if action == "delete":
            domain_id = request.POST.get("domain_id")
            UserCloudflareDomain.objects.filter(
                pk=domain_id,
                user=target_user,
            ).delete()
            messages.success(request, "Domain removed.")
            return redirect("dashboard:user_domains", user_id=user_id)

        if action == "toggle":
            domain = get_object_or_404(
                UserCloudflareDomain,
                pk=request.POST.get("domain_id"),
                user=target_user,
            )
            domain.is_active = not domain.is_active
            domain.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Domain status updated.")
            return redirect("dashboard:user_domains", user_id=user_id)

        if action == "update":
            domain = get_object_or_404(
                UserCloudflareDomain,
                pk=request.POST.get("domain_id"),
                user=target_user,
            )
            form = CloudflareDomainForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Invalid domain data.")
                return redirect("dashboard:user_domains", user_id=user_id)

            apply_cloudflare_domain_form(domain, form.cleaned_data)

            token = (form.cleaned_data.get("api_token") or "").strip()
            verify_token = token or None
            if not verify_token:
                try:
                    from ..cloudflare_token_crypto import decrypt_cloudflare_token

                    verify_token = decrypt_cloudflare_token(
                        target_user.id,
                        domain.api_token_ciphertext,
                    )
                except ValueError:
                    messages.error(request, "Stored token invalid; provide a new API token.")
                    return redirect("dashboard:user_domains", user_id=user_id)

            ok, err, resolved_zone_id = verify_cloudflare_zone(
                domain.zone_id,
                verify_token,
                domain_name=domain.domain_name,
            )
            if not ok:
                messages.error(request, f"Cloudflare verification failed: {err}")
                return redirect("dashboard:user_domains", user_id=user_id)

            if resolved_zone_id:
                domain.zone_id = resolved_zone_id

            if token:
                domain.api_token_ciphertext = encrypt_cloudflare_token(
                    target_user.id,
                    token,
                )

            domain.save()
            messages.success(request, "Domain updated.")
            return redirect("dashboard:user_domains", user_id=user_id)

    ctx = _domains_context(target_user)
    ctx["admin_mode"] = True
    ctx["header_subtitle"] = f"Manage zones for {target_user.username}"
    return render_page_or_shell(
        request,
        full_template="dashboard/user_domains.html",
        shell_template="dashboard/partials/shell/user_domains.html",
        context=ctx,
    )


@superuser_required
@require_POST
def user_domain_sync(request, user_id: int, domain_id: int):
    target_user = get_object_or_404(User, id=user_id)
    domain = get_object_or_404(
        UserCloudflareDomain,
        pk=domain_id,
        user=target_user,
    )
    result = sync_domain(domain)
    _flash_sync_result(request, result)
    return redirect("dashboard:user_domains", user_id=user_id)
