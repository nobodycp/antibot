from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from ..helpers.logs_views_helper import (
    apply_ip_info_fields_search,
    visitor_logs_search_q,
)
from ..helpers.ownership import ip_info_queryset
from ..models import IPInfo
from .list_flow import (
    logs_after_post_htmx_or_redirect,
    logs_render_full_page,
    logs_render_partial,
    logs_render_table,
)
from .utility_views import add_block_rule


def _ip_info_ordered(user):
    return ip_info_queryset(user).order_by("-last_seen")


@login_required
def ip_info_view(request):
    if request.method == 'POST':
        if not request.user.is_superuser:
            delete_id = request.POST.get("delete_id")
            delete_all = request.POST.get("delete_all")
            if delete_id:
                try:
                    row = _ip_info_ordered(request.user).get(id=delete_id)
                except IPInfo.DoesNotExist:
                    messages.error(request, "Row not found.")
                else:
                    IPInfo.objects.filter(pk=row.pk, owner=request.user).delete()
                    messages.success(
                        request, f"🗑️ Deleted IP info for IP: {row.ip_address}"
                    )
            elif delete_all:
                IPInfo.objects.filter(owner=request.user).delete()
                messages.success(request, "✅ All IP info records have been deleted.")
            else:
                messages.error(request, "Invalid action.")

            return logs_after_post_htmx_or_redirect(
                request,
                get_q=visitor_logs_search_q,
                ordered_qs=_ip_info_ordered(request.user),
                apply_filter=apply_ip_info_fields_search,
                list_key="ips",
                partial_template="tracker/partials/ip_info_partial.html",
                redirect_to="tracker:ip_info",
                per_page=10,
            )

        delete_id = request.POST.get("delete_id")
        delete_all = request.POST.get("delete_all")

        block_type = request.POST.get("block_type")
        block_value = request.POST.get("block_value")
        if block_type and block_value:
            return add_block_rule(request)

        if delete_id:
            try:
                row = IPInfo.objects.get(id=delete_id)
                ip = row.ip_address
                IPInfo.objects.filter(ip_address=ip).delete()
                messages.success(request, f"🗑️ Deleted IP info for IP: {ip}")
            except IPInfo.DoesNotExist:
                messages.error(request, "Row not found.")
        elif delete_all:
            IPInfo.objects.all().delete()
            messages.success(request, "✅ All IP info records have been deleted.")
        else:
            messages.error(request, "Invalid action.")

        return logs_after_post_htmx_or_redirect(
            request,
            get_q=visitor_logs_search_q,
            ordered_qs=_ip_info_ordered(request.user),
            apply_filter=apply_ip_info_fields_search,
            list_key="ips",
            partial_template="tracker/partials/ip_info_partial.html",
            redirect_to="tracker:ip_info",
            per_page=10,
        )

    return logs_render_full_page(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=_ip_info_ordered(request.user),
        apply_filter=apply_ip_info_fields_search,
        list_key="ips",
        template="tracker/ip_info.html",
        per_page=10,
        shell_fragment_template="tracker/partials/shell/ip_info.html",
    )


@login_required
def ip_info_partial(request):
    return logs_render_partial(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=_ip_info_ordered(request.user),
        apply_filter=apply_ip_info_fields_search,
        list_key="ips",
        partial_template="tracker/partials/ip_info_partial.html",
        per_page=10,
    )


@login_required
def ip_info_table(request):
    return logs_render_table(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=_ip_info_ordered(request.user),
        apply_filter=apply_ip_info_fields_search,
        list_key="ips",
        table_template="tracker/partials/ip_info_table.html",
        per_page=10,
    )
