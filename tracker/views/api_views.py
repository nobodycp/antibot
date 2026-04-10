from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import AllowedCountry
from ..services.visitor_context_service import build_visitor_context
from ..services.visitor_decision_service import evaluate_visitor_decision
from ..services.visitor_persistence_service import (
    persist_allowed_visitor,
    persist_rejected_visitor,
)


class LogVisitorAPIView(APIView):
    def post(self, request):
        allowed_codes = list(AllowedCountry.objects.values_list('code', flat=True))
        ip = request.data.get('ip')
        user_agent_str = request.data.get('useragent', '')

        if not ip or not user_agent_str:
            return Response({'error': 'Missing ip or useragent'}, status=400)

        ctx = build_visitor_context(ip, user_agent_str)
        decision = evaluate_visitor_decision(ip, ctx, allowed_codes)

        if not decision.allowed:
            persist_rejected_visitor(ip, ctx, decision.reason)
            return Response(
                {
                    'status': 'access_denied',
                    'reason': decision.response_reason(ctx.country_code),
                },
                status=403,
            )

        persist_allowed_visitor(ip, user_agent_str, ctx)
        return Response({'status': 'access_granted'}, status=201)
