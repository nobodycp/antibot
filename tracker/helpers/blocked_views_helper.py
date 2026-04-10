from .list_helpers import (
    list_partial_context as _list_partial_context,
    list_page_context as _list_page_context,
    list_search_q,
    list_table_only_context as _list_table_only_context,
    paginated_page,
)


def apply_search_filter(queryset, q: str, field_name: str):
    if not q:
        return queryset
    return queryset.filter(**{f"{field_name}__icontains": q})


def blocked_list_page_context(list_key: str, page_obj, q: str) -> dict:
    return _list_page_context(list_key, page_obj, q)


def blocked_table_only_context(list_key: str, page_obj, q: str) -> dict:
    return _list_table_only_context(list_key, page_obj, q)


def blocked_partial_context(list_key: str, page_obj, q: str, request) -> dict:
    return _list_partial_context(list_key, page_obj, q, request)


__all__ = [
    "apply_search_filter",
    "blocked_list_page_context",
    "blocked_partial_context",
    "blocked_table_only_context",
    "list_search_q",
    "paginated_page",
]
