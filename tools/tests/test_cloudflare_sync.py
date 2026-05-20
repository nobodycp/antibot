from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dashboard.cloudflare_token_crypto import encrypt_cloudflare_token
from dashboard.helpers.cloudflare_zone import ERR_TOKEN_NO_ACCESS
from dashboard.models import UserCloudflareDomain
from tools.services.cloudflare_sync_service import (
    IP_LIST_DELETE_BATCH_SIZE,
    IP_LIST_ITEMS_PER_PAGE,
    IP_LIST_POST_BATCH_SIZE,
    SUBNET_RULE_DESC,
    build_country_expression,
    build_inline_subnet_expression,
    build_subnet_expression,
    country_rule_description,
    sync_all_domains,
    sync_domain,
    sync_global_subnets_for_zones,
    sync_subnet_for_domain,
    _sync_ip_list_items,
)

User = get_user_model()

CF_TEST_ZONE_ID = "zone123"
CF_TEST_ACCOUNT_ID = "acct-test"


def _clear_cf_account_id_cache() -> None:
    from tools.services import cloudflare_sync_service

    cloudflare_sync_service._account_id_cache.clear()


def _cf_zone_account_lookup():
    return True, {"result": {"account": {"id": CF_TEST_ACCOUNT_ID}}}, ""


def _cf_bulk_operation_completed():
    return True, {"result": {"id": "op-1", "status": "completed"}}, ""


def _cf_async_list_write_result():
    return True, {"result": {"operation_id": "op-1"}}, ""


def _cf_zone_settings_response(method: str, path: str, domain: UserCloudflareDomain):
    """Mock GET responses for zone settings + bot_management sync."""
    if method == "GET" and "/settings/" in path:
        if path.endswith("/always_use_https"):
            val = "on" if domain.always_use_https else "off"
        elif path.endswith("/browser_check"):
            val = "on" if domain.browser_integrity_check else "off"
        elif path.endswith("/ssl"):
            val = domain.ssl_mode
        elif path.endswith("/min_tls_version"):
            val = domain.min_tls_version
        elif path.endswith("/security_level"):
            from tools.services.cloudflare_zone_settings import effective_security_level

            val = effective_security_level(domain)
        elif path.endswith("/challenge_ttl"):
            val = int(domain.challenge_ttl)
        elif path.endswith("/http3"):
            val = "on" if domain.http3_enabled else "off"
        elif path.endswith("/0rtt"):
            val = "on" if domain.zero_rtt_enabled else "off"
        elif path.endswith("/automatic_https_rewrites"):
            val = "on" if domain.automatic_https_rewrites else "off"
        else:
            return None
        return True, {"result": {"value": val}}, ""
    if method == "GET" and path.endswith("/bot_management"):
        return True, {
            "result": {
                "fight_mode": domain.bot_fight_mode,
                "ai_bots_protection": "block" if domain.block_ai_bots else "disabled",
                "crawler_protection": "enabled" if domain.ai_labyrinth else "disabled",
                "content_bots_protection": (
                    "block" if domain.ai_crawl_control else "disabled"
                ),
            }
        }, ""
    if method in ("PATCH", "PUT") and (
        "/settings/" in path or path.endswith("/bot_management")
    ):
        return True, {}, ""
    return None


class CloudflareExpressionTests(TestCase):
    def test_build_country_expression(self):
        expr = build_country_expression(["us", "de"])
        self.assertEqual(expr, 'not ip.geoip.country in {"DE" "US"}')

    def test_build_country_expression_empty(self):
        self.assertIsNone(build_country_expression([]))

    def test_build_subnet_expression_inline(self):
        expr = build_subnet_expression(["10.0.0.0/8"], "token", "zone1")
        self.assertEqual(expr, "ip.src in {10.0.0.0/8}")

    def test_build_inline_subnet_expression_sorted(self):
        expr = build_inline_subnet_expression(["10.0.0.0/8", "192.0.2.0/24"])
        self.assertEqual(expr, "ip.src in {10.0.0.0/8 192.0.2.0/24}")

    def test_build_inline_subnet_expression_many_cidrs(self):
        expr = build_inline_subnet_expression(
            ["8.8.8.0/24", "192.168.1.0/24", "203.0.113.0/24"]
        )
        self.assertEqual(
            expr,
            "ip.src in {192.168.1.0/24 203.0.113.0/24 8.8.8.0/24}",
        )

    def test_country_rule_description(self):
        self.assertEqual(country_rule_description(42), "antibot:country-allow-42")


class CloudflareSyncDomainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cf_user", password="pass")
        self.domain = UserCloudflareDomain.objects.create(
            user=self.user,
            domain_name="example.com",
            zone_id="zone123",
            api_token_ciphertext=encrypt_cloudflare_token(self.user.id, "test-token"),
            is_active=True,
        )

    @patch("tools.services.cloudflare_sync_service.sync_zone_settings")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_blocked_cidrs")
    @patch("tools.services.cloudflare_sync_service._get_allowed_country_codes")
    def test_sync_domain_merges_antibot_rules(
        self, mock_countries, mock_cidrs, mock_cf, mock_zone
    ):
        from tools.services.cloudflare_zone_settings import ZoneSettingsSyncResult

        mock_zone.return_value = ZoneSettingsSyncResult(ok=True, skipped=True)
        mock_cidrs.return_value = ["192.0.2.0/24"]
        mock_countries.return_value = ["US"]

        existing_rule = {
            "id": "rule-keep",
            "description": "manual rule",
            "action": "log",
            "expression": "true",
        }
        antibot_old = {
            "id": "rule-old",
            "description": SUBNET_RULE_DESC,
            "action": "block",
            "expression": "false",
        }

        put_called = []

        def cf_side_effect(method, path, token, **kwargs):
            zone_resp = _cf_zone_settings_response(method, path, self.domain)
            if zone_resp is not None:
                return zone_resp
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {
                    "result": {
                        "id": "rs1",
                        "rules": [existing_rule, antibot_old],
                    }
                }, ""
            if method == "PUT" and "rulesets" in path:
                put_called.append(True)
                rules = kwargs.get("json_body", {}).get("rules", [])
                self.assertEqual(len(rules), 3)
                descriptions = [r["description"] for r in rules]
                self.assertIn("manual rule", descriptions)
                self.assertIn(SUBNET_RULE_DESC, descriptions)
                self.assertIn(country_rule_description(self.user.id), descriptions)
                self.assertEqual(descriptions.count(SUBNET_RULE_DESC), 1)
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_domain(self.domain, include_subnet=True)
        self.assertTrue(result.ok)
        self.assertFalse(result.skipped)
        self.assertTrue(put_called)
        self.domain.refresh_from_db()
        self.assertEqual(self.domain.last_sync_status, UserCloudflareDomain.SYNC_OK)

    @patch("tools.services.cloudflare_sync_service.sync_zone_settings")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_allowed_country_codes")
    def test_sync_domain_skips_when_already_synced(
        self, mock_countries, mock_cf, mock_zone
    ):
        from tools.services.cloudflare_zone_settings import ZoneSettingsSyncResult

        mock_zone.return_value = ZoneSettingsSyncResult(ok=True, skipped=True)
        mock_countries.return_value = ["US"]
        subnet_expr = build_subnet_expression(["192.0.2.0/24"], "token", "zone123")
        country_expr = build_country_expression(["US"])
        country_desc = country_rule_description(self.user.id)

        def cf_side_effect(method, path, token, **kwargs):
            zone_resp = _cf_zone_settings_response(method, path, self.domain)
            if zone_resp is not None:
                return zone_resp
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {
                    "result": {
                        "id": "rs1",
                        "rules": [
                            {
                                "description": SUBNET_RULE_DESC,
                                "action": "block",
                                "expression": subnet_expr,
                                "enabled": True,
                            },
                            {
                                "description": country_desc,
                                "action": "block",
                                "expression": country_expr,
                                "enabled": True,
                            },
                        ],
                    }
                }, ""
            if method == "PUT":
                self.fail("PUT should not be called when already synced")
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_domain(self.domain)
        self.assertTrue(result.ok)
        self.assertTrue(result.skipped)
        self.assertIn("Already synced", result.message)

    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_blocked_cidrs")
    def test_sync_subnet_only_updates_ip_list_when_adding_cidrs(
        self, mock_cidrs, mock_cf
    ):
        _clear_cf_account_id_cache()
        many_cidrs = [f"10.0.{i}.0/24" for i in range(30)]
        mock_cidrs.return_value = many_cidrs
        list_expr = build_subnet_expression(many_cidrs, "token", "zone123")
        existing_on_cf = [f"10.0.{i}.0/24" for i in range(28)]
        list_post_bodies = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and path == f"/zones/{self.domain.zone_id}":
                return _cf_zone_account_lookup()
            if method == "GET" and "/bulk_operations/" in path:
                return _cf_bulk_operation_completed()
            zone_resp = _cf_zone_settings_response(method, path, self.domain)
            if zone_resp is not None:
                return zone_resp
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {
                    "result": {
                        "id": "rs1",
                        "rules": [
                            {
                                "description": SUBNET_RULE_DESC,
                                "action": "block",
                                "expression": list_expr,
                                "enabled": True,
                            },
                        ],
                    }
                }, ""
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {
                    "result": [{"id": "list1", "name": "antibot_subnet_block"}]
                }, ""
            if method == "GET" and "/rules/lists/list1/items" in path:
                return True, {
                    "result": [
                        {"id": f"id-{i}", "ip": c}
                        for i, c in enumerate(existing_on_cf)
                    ]
                }, ""
            if method == "POST" and "/rules/lists/list1/items" in path:
                list_post_bodies.append(kwargs.get("json_body"))
                return _cf_async_list_write_result()
            if method == "PUT" and "/rules/lists/list1/items" in path:
                self.fail("Full list PUT should not run; use batched POST instead")
            if method == "PUT" and "rulesets" in path:
                self.fail("Ruleset PUT should not run when only IP list items differ")
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        result = sync_subnet_for_domain(self.domain)
        self.assertTrue(result.ok)
        self.assertFalse(result.skipped)
        self.assertEqual(len(list_post_bodies), 1)
        uploaded = {item["ip"] for item in list_post_bodies[0]}
        self.assertEqual(uploaded, {"10.0.28.0/24", "10.0.29.0/24"})
        self.assertIn("IP list updated", result.message)

    @patch("tools.services.cloudflare_sync_service.sync_zone_settings")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_allowed_country_codes")
    def test_sync_domain_updates_when_country_list_changes(
        self, mock_countries, mock_cf, mock_zone
    ):
        from tools.services.cloudflare_zone_settings import ZoneSettingsSyncResult

        mock_zone.return_value = ZoneSettingsSyncResult(ok=True, skipped=True)
        mock_countries.return_value = ["US", "DE"]
        country_desc = country_rule_description(self.user.id)
        old_country_expr = build_country_expression(["US"])
        new_country_expr = build_country_expression(["US", "DE"])
        put_rules = []

        def cf_side_effect(method, path, token, **kwargs):
            zone_resp = _cf_zone_settings_response(method, path, self.domain)
            if zone_resp is not None:
                return zone_resp
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {
                    "result": {
                        "id": "rs1",
                        "rules": [
                            {
                                "description": country_desc,
                                "action": "block",
                                "expression": old_country_expr,
                                "enabled": True,
                            },
                        ],
                    }
                }, ""
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {"result": []}, ""
            if method == "PUT" and "rulesets" in path:
                put_rules.append(kwargs.get("json_body", {}).get("rules", []))
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_domain(self.domain)
        self.assertTrue(result.ok, result.message)
        self.assertFalse(result.skipped)
        self.assertEqual(len(put_rules), 1)
        country_rules = [
            r for r in put_rules[0] if r.get("description") == country_desc
        ]
        self.assertEqual(len(country_rules), 1)
        self.assertEqual(country_rules[0]["expression"], new_country_expr)

    @patch("tools.services.cloudflare_sync_service.sync_zone_settings")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_allowed_country_codes")
    def test_sync_domain_no_countries_warning(
        self, mock_countries, mock_cf, mock_zone
    ):
        from tools.services.cloudflare_zone_settings import ZoneSettingsSyncResult

        mock_zone.return_value = ZoneSettingsSyncResult(ok=True, skipped=True)
        mock_countries.return_value = []

        put_called = []

        def cf_side_effect(method, path, token, **kwargs):
            zone_resp = _cf_zone_settings_response(method, path, self.domain)
            if zone_resp is not None:
                return zone_resp
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {"result": {"id": "rs1", "rules": []}}, ""
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {"result": []}, ""
            if method == "PUT" and "rulesets" in path:
                put_called.append(True)
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_domain(self.domain)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.status, UserCloudflareDomain.SYNC_WARNING)
        self.assertTrue(result.warnings)
        self.assertFalse(put_called)

    @patch("tools.services.cloudflare_sync_service.requests.request")
    def test_sync_domain_authentication_error_maps_helpful_message(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {
            "success": False,
            "errors": [{"code": 10000, "message": "Authentication error"}],
        }
        mock_request.return_value = mock_resp

        result = sync_domain(self.domain)

        self.assertFalse(result.ok)
        self.assertEqual(result.message, ERR_TOKEN_NO_ACCESS)
        self.assertIn("invalid", result.message.lower())

    @patch("tools.services.cloudflare_sync_service.sync_zone_settings")
    @patch("tools.services.cloudflare_sync_service._sync_ip_list_items")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    @patch("tools.services.cloudflare_sync_service._get_allowed_country_codes")
    def test_sync_domain_user_does_not_touch_subnet_ip_list(
        self, mock_countries, mock_cf, mock_ip_list, mock_zone
    ):
        from tools.services.cloudflare_zone_settings import ZoneSettingsSyncResult

        mock_zone.return_value = ZoneSettingsSyncResult(ok=True, skipped=True)
        mock_countries.return_value = ["US"]
        country_desc = country_rule_description(self.user.id)
        country_expr = build_country_expression(["US"])
        subnet_expr = build_subnet_expression(["192.0.2.0/24"], "token", "zone123")
        put_rules = []

        def cf_side_effect(method, path, token, **kwargs):
            zone_resp = _cf_zone_settings_response(method, path, self.domain)
            if zone_resp is not None:
                return zone_resp
            if method == "GET" and "http_ratelimit" in path:
                return True, {"result": {"id": "rl1", "rules": []}}, ""
            if method == "GET" and "http_request_firewall_custom" in path:
                return True, {
                    "result": {
                        "id": "rs1",
                        "rules": [
                            {
                                "description": SUBNET_RULE_DESC,
                                "action": "block",
                                "expression": subnet_expr,
                                "enabled": True,
                            },
                            {
                                "description": country_desc,
                                "action": "block",
                                "expression": "not ip.geoip.country in {\"CA\"}",
                                "enabled": True,
                            },
                        ],
                    }
                }, ""
            if method == "PUT" and "rulesets" in path:
                put_rules.append(kwargs.get("json_body", {}).get("rules", []))
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_domain(self.domain)
        mock_ip_list.assert_not_called()
        self.assertTrue(result.ok, result.message)
        self.assertEqual(len(put_rules), 1)
        descriptions = [r["description"] for r in put_rules[0]]
        self.assertIn(SUBNET_RULE_DESC, descriptions)
        subnet_rules = [r for r in put_rules[0] if r["description"] == SUBNET_RULE_DESC]
        self.assertEqual(subnet_rules[0]["expression"], subnet_expr)
        country_rules = [r for r in put_rules[0] if r["description"] == country_desc]
        self.assertEqual(country_rules[0]["expression"], country_expr)

    @patch("tools.services.cloudflare_sync_service.sync_subnet_for_domain")
    @patch("tools.services.cloudflare_sync_service.sync_domain")
    def test_sync_all_domains_subnet_once_per_zone(
        self, mock_sync_domain, mock_sync_subnet
    ):
        user2 = User.objects.create_user(username="cf_user2", password="pass")
        UserCloudflareDomain.objects.create(
            user=user2,
            domain_name="other.example.com",
            zone_id="zone123",
            api_token_ciphertext=encrypt_cloudflare_token(user2.id, "token2"),
            is_active=True,
        )
        subnet_result = MagicMock(
            ok=True,
            domain_id=self.domain.pk,
            domain_name=self.domain.domain_name,
            status=UserCloudflareDomain.SYNC_OK,
            message="Subnet synced.",
            warnings=[],
            skipped=False,
        )
        mock_sync_subnet.return_value = subnet_result
        mock_sync_domain.return_value = MagicMock(
            ok=True,
            domain_id=0,
            domain_name="x",
            status=UserCloudflareDomain.SYNC_OK,
            message="ok",
            warnings=[],
            skipped=True,
        )

        results = sync_all_domains()

        self.assertEqual(mock_sync_subnet.call_count, 1)
        mock_sync_subnet.assert_called_once()
        called_domain = mock_sync_subnet.call_args[0][0]
        self.assertEqual(called_domain.zone_id, "zone123")
        self.assertEqual(mock_sync_domain.call_count, 2)
        for call in mock_sync_domain.call_args_list:
            self.assertFalse(call.kwargs.get("include_subnet", False))
            self.assertEqual(call.kwargs.get("include_subnet"), False)
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0].message.startswith("[SUBNET]"))

    @patch("tools.services.cloudflare_sync_service.sync_subnet_for_domain")
    def test_sync_global_subnets_for_zones_dedupes_by_zone(
        self, mock_sync_subnet
    ):
        user2 = User.objects.create_user(username="cf_user2", password="pass")
        UserCloudflareDomain.objects.create(
            user=user2,
            domain_name="other.example.com",
            zone_id="zone123",
            api_token_ciphertext=encrypt_cloudflare_token(user2.id, "token2"),
            is_active=True,
        )
        mock_sync_subnet.return_value = MagicMock(
            ok=True,
            domain_id=self.domain.pk,
            domain_name=self.domain.domain_name,
            status=UserCloudflareDomain.SYNC_OK,
            message="Subnet synced.",
            warnings=[],
            skipped=False,
        )
        domains = list(UserCloudflareDomain.objects.filter(is_active=True))
        results = sync_global_subnets_for_zones(domains)
        self.assertEqual(mock_sync_subnet.call_count, 1)
        self.assertEqual(len(results), 1)
        self.assertIn("[SUBNET]", results[0].message)


