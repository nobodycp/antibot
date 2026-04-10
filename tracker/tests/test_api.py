from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import UserAPIKey
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


# LocMem avoids requiring Redis in CI / dev when project default CACHES uses django-redis.
_API_TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "tracker-api-tests",
    }
}


@override_settings(CACHES=_API_TEST_CACHES)
@patch("tracker.views.api_views.build_visitor_context")
class LogVisitorAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="api_test_user",
            password="test-pass-123",
        )
        self.api_key = UserAPIKey.objects.get(user=self.user).api_key

    def _post(self, url, data, *, include_api_key=True, api_key=None):
        extra = {}
        if include_api_key:
            extra["HTTP_X_API_KEY"] = api_key if api_key is not None else self.api_key
        return self.client.post(url, data, format="json", **extra)

    def test_missing_api_key_returns_403(self, _mock_build):
        url = reverse("tracker:log_visitor")
        r = self._post(
            url,
            {"ip": "198.51.100.1", "useragent": "Mozilla/5.0"},
            include_api_key=False,
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", r.data)

    def test_wrong_api_key_returns_403(self, _mock_build):
        url = reverse("tracker:log_visitor")
        r = self._post(
            url,
            {"ip": "198.51.100.1", "useragent": "Mozilla/5.0"},
            api_key="wrong-key",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", r.data)

    def test_missing_ip_or_useragent_returns_400(self, _mock_build):
        url = reverse("tracker:log_visitor")

        r = self._post(url, {})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", r.data)

        r2 = self._post(url, {"ip": "198.51.100.1"})
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

        r3 = self._post(
            url, {"ip": "198.51.100.1", "useragent": ""}
        )
        self.assertEqual(r3.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_ip_returns_400(self, mock_build):
        url = reverse("tracker:log_visitor")
        r = self._post(
            url,
            {"ip": "not-an-ip", "useragent": "Mozilla/5.0"},
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", r.data)
        mock_build.assert_not_called()

    def test_ip_non_string_returns_400(self, mock_build):
        url = reverse("tracker:log_visitor")
        r = self._post(url, {"ip": 12345, "useragent": "Mozilla/5.0"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        mock_build.assert_not_called()

    def test_useragent_non_string_returns_400(self, mock_build):
        url = reverse("tracker:log_visitor")
        r = self._post(url, {"ip": "198.51.100.1", "useragent": ["bad"]})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        mock_build.assert_not_called()

    def test_useragent_only_control_chars_returns_400(self, mock_build):
        url = reverse("tracker:log_visitor")
        r = self._post(url, {"ip": "198.51.100.1", "useragent": "\x01\x02\r\n"})
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        mock_build.assert_not_called()

    def test_useragent_truncated_before_context(self, mock_build):
        mock_build.return_value = _sample_context(country_code="US")
        AllowedCountry.objects.create(code="US")
        url = reverse("tracker:log_visitor")
        long_ua = "A" * 3000
        r = self._post(url, {"ip": "198.51.100.40", "useragent": long_ua})
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mock_build.assert_called_once()
        called_ip, called_ua = mock_build.call_args[0]
        self.assertEqual(called_ip, "198.51.100.40")
        self.assertEqual(len(called_ua), 2048)

    def test_blocked_ip_returns_403_and_creates_rejected_visitor(self, mock_build):
        mock_build.return_value = _sample_context()
        ip = "198.51.100.22"
        BlockedIP.objects.create(ip_address=ip)
        AllowedCountry.objects.create(code="US")

        url = reverse("tracker:log_visitor")
        before = RejectedVisitor.objects.count()

        r = self._post(
            url,
            {"ip": ip, "useragent": "Mozilla/5.0 (compatible; Test/1.0)"},
        )

        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(r.data.get("status"), "access_denied")
        self.assertEqual(r.data.get("reason"), "Blocked IP")
        self.assertEqual(RejectedVisitor.objects.count(), before + 1)
        rv = RejectedVisitor.objects.latest("id")
        self.assertEqual(rv.ip_address, ip)
        self.assertEqual(rv.reason, "IP")
        self.assertEqual(rv.owner_id, self.user.id)

    def test_allowed_visitor_returns_201_and_creates_visitor(self, mock_build):
        mock_build.return_value = _sample_context(country_code="US")
        AllowedCountry.objects.create(code="US")
        ip = "198.51.100.33"

        url = reverse("tracker:log_visitor")
        ua = "Mozilla/5.0 (compatible; TestBot/1.0)"
        before_v = Visitor.objects.count()

        r = self._post(url, {"ip": ip, "useragent": ua})

        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data.get("status"), "access_granted")
        self.assertEqual(Visitor.objects.count(), before_v + 1)
        v = Visitor.objects.latest("id")
        self.assertEqual(v.ip_address, ip)
        self.assertEqual(v.user_agent, ua)
        self.assertEqual(v.owner_id, self.user.id)
