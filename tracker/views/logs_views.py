from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from core.decorators import superuser_required

from ..rule_cache_invalidation import invalidate_tracker_rule_caches
from ..helpers.logs_views_helper import (
    apply_country_code_filter,
    apply_visitor_like_fields_search,
    list_search_q,
    visitor_logs_search_q,
)
from ..helpers.ownership import rejected_logs_queryset, visitor_logs_queryset
from ..models import AllowedCountry, RejectedVisitor, Visitor
from .list_flow import (
    logs_after_post_htmx_or_redirect,
    logs_render_full_page,
    logs_render_partial,
    logs_render_table,
)


@superuser_required
def allowed_country_view(request):
    if request.method == 'POST':
        code = request.POST.get('country')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if code:
            code = code.strip().upper()
            if not AllowedCountry.objects.filter(code=code).exists():
                AllowedCountry.objects.create(code=code)
                messages.success(request, f"✅ Country code {code} added.")
            else:
                messages.warning(request, f"⚠️ {code} already exists.")
        elif delete_id:
            try:
                obj = AllowedCountry.objects.get(id=delete_id)
                messages.error(request, f"🗑️ {obj.code} deleted.")
                obj.delete()
            except AllowedCountry.DoesNotExist:
                messages.error(request, "❌ Entry not found.")
        elif delete_all:
            count = AllowedCountry.objects.count()
            AllowedCountry.objects.all().delete()
            invalidate_tracker_rule_caches()
            messages.error(request, f"🧹 Deleted {count} country codes.")
        else:
            messages.error(request, "Invalid action.")

        return logs_after_post_htmx_or_redirect(
            request,
            get_q=list_search_q,
            ordered_qs=AllowedCountry.objects.all().order_by("code"),
            apply_filter=apply_country_code_filter,
            list_key="allowed_countries",
            partial_template="tracker/partials/allowed_country_partial.html",
            redirect_to="tracker:allowed_country",
        )

    return logs_render_full_page(
        request,
        get_q=list_search_q,
        ordered_qs=AllowedCountry.objects.all().order_by("code"),
        apply_filter=apply_country_code_filter,
        list_key="allowed_countries",
        template="tracker/allowed_country.html",
    )


@superuser_required
def allowed_country_partial(request):
    return logs_render_partial(
        request,
        get_q=list_search_q,
        ordered_qs=AllowedCountry.objects.all().order_by("code"),
        apply_filter=apply_country_code_filter,
        list_key="allowed_countries",
        partial_template="tracker/partials/allowed_country_partial.html",
    )


@superuser_required
def allowed_country_table(request):
    return logs_render_table(
        request,
        get_q=list_search_q,
        ordered_qs=AllowedCountry.objects.all().order_by("code"),
        apply_filter=apply_country_code_filter,
        list_key="allowed_countries",
        table_template="tracker/partials/allowed_country_table.html",
    )


######################################################################
@login_required
def allowed_logs_view(request):
    base_qs = visitor_logs_queryset(request.user).order_by("-timestamp")
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if delete_id:
            try:
                log = base_qs.get(id=delete_id)
                ip = log.ip_address
                if request.user.is_superuser:
                    Visitor.objects.filter(ip_address=ip).delete()
                else:
                    Visitor.objects.filter(ip_address=ip, owner=request.user).delete()
                messages.error(request, f"🗑️ Deleted all logs for IP: {ip}")
            except Visitor.DoesNotExist:
                messages.error(request, "Log not found.")
        elif delete_all:
            if request.user.is_superuser:
                Visitor.objects.all().delete()
            else:
                Visitor.objects.filter(owner=request.user).delete()
            messages.success(request, "✅ All allowed logs have been deleted.")
        else:
            messages.error(request, "Invalid action.")

        return logs_after_post_htmx_or_redirect(
            request,
            get_q=visitor_logs_search_q,
            ordered_qs=visitor_logs_queryset(request.user).order_by("-timestamp"),
            apply_filter=apply_visitor_like_fields_search,
            list_key="logs",
            partial_template="tracker/partials/allowed_logs_partial.html",
            redirect_to="tracker:allowed_logs",
        )

    return logs_render_full_page(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=base_qs,
        apply_filter=apply_visitor_like_fields_search,
        list_key="logs",
        template="tracker/allowed_logs.html",
    )


@login_required
def allowed_logs_partial(request):
    return logs_render_partial(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=visitor_logs_queryset(request.user).order_by("-timestamp"),
        apply_filter=apply_visitor_like_fields_search,
        list_key="logs",
        partial_template="tracker/partials/allowed_logs_partial.html",
    )


@login_required
def allowed_logs_table(request):
    return logs_render_table(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=visitor_logs_queryset(request.user).order_by("-timestamp"),
        apply_filter=apply_visitor_like_fields_search,
        list_key="logs",
        table_template="tracker/partials/allowed_logs_table.html",
    )


######################################################################
@login_required
def denied_logs_view(request):
    base_qs = rejected_logs_queryset(request.user).order_by("-timestamp")
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')
        delete_all_subnet_reason = request.POST.get('delete_all_subnet_reason')

        if delete_id:
            try:
                log = base_qs.get(id=delete_id)
                ip = log.ip_address
                if request.user.is_superuser:
                    RejectedVisitor.objects.filter(ip_address=ip).delete()
                else:
                    RejectedVisitor.objects.filter(ip_address=ip, owner=request.user).delete()
                messages.success(request, f"🗑️ Deleted all logs for IP: {ip}")
            except RejectedVisitor.DoesNotExist:
                messages.error(request, "Log not found.")
        elif delete_all:
            if request.user.is_superuser:
                RejectedVisitor.objects.all().delete()
            else:
                RejectedVisitor.objects.filter(owner=request.user).delete()
            messages.success(request, "✅ All denied logs have been deleted.")
        elif delete_all_subnet_reason:
            subnet_qs = RejectedVisitor.objects.filter(reason="Subnet")
            if not request.user.is_superuser:
                subnet_qs = subnet_qs.filter(owner=request.user)
            deleted_count, _ = subnet_qs.delete()
            if deleted_count:
                messages.success(
                    request,
                    f"🗑️ Deleted {deleted_count} denied log(s) with reason Subnet.",
                )
            else:
                messages.info(request, "ℹ️ No denied logs with reason Subnet to delete.")
        else:
            messages.error(request, "Invalid action.")

        return logs_after_post_htmx_or_redirect(
            request,
            get_q=visitor_logs_search_q,
            ordered_qs=rejected_logs_queryset(request.user).order_by("-timestamp"),
            apply_filter=apply_visitor_like_fields_search,
            list_key="logs",
            partial_template="tracker/partials/denied_logs_partial.html",
            redirect_to="tracker:denied_logs",
            per_page=10,
        )

    return logs_render_full_page(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=base_qs,
        apply_filter=apply_visitor_like_fields_search,
        list_key="logs",
        template="tracker/denied_logs.html",
        per_page=10,
    )


@login_required
def denied_logs_partial(request):
    return logs_render_partial(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=rejected_logs_queryset(request.user).order_by("-timestamp"),
        apply_filter=apply_visitor_like_fields_search,
        list_key="logs",
        partial_template="tracker/partials/denied_logs_partial.html",
        per_page=10,
    )


@login_required
def denied_logs_table(request):
    return logs_render_table(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=rejected_logs_queryset(request.user).order_by("-timestamp"),
        apply_filter=apply_visitor_like_fields_search,
        list_key="logs",
        table_template="tracker/partials/denied_logs_table.html",
        per_page=10,
    )
