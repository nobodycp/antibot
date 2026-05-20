from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from dashboard.cloudflare_token_crypto import encrypt_cloudflare_token
from dashboard.forms import CloudflareDomainForm, apply_cloudflare_domain_form
from dashboard.models import UserCloudflareDomain
from tools.services.cloudflare_zone_settings import (
    effective_security_level,
    sync_zone_settings,
)

User = get_user_model()


class CloudflareDomainFormTests(TestCase):
    def test_off_not_in_security_level_choices(self):
        values = {c[0] for c in UserCloudflareDomain.SECURITY_LEVEL_CHOICES}
        self.assertNotIn("off", values)

    def test_form_normalizes_legacy_off_post(self):
        form = CloudflareDomainForm(
            data={
                "domain_name": "example.com",
                "zone_id": "z1",
                "security_level": "off",
                "min_tls_version": "1.2",
                "ssl_mode": "full",
                "challenge_ttl": "1800",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["security_level"],
            UserCloudflareDomain.SECURITY_ESSENTIALLY_OFF,
        )

    def test_under_attack_sets_security_level(self):
        form = CloudflareDomainForm(
            data={
                "domain_name": "example.com",
                "zone_id": "z1",
                "under_attack_mode": True,
                "security_level": "medium",
                "min_tls_version": "1.2",
                "ssl_mode": "full",
                "challenge_ttl": "1800",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["security_level"],
            UserCloudflareDomain.SECURITY_UNDER_ATTACK,
        )

    def test_apply_form_sets_zone_fields(self):
        user = User.objects.create_user(username="u1", password="p")
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
                "bot_fight_mode": True,
                "always_use_https": True,
                "http3_enabled": True,
                "zero_rtt_enabled": True,
                "automatic_https_rewrites": True,
                "security_level": "high",
                "min_tls_version": "1.3",
                "ssl_mode": "strict",
                "challenge_ttl": "3600",
            }
        )
        self.assertTrue(form.is_valid())
        apply_cloudflare_domain_form(domain, form.cleaned_data, include_identity=False)
        self.assertTrue(domain.bot_fight_mode)
        self.assertTrue(domain.always_use_https)
        self.assertTrue(domain.http3_enabled)
        self.assertTrue(domain.zero_rtt_enabled)
        self.assertTrue(domain.automatic_https_rewrites)
        self.assertEqual(domain.security_level, "high")
        self.assertEqual(domain.min_tls_version, "1.3")
        self.assertEqual(domain.ssl_mode, "strict")
        self.assertEqual(domain.challenge_ttl, 3600)


class CloudflareZoneSettingsSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="zs_user", password="pass")
        self.domain = UserCloudflareDomain.objects.create(
            user=self.user,
            domain_name="example.com",
            zone_id="zone123",
            api_token_ciphertext=encrypt_cloudflare_token(self.user.id, "test-token"),
            always_use_https=True,
            browser_integrity_check=False,
            security_level=UserCloudflareDomain.SECURITY_MEDIUM,
            min_tls_version="1.2",
            ssl_mode="full",
            challenge_ttl=1800,
        )

    def test_effective_security_level_under_attack(self):
        self.domain.under_attack_mode = True
        self.domain.security_level = UserCloudflareDomain.SECURITY_MEDIUM
        self.assertEqual(
            effective_security_level(self.domain),
            UserCloudflareDomain.SECURITY_UNDER_ATTACK,
        )

    def test_effective_security_level_maps_legacy_off(self):
        self.domain.security_level = UserCloudflareDomain.SECURITY_OFF
        self.assertEqual(
            effective_security_level(self.domain),
            UserCloudflareDomain.SECURITY_ESSENTIALLY_OFF,
        )

    def test_normalize_security_level_classmethod(self):
        self.assertEqual(
            UserCloudflareDomain.normalize_security_level("off"),
            "essentially_off",
        )
        self.assertEqual(
            UserCloudflareDomain.normalize_security_level("medium"),
            "medium",
        )

    @patch("tools.services.cloudflare_zone_settings._cf_request")
    def test_sync_skips_patch_when_cf_matches_db(self, mock_cf):
        patch_calls = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "/settings/" in path:
                if path.endswith("/always_use_https"):
                    return True, {"result": {"value": "on"}}, ""
                if path.endswith("/browser_check"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/ssl"):
                    return True, {"result": {"value": "full"}}, ""
                if path.endswith("/min_tls_version"):
                    return True, {"result": {"value": "1.2"}}, ""
                if path.endswith("/security_level"):
                    return True, {"result": {"value": "medium"}}, ""
                if path.endswith("/challenge_ttl"):
                    return True, {"result": {"value": 1800}}, ""
                if path.endswith("/http3"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/0rtt"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/automatic_https_rewrites"):
                    return True, {"result": {"value": "off"}}, ""
            if method == "GET" and path.endswith("/bot_management"):
                return True, {
                    "result": {
                        "fight_mode": False,
                        "ai_bots_protection": "disabled",
                        "crawler_protection": "disabled",
                        "content_bots_protection": "disabled",
                    }
                }, ""
            if method == "PATCH":
                patch_calls.append(path)
            if method == "PUT":
                patch_calls.append(path)
            return True, {}, ""

        mock_cf.side_effect = cf_side_effect

        result = sync_zone_settings(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertFalse(result.changed)
        self.assertTrue(result.skipped)
        self.assertEqual(patch_calls, [])

    @patch("tools.services.cloudflare_zone_settings._cf_request")
    def test_sync_patches_only_changed_setting(self, mock_cf):
        patch_paths = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "/settings/" in path:
                if path.endswith("/always_use_https"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/browser_check"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/ssl"):
                    return True, {"result": {"value": "full"}}, ""
                if path.endswith("/min_tls_version"):
                    return True, {"result": {"value": "1.2"}}, ""
                if path.endswith("/security_level"):
                    return True, {"result": {"value": "medium"}}, ""
                if path.endswith("/challenge_ttl"):
                    return True, {"result": {"value": 1800}}, ""
                if path.endswith("/http3"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/0rtt"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/automatic_https_rewrites"):
                    return True, {"result": {"value": "off"}}, ""
            if method == "GET" and path.endswith("/bot_management"):
                return True, {"result": {}}, ""
            if method == "PATCH":
                patch_paths.append(path)
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_zone_settings(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(len(patch_paths), 1)
        self.assertTrue(patch_paths[0].endswith("/always_use_https"))

    @patch("tools.services.cloudflare_zone_settings._cf_request")
    def test_sync_patches_http3_when_differs(self, mock_cf):
        self.domain.http3_enabled = True
        patch_paths = []

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "/settings/" in path:
                if path.endswith("/http3"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/always_use_https"):
                    return True, {"result": {"value": "on"}}, ""
                if path.endswith("/browser_check"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/ssl"):
                    return True, {"result": {"value": "full"}}, ""
                if path.endswith("/min_tls_version"):
                    return True, {"result": {"value": "1.2"}}, ""
                if path.endswith("/security_level"):
                    return True, {"result": {"value": "medium"}}, ""
                if path.endswith("/challenge_ttl"):
                    return True, {"result": {"value": 1800}}, ""
                if path.endswith("/0rtt"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/automatic_https_rewrites"):
                    return True, {"result": {"value": "off"}}, ""
            if method == "GET" and path.endswith("/bot_management"):
                return True, {"result": {}}, ""
            if method == "PATCH":
                patch_paths.append(path)
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_zone_settings(self.domain, "token")
        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(len(patch_paths), 1)
        self.assertTrue(patch_paths[0].endswith("/http3"))

    @patch("tools.services.cloudflare_zone_settings._cf_request")
    def test_sync_migrates_legacy_off_in_db(self, mock_cf):
        self.domain.security_level = UserCloudflareDomain.SECURITY_OFF
        self.domain.save(update_fields=["security_level"])

        def cf_side_effect(method, path, token, **kwargs):
            if method == "GET" and "/settings/" in path:
                if path.endswith("/security_level"):
                    return True, {"result": {"value": "essentially_off"}}, ""
                if path.endswith("/always_use_https"):
                    return True, {"result": {"value": "on"}}, ""
                if path.endswith("/browser_check"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/ssl"):
                    return True, {"result": {"value": "full"}}, ""
                if path.endswith("/min_tls_version"):
                    return True, {"result": {"value": "1.2"}}, ""
                if path.endswith("/challenge_ttl"):
                    return True, {"result": {"value": 1800}}, ""
                if path.endswith("/http3"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/0rtt"):
                    return True, {"result": {"value": "off"}}, ""
                if path.endswith("/automatic_https_rewrites"):
                    return True, {"result": {"value": "off"}}, ""
            if method == "GET" and path.endswith("/bot_management"):
                return True, {
                    "result": {
                        "fight_mode": False,
                        "ai_bots_protection": "disabled",
                        "crawler_protection": "disabled",
                        "content_bots_protection": "disabled",
                    }
                }, ""
            if method == "PATCH":
                body = kwargs.get("json_body") or {}
                if path.endswith("/security_level"):
                    self.assertEqual(body.get("value"), "essentially_off")
                return True, {}, ""
            return False, None, "unexpected"

        mock_cf.side_effect = cf_side_effect

        result = sync_zone_settings(self.domain, "token")
        self.assertTrue(result.ok)
        self.domain.refresh_from_db()
        self.assertEqual(
            self.domain.security_level,
            UserCloudflareDomain.SECURITY_ESSENTIALLY_OFF,
        )
        self.assertTrue(
            any("Enterprise-only" in w for w in result.warnings),
            result.warnings,
        )
