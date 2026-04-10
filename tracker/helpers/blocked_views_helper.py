from django.contrib import messages
from django.core.paginator import Paginator


def list_search_q(request) -> str:
    return (request.GET.get("q") or "").strip()


def apply_search_filter(queryset, q: str, field_name: str):
    if not q:
        return queryset
    return queryset.filter(**{f"{field_name}__icontains": q})


def paginated_page(request, queryset, *, per_page=20, force_first_page: bool = False):
    paginator = Paginator(queryset, per_page)
    if force_first_page:
        return paginator.get_page(1)
    return paginator.get_page(request.GET.get("page"))


def blocked_list_page_context(list_key: str, page_obj, q: str) -> dict:
    return {
        list_key: page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
    }


def blocked_table_only_context(list_key: str, page_obj, q: str) -> dict:
    return {
        list_key: page_obj.object_list,
        "q": q,
    }


def blocked_partial_context(list_key: str, page_obj, q: str, request) -> dict:
    ctx = blocked_list_page_context(list_key, page_obj, q)
    ctx["messages"] = messages.get_messages(request)
    return ctx
