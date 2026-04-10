from django.contrib import messages

from core.decorators import superuser_required

from ..helpers.logs_views_helper import (
    apply_ip_info_fields_search,
    visitor_logs_search_q,
)
from ..models import IPInfo
from .list_flow import (
    logs_after_post_htmx_or_redirect,
    logs_render_full_page,
    logs_render_partial,
    logs_render_table,
)
from .utility_views import add_block_rule


@superuser_required
def ip_info_view(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

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
            ordered_qs=IPInfo.objects.all().order_by("-last_seen"),
            apply_filter=apply_ip_info_fields_search,
            list_key="ips",
            partial_template="tracker/partials/ip_info_partial.html",
            redirect_to="tracker:ip_info",
            per_page=10,
        )

    return logs_render_full_page(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=IPInfo.objects.all().order_by("-last_seen"),
        apply_filter=apply_ip_info_fields_search,
        list_key="ips",
        template="tracker/ip_info.html",
        per_page=10,
    )


@superuser_required
def ip_info_partial(request):
    return logs_render_partial(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=IPInfo.objects.all().order_by("-last_seen"),
        apply_filter=apply_ip_info_fields_search,
        list_key="ips",
        partial_template="tracker/partials/ip_info_partial.html",
        per_page=10,
    )


@superuser_required
def ip_info_table(request):
    return logs_render_table(
        request,
        get_q=visitor_logs_search_q,
        ordered_qs=IPInfo.objects.all().order_by("-last_seen"),
        apply_filter=apply_ip_info_fields_search,
        list_key="ips",
        table_template="tracker/partials/ip_info_table.html",
        per_page=10,
    )
