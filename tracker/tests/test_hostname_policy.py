from django.test import SimpleTestCase, TestCase, override_settings

from tracker.helpers.blocked_hostname_rules import (
    get_blocked_hostname_rules_normalized,
    normalize_hostname_for_match,
    visitor_hostname_matches_blocked_list,
)
from tracker.models import AllowedCountry, BlockedHostname
from tracker.services.visitor_decision_service import evaluate_visitor_decision
from tracker.services.visitor_context_service import VisitorContext


def _ctx(hostname: str) -> VisitorContext:
    return VisitorContext(
        os="x",
        browser="y",
        hostname=hostname,
        isp="z",
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


class NormalizeHostnameTests(SimpleTestCase):
    def test_strips_and_lowercases(self):
        self.assertEqual(normalize_hostname_for_match("  WWW.EXAMPLE.COM. "), "www.example.com")


class VisitorHostnameMatchTests(SimpleTestCase):
    def test_exact_match(self):
        self.assertTrue(
            visitor_hostname_matches_blocked_list("www.evil.com", ("www.evil.com",))
        )

    def test_subdomain_of_rule(self):
        self.assertTrue(visitor_hostname_matches_blocked_list("a.evil.com", ("evil.com",)))

    def test_rule_is_superdomain_string_legacy(self):
        self.assertTrue(visitor_hostname_matches_blocked_list("evil.com", ("foo.evil.com",)))

    def test_single_label_matches_component(self):
        self.assertTrue(visitor_hostname_matches_blocked_list("x.bad.y", ("bad",)))

    def test_substring_not_in_label_list_does_not_match(self):
        self.assertFalse(visitor_hostname_matches_blocked_list("notevil.com", ("evil",)))

    def test_case_insensitive(self):
        self.assertTrue(
            visitor_hostname_matches_blocked_list("WWW.EXAMPLE.COM", ("example.com",))
        )


_API_TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "hostname-policy-tests",
    }
}


@override_settings(CACHES=_API_TEST_CACHES)
class HostnameDecisionIntegrationTests(TestCase):
    def setUp(self):
        AllowedCountry.objects.create(code="US")

    def tearDown(self):
        from tracker.helpers.blocked_hostname_rules import invalidate_blocked_hostname_rules_cache

        invalidate_blocked_hostname_rules_cache()

    def test_blocked_subdomain(self):
        BlockedHostname.objects.create(hostname="evil.com")
        d = evaluate_visitor_decision("198.51.100.1", _ctx("www.evil.com"), ["US"])
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "Hostname")

    def test_not_blocked_similar_substring(self):
        BlockedHostname.objects.create(hostname="evil")
        d = evaluate_visitor_decision("198.51.100.2", _ctx("notevil.com"), ["US"])
        self.assertTrue(d.allowed)

    def test_cache_loads_rules(self):
        BlockedHostname.objects.create(hostname="block.example")
        rules = get_blocked_hostname_rules_normalized()
        self.assertIn("block.example", rules)
