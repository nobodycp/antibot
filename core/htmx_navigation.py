"""Helpers for dashboard shell navigation (full page vs HTMX fragment)."""

from __future__ import annotations

from django.shortcuts import render


def is_htmx_get(request) -> bool:
    return request.method == "GET" and bool(request.headers.get("HX-Request"))


def render_page_or_shell(
    request,
    *,
    full_template: str,
    shell_template: str | None,
    context: dict,
):
    if shell_template and is_htmx_get(request):
        return render(request, shell_template, context)
    return render(request, full_template, context)
