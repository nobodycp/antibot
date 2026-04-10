from django.contrib import messages
from django.shortcuts import redirect, render

from core.decorators import superuser_required

from ..helpers.logs_views_helper import (
    apply_ip_info_fields_search,
    logs_list_page_context,
    logs_partial_context,
    paginated_page,
    visitor_logs_search_q,
)
from ..models import IPInfo

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

        if request.headers.get("HX-Request"):
            q = visitor_logs_search_q(request)
            queryset = apply_ip_info_fields_search(
                IPInfo.objects.all().order_by("-last_seen"), q
            )
            page_obj = paginated_page(request, queryset, per_page=10, force_first_page=True)
            return render(
                request,
                "tracker/partials/ip_info_partial.html",
                logs_partial_context("ips", page_obj, q, request),
            )

        return redirect('tracker:ip_info')

    q = visitor_logs_search_q(request)
    queryset = apply_ip_info_fields_search(
        IPInfo.objects.all().order_by("-last_seen"), q
    )
    page_obj = paginated_page(request, queryset, per_page=10)
    return render(
        request,
        "tracker/ip_info.html",
        logs_list_page_context("ips", page_obj, q),
    )


@superuser_required
def ip_info_partial(request):
    q = visitor_logs_search_q(request)
    queryset = apply_ip_info_fields_search(
        IPInfo.objects.all().order_by("-last_seen"), q
    )
    page_obj = paginated_page(request, queryset, per_page=10)
    return render(
        request,
        "tracker/partials/ip_info_partial.html",
        logs_partial_context("ips", page_obj, q, request),
    )


@superuser_required
def ip_info_table(request):
    q = visitor_logs_search_q(request)
    queryset = apply_ip_info_fields_search(
        IPInfo.objects.all().order_by("-last_seen"), q
    )
    page_obj = paginated_page(request, queryset, per_page=10)
    return render(
        request,
        "tracker/partials/ip_info_table.html",
        logs_list_page_context("ips", page_obj, q),
    )
