import hashlib
import time

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import UserAPIKey

from ..helpers.api_log_input import normalize_client_ip, normalize_user_agent
from ..policy.global_policy import allowed_country_codes
from ..services.visitor_context_service import build_visitor_context
from ..services.visitor_decision_service import evaluate_visitor_decision
from ..services.visitor_persistence_service import (
    persist_allowed_visitor,
    persist_rejected_visitor,
)

_LOG_API_RATE_LIMIT = 300
_LOG_API_RATE_WINDOW_SEC = 60


def _raw_api_key_from_request(request):
    return (
        request.headers.get("X-API-Key")
        or request.headers.get("X-API-KEY")
        or ""
    ).strip()


def _api_key_lookup_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_api_user(request):
    sent = _raw_api_key_from_request(request)
    if not sent:
        return None, ""
    digest = _api_key_lookup_digest(sent)
    row = (
        UserAPIKey.objects.select_related("user")
        .filter(api_key_lookup_hash=digest)
        .first()
    )
    if row is None:
        row = (
            UserAPIKey.objects.select_related("user")
            .filter(api_key=sent)
            .first()
        )
    if row is None:
        return None, sent
    return row.user, sent


def _log_api_rate_limit_allows(raw_api_key: str) -> bool:
    """Fixed window: up to _LOG_API_RATE_LIMIT POSTs per key per _LOG_API_RATE_WINDOW_SEC."""
    window = int(time.time()) // _LOG_API_RATE_WINDOW_SEC
    digest = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()[:32]
    cache_key = f"tracker:log_api:rl:{digest}:{window}"
    ttl = _LOG_API_RATE_WINDOW_SEC + 5
    try:
        n = cache.incr(cache_key)
    except ValueError:
        # Key missing: create counter (add is atomic on supported backends).
        if cache.add(cache_key, 1, ttl):
            n = 1
        else:
            try:
                n = cache.incr(cache_key)
            except ValueError:
                n = 1
    return n <= _LOG_API_RATE_LIMIT


class LogVisitorAPIView(APIView):
    def post(self, request):
        api_user, raw_key = _resolve_api_user(request)
        if api_user is None:
            return Response({"error": "Invalid or missing API key"}, status=403)
        if not _log_api_rate_limit_allows(raw_key):
            return Response(
                {"error": "Rate limit exceeded. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        request.api_user = api_user
        if getattr(request, "_request", None) is not None:
            request._request.api_user = api_user

        allowed_codes = allowed_country_codes()

        ip, ip_err = normalize_client_ip(request.data.get('ip'))
        user_agent_str, ua_err = normalize_user_agent(request.data.get('useragent'))
        if ip_err:
            return Response({'error': ip_err}, status=400)
        if ua_err:
            return Response({'error': ua_err}, status=400)

        ctx = build_visitor_context(ip, user_agent_str)
        decision = evaluate_visitor_decision(ip, ctx, allowed_codes)

        if not decision.allowed:
            persist_rejected_visitor(ip, ctx, decision.reason, owner=api_user)
            return Response(
                {
                    'status': 'access_denied',
                    'reason': decision.response_reason(ctx.country_code),
                },
                status=403,
            )

        persist_allowed_visitor(ip, user_agent_str, ctx, owner=api_user)
        return Response({'status': 'access_granted'}, status=201)
