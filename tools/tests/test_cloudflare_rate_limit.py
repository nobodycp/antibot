from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from dashboard.cloudflare_token_crypto import encrypt_cloudflare_token
from dashboard.forms import CloudflareDomainForm, apply_cloudflare_domain_form
from dashboard.models import UserCloudflareDomain
from tools.services.cloudflare_rate_limit import (
    RATE_LIMIT_RULE_DESC,
    build_rate_limit_rule,
    rate_limit_config_matches,
    rate_limit_rule_matches,
    sync_rate_limit,
)
from tools.services.cloudflare_sync_service import sync_domain

User = get_user_model()


class RateLimitRuleBuilderTests(TestCase):
    def test_build_rate_limit_rule(self):
        user = User.objects.create_user(username="rl_u", password="p")
        domain = UserCloudflareDomain(
            user=user,
            domain_name="example.com",
            zone_id="z1",
            rate_limit_enabled=True,
            rate_limit_requests=30,
            rate_limit_period_seconds=10,
            rate_limit_action=UserCloudflareDomain.RATE_LIMIT_ACTION_BLOCK,
            rate_limit_duration_seconds=10,
        )
        rule = build_rate_limit_rule(domain)
        self.assertEqual(rule["description"], RATE_LIMIT_RULE_DESC)
        self.assertEqual(rule["action"], "block")
        self.assertEqual(rule["ratelimit"]["requests_per_period"], 30)
        self.assertEqual(rule["ratelimit"]["period"], 10)
        self.assertEqual(rule["ratelimit"]["mitigation_timeout"], 10)
        self.assertEqual(
            rule["ratelimit"]["characteristics"], ["ip.src", "cf.colo.id"]
        )


class RateLimitSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rl_sync", password="pass")
        self.domain = UserCloudflareDomain.objects.create(
            user=self.user,
            domain_name="example.com",
            zone_id="zone123",
            api_token_ciphertext=encrypt_cloudflare_token(self.user.id, "test-token"),
            is_active=True,
            rate_limit_enabled=True,
            rate_limit_requests=30,
            rate_limit_period_seconds=10,
            rate_limit_action=UserCloudflareDomain.RATE_LIMIT_ACTION_BLOCK,
            rate_limit_duration_seconds=10,
        )

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_skips_when_unchanged(self, mock_cf):
        desired = build_rate_limit_rule(self.domain)
        put_called = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "http_ratelimit" in path:
                return True, {
                    "result": {
                        "id": "rl_rs1",
                        "rules": [desired],
                    }
                }, ""
            if method == "PUT":
                put_called.append(True)
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_rate_limit(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertFalse(result.changed)
        self.assertFalse(put_called)

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_creates_when_enabled_and_missing(self, mock_cf):
        put_bodies = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl_rs1", "rules": []}}, ""
            if method == "PUT" and "rulesets" in path:
                put_bodies.append(kwargs.get("json_body", {}))
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_rate_limit(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertFalse(result.skipped)
        self.assertTrue(result.changed)
        self.assertEqual(len(put_bodies), 1)
        rules = put_bodies[0]["rules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["description"], RATE_LIMIT_RULE_DESC)
        self.assertEqual(rules[0]["ratelimit"]["requests_per_period"], 30)

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_removes_when_disabled(self, mock_cf):
        self.domain.rate_limit_enabled = False
        self.domain.save()
        existing = build_rate_limit_rule(
            UserCloudflareDomain(
                user=self.user,
                domain_name="example.com",
                zone_id="zone123",
                rate_limit_enabled=True,
                rate_limit_requests=30,
                rate_limit_period_seconds=10,
                rate_limit_duration_seconds=10,
            )
        )
        put_bodies = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "http_ratelimit" in path:
                return True, {
                    "result": {"id": "rl_rs1", "rules": [existing]},
                }, ""
            if method == "PUT":
                put_bodies.append(kwargs.get("json_body", {}))
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_rate_limit(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(put_bodies[0]["rules"], [])

    def test_rate_limit_rule_matches(self):
        rule = build_rate_limit_rule(self.domain)
        self.assertTrue(rate_limit_rule_matches(rule, rule))

    def test_rate_limit_rule_does_not_match_legacy_ip_only(self):
        desired = build_rate_limit_rule(self.domain)
        legacy = {**desired, "ratelimit": {**desired["ratelimit"], "characteristics": ["ip.src"]}}
        self.assertFalse(rate_limit_rule_matches(legacy, desired))

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_adopts_single_matching_rule_in_place(self, mock_cf):
        desired = build_rate_limit_rule(self.domain)
        legacy = {
            **desired,
            "id": "rule-legacy-1",
            "description": "30 req per 10s block 10s",
        }
        put_bodies = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl_rs1", "rules": [legacy]}}, ""
            if method == "PUT" and "rulesets" in path:
                put_bodies.append(kwargs.get("json_body", {}))
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_rate_limit(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        rules = put_bodies[0]["rules"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], "rule-legacy-1")
        self.assertEqual(rules[0]["description"], RATE_LIMIT_RULE_DESC)

    def test_rate_limit_config_matches_ignores_description(self):
        desired = build_rate_limit_rule(self.domain)
        legacy = {**desired, "description": "legacy label"}
        self.assertTrue(rate_limit_config_matches(legacy, desired))
        self.assertFalse(rate_limit_rule_matches(legacy, desired))

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_updates_when_characteristics_missing_colo(self, mock_cf):
        desired = build_rate_limit_rule(self.domain)
        legacy = {**desired, "ratelimit": {**desired["ratelimit"], "characteristics": ["ip.src"]}}
        put_bodies = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl_rs1", "rules": [legacy]}}, ""
            if method == "PUT" and "rulesets" in path:
                put_bodies.append(kwargs.get("json_body", {}))
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_rate_limit(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(
            put_bodies[0]["rules"][-1]["ratelimit"]["characteristics"],
            ["ip.src", "cf.colo.id"],
        )


class RateLimitFormTests(TestCase):
    def test_apply_form_sets_rate_limit_fields(self):
        user = User.objects.create_user(username="rl_form", password="p")
        domain = UserCloudflareDomain(
            user=user,
            domain_name="example.com",
            zone_id="z1",
            api_token_ciphertext=encrypt_cloudflare_token(user.id, "tok"),
        )
        form = CloudflareDomainForm(
            data={
                "domain_name": "example.com",
                "zone_id": "z1",
                "security_level": "medium",
                "min_tls_version": "1.2",
                "ssl_mode": "full",
                "challenge_ttl": "1800",
                "rate_limit_enabled": True,
                "rate_limit_requests": "50",
                "rate_limit_period_seconds": "15",
                "rate_limit_action": "challenge",
                "rate_limit_duration_seconds": "20",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        apply_cloudflare_domain_form(domain, form.cleaned_data, include_identity=False)
        self.assertTrue(domain.rate_limit_enabled)
        self.assertEqual(domain.rate_limit_requests, 50)
        self.assertEqual(domain.rate_limit_period_seconds, 15)
        self.assertEqual(domain.rate_limit_action, "challenge")
        self.assertEqual(domain.rate_limit_duration_seconds, 20)


class RateLimitDomainSyncIntegrationTests(TestCase):
    """sync_domain calls rate limit sync after WAF + zone settings."""

    def setUp(self):
        self.user = User.objects.create_user(username="rl_int", password="pass")
        self.domain = UserCloudflareDomain.objects.create(
            user=self.user,
            domain_name="example.com",
            zone_id="zone123",
            api_token_ciphertext=encrypt_cloudflare_token(self.user.id, "test-token"),
            is_active=True,
            rate_limit_enabled=True,
            rate_limit_requests=30,
            rate_limit_period_seconds=10,
            rate_limit_duration_seconds=10,
        )

    @patch("tools.services.cloudflare_sync_service.sync_zone_settings")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_blocked_cidrs")
    @patch("tools.services.cloudflare_sync_service._get_allowed_country_codes")
    def test_sync_domain_includes_rate_limit_put(
        self, mock_countries, mock_cidrs, mock_cf, mock_zone_sync
    ):
        from tools.services.cloudflare_zone_settings import ZoneSettingsSyncResult

        mock_zone_sync.return_value = ZoneSettingsSyncResult(ok=True, skipped=True)
        mock_cidrs.return_value = []
        mock_countries.return_value = []
        rate_put_bodies = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {"result": {"id": "waf1", "rules": []}}, ""
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {"result": []}, ""
            if method == "PUT" and "rulesets" in path:
                body = kwargs.get("json_body") or {}
                rules = body.get("rules") or []
                if rules and rules[0].get("ratelimit"):
                    rate_put_bodies.append(body)
                return True, {}, ""
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        result = sync_domain(self.domain)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(len(rate_put_bodies), 1)
        self.assertEqual(
            rate_put_bodies[0]["rules"][0]["description"], RATE_LIMIT_RULE_DESC
        )