class CloudflareIpListBatchTests(TestCase):
    def setUp(self):
        _clear_cf_account_id_cache()

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_ip_list_items_paginated_get_and_batched_post(self, mock_cf):
        desired = [f"192.0.2.{i}/32" for i in range(150)]
        page1 = [
            {"id": f"old-{i}", "ip": f"10.0.{i}.0/24"} for i in range(100)
        ]
        page2 = [{"id": "old-100", "ip": "10.0.100.0/24"}]
        post_batches: list[list] = []
        get_calls = 0

        def cf_side_effect(method, path, token, **kwargs):
            nonlocal get_calls
            if method == "GET" and path == f"/zones/{CF_TEST_ZONE_ID}":
                return _cf_zone_account_lookup()
            if method == "GET" and "/bulk_operations/" in path:
                return _cf_bulk_operation_completed()
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {
                    "result": [{"id": "list1", "name": "antibot_subnet_block"}]
                }, ""
            if method == "GET" and "/rules/lists/list1/items" in path:
                get_calls += 1
                params = kwargs.get("query_params") or {}
                if get_calls == 1:
                    self.assertEqual(params.get("per_page"), IP_LIST_ITEMS_PER_PAGE)
                    return True, {
                        "result": page1,
                        "result_info": {"cursors": {"after": "cursor-2"}},
                    }, ""
                self.assertEqual(params.get("cursor"), "cursor-2")
                return True, {"result": page2}, ""
            if method == "DELETE" and "/rules/lists/list1/items" in path:
                body = kwargs.get("json_body") or {}
                self.assertEqual(len(body.get("items", [])), 101)
                return _cf_async_list_write_result()
            if method == "POST" and "/rules/lists/list1/items" in path:
                post_batches.append(kwargs.get("json_body"))
                return _cf_async_list_write_result()
            if method == "PUT" and "/rules/lists/list1/items" in path:
                self.fail("Full list PUT should not be used for large sync")
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        ok, changed, err, _warning = _sync_ip_list_items(
            "token", CF_TEST_ZONE_ID, desired
        )
        self.assertTrue(ok, err)
        self.assertTrue(changed)
        self.assertEqual(get_calls, 2)
        self.assertEqual(len(post_batches), 1)
        self.assertEqual(len(post_batches[0]), len(desired))
        self.assertEqual(
            {item["ip"] for item in post_batches[0]},
            set(desired),
        )

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_ip_list_items_batched_post_over_batch_size(self, mock_cf):
        count = IP_LIST_POST_BATCH_SIZE + 50
        desired = [f"203.0.113.{i}/32" for i in range(count)]
        post_batches: list[list] = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and path == f"/zones/{CF_TEST_ZONE_ID}":
                return _cf_zone_account_lookup()
            if method == "GET" and "/bulk_operations/" in path:
                return _cf_bulk_operation_completed()
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {
                    "result": [{"id": "list1", "name": "antibot_subnet_block"}]
                }, ""
            if method == "GET" and "/rules/lists/list1/items" in path:
                return True, {"result": []}, ""
            if method == "POST" and "/rules/lists/list1/items" in path:
                post_batches.append(kwargs.get("json_body"))
                return _cf_async_list_write_result()
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        ok, changed, err, _warning = _sync_ip_list_items(
            "token", CF_TEST_ZONE_ID, desired
        )
        self.assertTrue(ok, err)
        self.assertTrue(changed)
        self.assertEqual(len(post_batches), 2)
        self.assertEqual(len(post_batches[0]), IP_LIST_POST_BATCH_SIZE)
        self.assertEqual(len(post_batches[1]), 50)

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_ip_list_payload_too_large_error_message(self, mock_cf):
        desired = [f"198.51.100.{i}/32" for i in range(10)]

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and path == f"/zones/{CF_TEST_ZONE_ID}":
                return _cf_zone_account_lookup()
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {
                    "result": [{"id": "list1", "name": "antibot_subnet_block"}]
                }, ""
            if method == "GET" and "/rules/lists/list1/items" in path:
                return True, {"result": []}, ""
            if method == "POST" and "/rules/lists/list1/items" in path:
                return (
                    False,
                    {"errors": [{"message": "Request body too large"}]},
                    "Request body too large",
                )
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        ok, changed, err, _warning = _sync_ip_list_items(
            "token", CF_TEST_ZONE_ID, desired
        )
        self.assertFalse(ok)
        self.assertFalse(changed)
        self.assertIn("Too many subnets (10)", err)
        self.assertIn(str(IP_LIST_POST_BATCH_SIZE), err)

    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_ip_list_clear_uses_batched_delete(self, mock_cf):
        existing = [
            {"id": f"id-{i}", "ip": f"10.1.{i}.0/24"}
            for i in range(IP_LIST_DELETE_BATCH_SIZE + 10)
        ]
        delete_batches: list[list] = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and path == f"/zones/{CF_TEST_ZONE_ID}":
                return _cf_zone_account_lookup()
            if method == "GET" and "/bulk_operations/" in path:
                return _cf_bulk_operation_completed()
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {
                    "result": [{"id": "list1", "name": "antibot_subnet_block"}]
                }, ""
            if method == "GET" and "/rules/lists/list1/items" in path:
                return True, {"result": existing}, ""
            if method == "DELETE" and "/rules/lists/list1/items" in path:
                delete_batches.append(
                    [item["id"] for item in (kwargs.get("json_body") or {}).get("items", [])]
                )
                return _cf_async_list_write_result()
            if method == "PUT" and "/rules/lists/list1/items" in path:
                self.fail("Clearing list should use DELETE batches, not PUT []")
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        ok, changed, err, _warning = _sync_ip_list_items("token", CF_TEST_ZONE_ID, [])
        self.assertTrue(ok, err)
        self.assertTrue(changed)
        self.assertEqual(len(delete_batches), 2)
        self.assertEqual(len(delete_batches[0]), IP_LIST_DELETE_BATCH_SIZE)
        self.assertEqual(len(delete_batches[1]), 10)

    @patch("tools.services.cloudflare_sync_service.time.sleep")
    @patch("tools.services.cloudflare_sync_service._cf_request")
    def test_sync_ip_list_waits_for_bulk_operation_between_batches(
        self, mock_cf, _mock_sleep
    ):
        desired = [f"203.0.113.{i}/32" for i in range(IP_LIST_POST_BATCH_SIZE + 1)]
        bulk_polls = 0

        def cf_side_effect(method, path, token, **kwargs):
            nonlocal bulk_polls
            if method == "GET" and path == f"/zones/{CF_TEST_ZONE_ID}":
                return _cf_zone_account_lookup()
            if method == "GET" and "/bulk_operations/" in path:
                bulk_polls += 1
                return _cf_bulk_operation_completed()
            if method == "GET" and path.endswith("/rules/lists"):
                return True, {
                    "result": [{"id": "list1", "name": "antibot_subnet_block"}]
                }, ""
            if method == "GET" and "/rules/lists/list1/items" in path:
                return True, {"result": []}, ""
            if method == "POST" and "/rules/lists/list1/items" in path:
                return _cf_async_list_write_result()
            return False, None, f"unexpected {method} {path}"

        mock_cf.side_effect = cf_side_effect

        ok, changed, err, _warning = _sync_ip_list_items(
            "token", CF_TEST_ZONE_ID, desired
        )
        self.assertTrue(ok, err)
        self.assertTrue(changed)
        self.assertEqual(bulk_polls, 2)


class CloudSyncPermissionTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.user = User.objects.create_user(username="staff_u", password="pass", is_staff=True)
        self.superuser = User.objects.create_user(
            username="super_u",
            password="pass",
            is_superuser=True,
            is_staff=True,
        )

    def test_non_superuser_cannot_access_cloud_sync(self):
        self.client.force_login(self.user)
        r = self.client.get("/tools/cloud-sync/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login", r.url)

    def test_superuser_can_access_cloud_sync(self):
        self.client.force_login(self.superuser)
        r = self.client.get("/tools/cloud-sync/")
        self.assertEqual(r.status_code, 200)

    def test_cloud_sync_lists_admin_added_active_domain(self):
        target = User.objects.create_user(username="cf_owner", password="pass")
        UserCloudflareDomain.objects.create(
            user=target,
            domain_name="admin-added.example.com",
            zone_id="zone-admin",
            api_token_ciphertext=encrypt_cloudflare_token(target.id, "token"),
            is_active=True,
        )
        inactive = UserCloudflareDomain.objects.create(
            user=target,
            domain_name="inactive.example.com",
            zone_id="zone-inactive",
            api_token_ciphertext=encrypt_cloudflare_token(target.id, "token2"),
            is_active=False,
        )
        self.client.force_login(self.superuser)
        r = self.client.get("/tools/cloud-sync/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "admin-added.example.com")
        self.assertContains(r, "cf_owner")
        self.assertContains(r, ">1<", html=False)
        self.assertContains(r, "active domain")
        self.assertNotContains(r, inactive.domain_name)

    @patch("dashboard.views.user_domains_views.verify_cloudflare_zone", return_value=(True, "", "zone-new"))
    def test_admin_added_domain_via_post_appears_on_cloud_sync(self, _mock_verify):
        target = User.objects.create_user(username="post_owner", password="pass")
        self.client.force_login(self.superuser)
        add_url = reverse("dashboard:user_domains", args=[target.id])
        self.client.post(
            add_url,
            {
                "action": "add",
                "domain_name": "posted.example.com",
                "zone_id": "zone-posted",
                "api_token": "test-token",
                "is_active": "on",
                "security_level": UserCloudflareDomain.SECURITY_MEDIUM,
                "min_tls_version": UserCloudflareDomain.TLS_1_2,
                "ssl_mode": UserCloudflareDomain.SSL_FULL,
                "challenge_ttl": str(UserCloudflareDomain.CHALLENGE_TTL_1800),
            },
        )
        r = self.client.get("/tools/cloud-sync/")
        self.assertContains(r, "posted.example.com")
        self.assertContains(r, "post_owner")

    @patch("tools.views.cloud_sync_views.sync_domain")
    def test_superuser_can_sync_single_domain_from_cloud_sync(self, mock_sync):
        from tools.services.cloudflare_sync_service import DomainSyncResult

        target = User.objects.create_user(username="sync_owner", password="pass")
        domain = UserCloudflareDomain.objects.create(
            user=target,
            domain_name="single.example.com",
            zone_id="zone-single",
            api_token_ciphertext=encrypt_cloudflare_token(target.id, "token"),
            is_active=True,
        )
        mock_sync.return_value = DomainSyncResult(
            ok=True,
            domain_id=domain.pk,
            domain_name=domain.domain_name,
            status=UserCloudflareDomain.SYNC_OK,
            message="Synced.",
            warnings=[],
            skipped=False,
        )
        self.client.force_login(self.superuser)
        url = reverse("tools:cloud_sync_domain_sync", args=[domain.pk])
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse("tools:cloud_sync"))
        mock_sync.assert_called_once_with(domain, include_subnet=False)

    def test_non_superuser_cannot_sync_single_domain_from_cloud_sync(self):
        target = User.objects.create_user(username="no_sync", password="pass")
        domain = UserCloudflareDomain.objects.create(
            user=target,
            domain_name="blocked.example.com",
            zone_id="zone-blocked",
            api_token_ciphertext=encrypt_cloudflare_token(target.id, "token"),
            is_active=True,
        )
        self.client.force_login(self.user)
        url = reverse("tools:cloud_sync_domain_sync", args=[domain.pk])
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login", r.url)

    @patch("tools.views.cloud_sync_views.sync_domain")
    def test_cloud_sync_page_shows_per_domain_sync_button(self, _mock_sync):
        target = User.objects.create_user(username="btn_owner", password="pass")
        domain = UserCloudflareDomain.objects.create(
            user=target,
            domain_name="btn.example.com",
            zone_id="zone-btn",
            api_token_ciphertext=encrypt_cloudflare_token(target.id, "token"),
            is_active=True,
        )
        self.client.force_login(self.superuser)
        r = self.client.get("/tools/cloud-sync/")
        self.assertContains(r, reverse("tools:cloud_sync_domain_sync", args=[domain.pk]))
        self.assertContains(r, ">Sync</button>", html=False)
