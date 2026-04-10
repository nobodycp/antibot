"""Shared list/search/pagination helpers for tracker list + HTMX partial views."""

from django.contrib import messages
from django.core.paginator import Paginator


def list_search_q(request) -> str:
    return (request.GET.get("q") or "").strip()


def visitor_logs_search_q(request) -> str:
    return (request.GET.get("q") or request.GET.get("search") or "").strip()


def paginated_page(request, queryset, *, per_page=20, force_first_page: bool = False):
    paginator = Paginator(queryset, per_page)
    if force_first_page:
        return paginator.get_page(1)
    return paginator.get_page(request.GET.get("page"))


def list_page_context(list_key: str, page_obj, q: str) -> dict:
    return {
        list_key: page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
    }


def list_partial_context(list_key: str, page_obj, q: str, request) -> dict:
    ctx = list_page_context(list_key, page_obj, q)
    ctx["messages"] = messages.get_messages(request)
    return ctx


def list_table_only_context(list_key: str, page_obj, q: str) -> dict:
    return {
        list_key: page_obj.object_list,
        "q": q,
    }
