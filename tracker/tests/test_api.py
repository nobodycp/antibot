from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from tracker.models import AllowedCountry, BlockedIP, RejectedVisitor, Visitor
from tracker.services.visitor_context_service import VisitorContext


def _sample_context(**overrides):
    base = dict(
        os="Windows 10",
        browser="Chrome 120.0",
        hostname="",
        isp="Example ISP",
        country_code="US",
        b_subnet="",
        as_type="",
        is_anonymous=False,
        is_hosting=False,
        is_proxy=False,
        is_vpn=False,
        is_tor=False,
        is_satellite=False,
    )
    base.update(overrides)
    return VisitorContext(**base)


@patch("tracker.views.api_views.build_visitor_context")
class LogVisitorAPITests(APITestCase):
    def test_missing_ip_or_useragent_returns_400(self, _mock_build):
        url = reverse("tracker:log_visitor")

        r = self.client.post(url, {}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", r.data)

        r2 = self.client.post(url, {"ip": "198.51.100.1"}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

        r3 = self.client.post(
            url, {"ip": "198.51.100.1", "useragent": ""}, format="json"
        )
        self.assertEqual(r3.status_code, status.HTTP_400_BAD_REQUEST)

    def test_blocked_ip_returns_403_and_creates_rejected_visitor(self, mock_build):
        mock_build.return_value = _sample_context()
        ip = "198.51.100.22"
        BlockedIP.objects.create(ip_address=ip)
        AllowedCountry.objects.create(code="US")

        url = reverse("tracker:log_visitor")
        before = RejectedVisitor.objects.count()

        r = self.client.post(
            url,
            {"ip": ip, "useragent": "Mozilla/5.0 (compatible; Test/1.0)"},
            format="json",
        )

        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(r.data.get("status"), "access_denied")
        self.assertEqual(r.data.get("reason"), "Blocked IP")
        self.assertEqual(RejectedVisitor.objects.count(), before + 1)
        rv = RejectedVisitor.objects.latest("id")
        self.assertEqual(rv.ip_address, ip)
        self.assertEqual(rv.reason, "IP")

    def test_allowed_visitor_returns_201_and_creates_visitor(self, mock_build):
        mock_build.return_value = _sample_context(country_code="US")
        AllowedCountry.objects.create(code="US")
        ip = "198.51.100.33"

        url = reverse("tracker:log_visitor")
        ua = "Mozilla/5.0 (compatible; TestBot/1.0)"
        before_v = Visitor.objects.count()

        r = self.client.post(url, {"ip": ip, "useragent": ua}, format="json")

        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data.get("status"), "access_granted")
        self.assertEqual(Visitor.objects.count(), before_v + 1)
        v = Visitor.objects.latest("id")
        self.assertEqual(v.ip_address, ip)
        self.assertEqual(v.user_agent, ua)
