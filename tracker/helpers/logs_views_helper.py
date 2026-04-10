from django.db.models import Q

from .list_helpers import (
    list_partial_context,
    list_page_context,
    list_search_q,
    paginated_page,
    visitor_logs_search_q,
)


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


def logs_list_page_context(list_key: str, page_obj, q: str) -> dict:
    return list_page_context(list_key, page_obj, q)


def logs_partial_context(list_key: str, page_obj, q: str, request) -> dict:
    return list_partial_context(list_key, page_obj, q, request)


__all__ = [
    "apply_country_code_filter",
    "apply_ip_info_fields_search",
    "apply_visitor_like_fields_search",
    "list_search_q",
    "logs_list_page_context",
    "logs_partial_context",
    "paginated_page",
    "visitor_logs_search_q",
]
