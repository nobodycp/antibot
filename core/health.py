"""Lightweight health endpoint for load balancers and deploy checks."""

from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """
    GET /health/ — JSON: database, cache, and static asset discoverability.
    Returns 503 if the database is unreachable or the default cache round-trip fails.
    """
    payload = {
        "ok": True,
        "database": False,
        "cache": False,
        "static_design_system_css": False,
    }

    try:
        connection.ensure_connection()
        payload["database"] = True
    except Exception as exc:  # pragma: no cover - defensive
        payload["ok"] = False
        payload["database_error"] = str(exc)

    try:
        cache.set("health_check", "ok", 5)
        payload["cache"] = cache.get("health_check") == "ok"
    except Exception as exc:  # pragma: no cover
        payload["ok"] = False
        payload["cache_error"] = str(exc)

    if not payload["cache"]:
        payload["ok"] = False

    ds_path = finders.find("dashboard/css/design-system.css")
    payload["static_design_system_css"] = bool(ds_path)

    if not payload["static_design_system_css"]:
        payload["ok"] = False

    status_code = 200 if payload["ok"] else 503
    return JsonResponse(payload, status=status_code)
