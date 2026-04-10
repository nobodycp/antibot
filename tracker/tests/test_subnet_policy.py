from django.test import TestCase, override_settings

from tracker.helpers.blocked_subnet_rules import (
    get_blocked_subnet_cidr_list,
    invalidate_blocked_subnet_cidr_cache,
)
from tracker.models import BlockedSubnet
from tracker.policy.global_policy import subnet_deny_reason_if_blocked

_TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "subnet-policy-tests",
    }
}


@override_settings(CACHES=_TEST_CACHES)
class SubnetPolicyCacheTests(TestCase):
    def tearDown(self):
        invalidate_blocked_subnet_cidr_cache()

    def test_subnet_deny_reason_matches_cidr(self):
        BlockedSubnet.objects.create(cidr="198.51.100.0/24")
        invalidate_blocked_subnet_cidr_cache()
        self.assertEqual(subnet_deny_reason_if_blocked("198.51.100.50"), "Subnet")
        self.assertIsNone(subnet_deny_reason_if_blocked("10.0.0.1"))

    def test_cached_cidr_list_includes_new_subnet(self):
        BlockedSubnet.objects.create(cidr="203.0.113.0/24")
        invalidate_blocked_subnet_cidr_cache()
        self.assertIn("203.0.113.0/24", get_blocked_subnet_cidr_list())
