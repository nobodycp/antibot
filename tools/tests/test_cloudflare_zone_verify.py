from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from dashboard.helpers.cloudflare_zone import (
    ERR_TOKEN_LISTS_ACCESS,
    ERR_TOKEN_NO_ACCESS,
    ERR_ZONE_ID_FORMAT,
    ERR_ZONE_NOT_FOUND,
    is_valid_zone_id_format,
    map_cf_api_error,
    normalize_zone_id,
    verify_cloudflare_lists_access,
    verify_cloudflare_zone,
)

VALID_ZONE = "a" * 32
OTHER_ZONE = "b" * 32
TEST_ACCOUNT_ID = "c" * 32
TOKEN = "cf-test-token"


def _cf_response(*, status_code=200, success=True, result=None, errors=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "success": success,
        "result": result,
        "errors": errors or [],
    }
    return resp


def _zone_result(zone_id: str = VALID_ZONE, *, name: str = "example.com") -> dict:
    return {"id": zone_id, "name": name, "account": {"id": TEST_ACCOUNT_ID}}


def _zone_and_lists_success(zone_id: str = VALID_ZONE) -> list:
    zone = _cf_response(result=_zone_result(zone_id))
    lists = _cf_response(result=[])
    return [zone, zone, lists]


class CloudflareZoneVerifyTests(SimpleTestCase):
    def test_normalize_zone_id_strips_and_lowercases(self):
        raw = "  ABCD0123" + "0" * 24 + "  "
        self.assertEqual(normalize_zone_id(raw), "abcd0123" + "0" * 24)

    def test_is_valid_zone_id_format(self):
        self.assertTrue(is_valid_zone_id_format(VALID_ZONE))
        self.assertFalse(is_valid_zone_id_format("zone-name"))
        self.assertFalse(is_valid_zone_id_format("short"))

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_valid_zone_id_success(self, mock_get):
        mock_get.side_effect = _zone_and_lists_success()
        ok, err, resolved = verify_cloudflare_zone(
            VALID_ZONE,
            TOKEN,
            domain_name="example.com",
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(resolved, VALID_ZONE)
        self.assertEqual(mock_get.call_count, 3)
        self.assertIn(
            f"/accounts/{TEST_ACCOUNT_ID}/rules/lists",
            mock_get.call_args_list[-1][0][0],
        )

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_invalid_zone_id_format_uses_name_lookup(self, mock_get):
        mock_get.side_effect = [
            _cf_response(result=[_zone_result()]),
            *_zone_and_lists_success(),
        ]

        ok, err, resolved = verify_cloudflare_zone(
            "not-a-valid-zone-id",
            TOKEN,
            domain_name="example.com",
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(resolved, VALID_ZONE)
        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_get.call_args_list[0].kwargs["params"]["name"], "example.com")

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_valid_zone_id_api_error_falls_back_to_name_lookup(self, mock_get):
        zone_by_id = _cf_response(
            success=False,
            errors=[{"code": 1001, "message": "Invalid zone identifier"}],
        )
        zone_by_name = _cf_response(
            result=[
                {"id": OTHER_ZONE, "name": "example.com"},
            ],
        )
        zone_confirm = _cf_response(result=_zone_result(OTHER_ZONE))
        mock_get.side_effect = [
            zone_by_id,
            zone_by_name,
            zone_confirm,
            *_zone_and_lists_success(OTHER_ZONE),
        ]

        ok, err, resolved = verify_cloudflare_zone(
            VALID_ZONE,
            TOKEN,
            domain_name="example.com",
        )
        self.assertTrue(ok)
        self.assertEqual(resolved, OTHER_ZONE)
        self.assertEqual(mock_get.call_count, 5)

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_invalid_format_without_domain_name(self, mock_get):
        ok, err, resolved = verify_cloudflare_zone("example.com", TOKEN)
        self.assertFalse(ok)
        self.assertEqual(err, ERR_ZONE_ID_FORMAT)
        self.assertEqual(resolved, "")
        mock_get.assert_not_called()

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_valid_zone_id_not_in_account_maps_zone_not_found(self, mock_get):
        mock_get.return_value = _cf_response(
            success=False,
            status_code=403,
            errors=[{"code": 9109, "message": "Unauthorized to access this zone"}],
        )
        ok, err, resolved = verify_cloudflare_zone(VALID_ZONE, TOKEN)
        self.assertFalse(ok)
        self.assertEqual(err, ERR_ZONE_NOT_FOUND)
        self.assertEqual(resolved, "")

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_random_zone_and_domain_maps_zone_not_found(self, mock_get):
        zone_by_id = _cf_response(
            success=False,
            status_code=403,
            errors=[{"code": 9109, "message": "Unauthorized to access this zone"}],
        )
        zone_by_name = _cf_response(result=[])
        mock_get.side_effect = [zone_by_id, zone_by_name]

        ok, err, resolved = verify_cloudflare_zone(
            OTHER_ZONE,
            TOKEN,
            domain_name="fake-random.example",
        )
        self.assertFalse(ok)
        self.assertEqual(err, ERR_ZONE_NOT_FOUND)
        self.assertEqual(resolved, "")
        self.assertEqual(mock_get.call_count, 2)

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_authentication_error_message_maps_token_error(self, mock_get):
        mock_get.return_value = _cf_response(
            success=False,
            status_code=401,
            errors=[{"code": 10000, "message": "Authentication error"}],
        )
        ok, err, resolved = verify_cloudflare_zone(VALID_ZONE, TOKEN)
        self.assertFalse(ok)
        self.assertEqual(err, ERR_TOKEN_NO_ACCESS)
        self.assertEqual(resolved, "")
        self.assertIn("invalid", err.lower())

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_invalid_token_on_name_lookup(self, mock_get):
        mock_get.return_value = _cf_response(
            success=False,
            status_code=401,
            errors=[{"code": 6003, "message": "Invalid request headers"}],
        )
        ok, err, resolved = verify_cloudflare_zone(
            "bad",
            TOKEN,
            domain_name="missing.example.com",
        )
        self.assertFalse(ok)
        self.assertEqual(err, ERR_TOKEN_NO_ACCESS)
        self.assertEqual(resolved, "")

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_name_lookup_no_match(self, mock_get):
        mock_get.return_value = _cf_response(result=[])
        ok, err, resolved = verify_cloudflare_zone(
            "bad",
            TOKEN,
            domain_name="missing.example.com",
        )
        self.assertFalse(ok)
        self.assertEqual(err, ERR_ZONE_NOT_FOUND)
        self.assertEqual(resolved, "")

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_bearer_token_header(self, mock_get):
        mock_get.side_effect = _zone_and_lists_success()
        verify_cloudflare_zone(VALID_ZONE, "  secret-token  ")
        headers = mock_get.call_args.kwargs.get("headers") or mock_get.call_args[1].get(
            "headers"
        )
        self.assertEqual(headers["Authorization"], "Bearer secret-token")

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_whitespace_zone_id_normalized_before_request(self, mock_get):
        mock_get.side_effect = _zone_and_lists_success()
        verify_cloudflare_zone(f"  {VALID_ZONE.upper()}  ", TOKEN)
        self.assertIn(f"/zones/{VALID_ZONE}", mock_get.call_args_list[0][0][0])

    def test_map_cf_api_error_lists_403_returns_message_not_zone_not_found(self):
        msg = "Insufficient permissions to list filter rules"
        mapped = map_cf_api_error(
            code=10000,
            message=msg,
            http_status=403,
            lists_operation=True,
        )
        self.assertEqual(mapped, msg)
        self.assertNotEqual(mapped, ERR_ZONE_NOT_FOUND)

    def test_map_cf_api_error_lists_403_without_message_uses_lists_hint(self):
        mapped = map_cf_api_error(http_status=403, lists_operation=True)
        self.assertEqual(mapped, ERR_TOKEN_LISTS_ACCESS)

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_verify_lists_access_forbidden(self, mock_get):
        mock_get.side_effect = [
            _cf_response(result=_zone_result()),
            _cf_response(
                success=False,
                status_code=403,
                errors=[{"code": 10000, "message": "Insufficient permissions"}],
            ),
        ]
        ok, err = verify_cloudflare_lists_access(VALID_ZONE, TOKEN)
        self.assertFalse(ok)
        self.assertEqual(err, "Insufficient permissions")
        self.assertIn(f"/accounts/{TEST_ACCOUNT_ID}/rules/lists", mock_get.call_args[0][0])

    @patch("dashboard.helpers.cloudflare_zone.requests.get")
    def test_verify_zone_fails_when_lists_forbidden(self, mock_get):
        mock_get.side_effect = [
            _cf_response(result=_zone_result()),
            _cf_response(result=_zone_result()),
            _cf_response(
                success=False,
                status_code=403,
                errors=[{"code": 10000, "message": "Insufficient permissions"}],
            ),
        ]
        ok, err, resolved = verify_cloudflare_zone(VALID_ZONE, TOKEN)
        self.assertFalse(ok)
        self.assertEqual(err, "Insufficient permissions")
        self.assertEqual(resolved, "")
