"""Reusable render/redirect patterns for tracker list + HTMX CRUD views."""

from django.shortcuts import redirect, render

from ..helpers.blocked_views_helper import (
    apply_search_filter,
    blocked_list_page_context,
    blocked_partial_context,
    blocked_table_only_context,
    list_search_q,
    paginated_page,
)
from ..helpers.logs_views_helper import (
    logs_list_page_context,
    logs_partial_context,
    paginated_page as logs_paginated_page,
)


def htmx_request(request) -> bool:
    return bool(request.headers.get("HX-Request"))


# --- Blocked rules lists (apply_search_filter + blocked_* context) ---


def blocked_render_full_page(
    request,
    *,
    ordered_qs,
    search_field: str,
    list_key: str,
    template: str,
):
    q = list_search_q(request)
    qs = apply_search_filter(ordered_qs, q, search_field)
    page_obj = paginated_page(request, qs)
    return render(request, template, blocked_list_page_context(list_key, page_obj, q))


def blocked_render_partial(
    request,
    *,
    ordered_qs,
    search_field: str,
    list_key: str,
    partial_template: str,
):
    q = list_search_q(request)
    qs = apply_search_filter(ordered_qs, q, search_field)
    page_obj = paginated_page(request, qs)
    return render(
        request,
        partial_template,
        blocked_partial_context(list_key, page_obj, q, request),
    )


def blocked_render_table(
    request,
    *,
    ordered_qs,
    search_field: str,
    list_key: str,
    table_template: str,
    table_only: bool = False,
):
    q = list_search_q(request)
    qs = apply_search_filter(ordered_qs, q, search_field)
    page_obj = paginated_page(request, qs)
    if table_only:
        ctx = blocked_table_only_context(list_key, page_obj, q)
    else:
        ctx = blocked_list_page_context(list_key, page_obj, q)
    return render(request, table_template, ctx)


def blocked_after_post_htmx_or_redirect(
    request,
    *,
    ordered_qs,
    search_field: str,
    list_key: str,
    partial_template: str,
    redirect_to: str,
    force_first_page: bool = True,
):
    if htmx_request(request):
        q = list_search_q(request)
        qs = apply_search_filter(ordered_qs, q, search_field)
        page_obj = paginated_page(request, qs, force_first_page=force_first_page)
        return render(
            request,
            partial_template,
            blocked_partial_context(list_key, page_obj, q, request),
        )
    return redirect(redirect_to)


# --- Logs / IP info style (custom apply_filter + logs_* context) ---


def logs_render_full_page(
    request,
    *,
    get_q,
    ordered_qs,
    apply_filter,
    list_key: str,
    template: str,
    per_page: int = 20,
):
    q = get_q(request)
    queryset = apply_filter(ordered_qs, q)
    page_obj = logs_paginated_page(request, queryset, per_page=per_page)
    return render(request, template, logs_list_page_context(list_key, page_obj, q))


def logs_render_partial(
    request,
    *,
    get_q,
    ordered_qs,
    apply_filter,
    list_key: str,
    partial_template: str,
    per_page: int = 20,
):
    q = get_q(request)
    queryset = apply_filter(ordered_qs, q)
    page_obj = logs_paginated_page(request, queryset, per_page=per_page)
    return render(
        request,
        partial_template,
        logs_partial_context(list_key, page_obj, q, request),
    )


def logs_render_table(
    request,
    *,
    get_q,
    ordered_qs,
    apply_filter,
    list_key: str,
    table_template: str,
    per_page: int = 20,
):
    q = get_q(request)
    queryset = apply_filter(ordered_qs, q)
    page_obj = logs_paginated_page(request, queryset, per_page=per_page)
    return render(request, table_template, logs_list_page_context(list_key, page_obj, q))


def logs_after_post_htmx_or_redirect(
    request,
    *,
    get_q,
    ordered_qs,
    apply_filter,
    list_key: str,
    partial_template: str,
    redirect_to: str,
    per_page: int = 20,
    force_first_page: bool = True,
):
    if htmx_request(request):
        q = get_q(request)
        queryset = apply_filter(ordered_qs, q)
        page_obj = logs_paginated_page(
            request, queryset, per_page=per_page, force_first_page=force_first_page
        )
        return render(
            request,
            partial_template,
            logs_partial_context(list_key, page_obj, q, request),
        )
    return redirect(redirect_to)
