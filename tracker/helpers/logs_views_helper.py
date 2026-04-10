from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q


def list_search_q(request) -> str:
    return (request.GET.get("q") or "").strip()


def visitor_logs_search_q(request) -> str:
    return (request.GET.get("q") or request.GET.get("search") or "").strip()


def apply_country_code_filter(queryset, q: str):
    if not q:
        return queryset
    return queryset.filter(code__icontains=q)


def apply_visitor_like_fields_search(queryset, q: str):
    if not q:
        return queryset
    return queryset.filter(
        Q(ip_address__icontains=q) |
        Q(hostname__icontains=q) |
        Q(isp__icontains=q) |
        Q(os__icontains=q) |
        Q(browser__icontains=q) |
        Q(country__icontains=q)
    )


def apply_ip_info_fields_search(queryset, q: str):
    if not q:
        return queryset
    return queryset.filter(
        Q(ip_address__icontains=q) |
        Q(isp__icontains=q) |
        Q(subnet__icontains=q) |
        Q(as_type__icontains=q)
    )


def paginated_page(request, queryset, *, per_page=20, force_first_page: bool = False):
    paginator = Paginator(queryset, per_page)
    if force_first_page:
        return paginator.get_page(1)
    return paginator.get_page(request.GET.get("page"))


def logs_list_page_context(list_key: str, page_obj, q: str) -> dict:
    return {
        list_key: page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
    }


def logs_partial_context(list_key: str, page_obj, q: str, request) -> dict:
    ctx = logs_list_page_context(list_key, page_obj, q)
    ctx["messages"] = messages.get_messages(request)
    return ctx
