from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import UserAPIKey

from ..models import AllowedCountry
from ..services.visitor_context_service import build_visitor_context
from ..services.visitor_decision_service import evaluate_visitor_decision
from ..services.visitor_persistence_service import (
    persist_allowed_visitor,
    persist_rejected_visitor,
)


def _resolve_api_user(request):
    sent = (
        request.headers.get("X-API-Key")
        or request.headers.get("X-API-KEY")
        or ""
    ).strip()
    if not sent:
        return None
    try:
        row = UserAPIKey.objects.select_related("user").get(api_key=sent)
    except UserAPIKey.DoesNotExist:
        return None
    return row.user


class LogVisitorAPIView(APIView):
    def post(self, request):
        api_user = _resolve_api_user(request)
        if api_user is None:
            return Response({"error": "Invalid or missing API key"}, status=403)
        request.api_user = api_user
        if getattr(request, "_request", None) is not None:
            request._request.api_user = api_user

        allowed_codes = list(AllowedCountry.objects.values_list('code', flat=True))
        ip = request.data.get('ip')
        user_agent_str = request.data.get('useragent', '')

        if not ip or not user_agent_str:
            return Response({'error': 'Missing ip or useragent'}, status=400)

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
