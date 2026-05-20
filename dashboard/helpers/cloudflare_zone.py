"""Verify Cloudflare zone access when saving a domain."""

from __future__ import annotations

import re
from typing import Any, Optional

import requests

CF_API_BASE = "https://api.cloudflare.com/client/v4"
ZONE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

ERR_ZONE_ID_REQUIRED = "Zone ID or domain name is required."
ERR_TOKEN_REQUIRED = "API token is required."
ERR_ZONE_ID_FORMAT = (
    "Invalid Zone ID: use the 32-character hex ID from Cloudflare Overview."
)
ERR_ZONE_NOT_FOUND = (
    "Zone not found, or domain name does not match the Zone ID."
)
ERR_TOKEN_NO_ACCESS = (
    "API token is invalid, expired, or lacks Zone Read permission."
)
ERR_CF_UNREACHABLE = "Could not reach Cloudflare: {detail}"
ERR_CF_INVALID_RESPONSE = "Invalid response from Cloudflare (HTTP {status})."


def normalize_zone_id(zone_id: str) -> str:
    return (zone_id or "").strip().lower()


def normalize_domain_name(domain_name: str) -> str:
    return (domain_name or "").strip().lower()


def is_valid_zone_id_format(zone_id: str) -> bool:
    return bool(ZONE_ID_RE.match(normalize_zone_id(zone_id)))


def _cf_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.strip()}"}


def _parse_cf_payload(resp: requests.Response) -> tuple[Optional[dict[str, Any]], str]:
    try:
        payload = resp.json()
    except ValueError:
        return None, ERR_CF_INVALID_RESPONSE.format(status=resp.status_code)
    return payload, ""


def _first_cf_error(payload: dict[str, Any]) -> tuple[Optional[int], str]:
    errors = payload.get("errors") or []
    if not errors:
        return None, ""
    err = errors[0]
    code = err.get("code")
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    message = (err.get("message") or str(err)).strip()
    return code, message


def _is_zone_error(*, code: Optional[int], message: str) -> bool:
    lowered = message.lower()
    if code in (1001, 7003):
        return True
    zone_markers = (
        "invalid zone identifier",
        "zone not found",
        "unknown zone",
        "could not route to",
        "no route for",
    )
    return any(marker in lowered for marker in zone_markers)


def _is_auth_error(*, code: Optional[int], message: str, http_status: int) -> bool:
    lowered = message.lower()
    if code in (6003, 10000):
        return True
    if http_status == 401:
        return True
    auth_markers = (
        "authentication error",
        "invalid api token",
        "invalid access token",
        "invalid credentials",
        "invalid format for authorization",
        "invalid request headers",
        "unable to authenticate",
    )
    if any(marker in lowered for marker in auth_markers):
        return True
    if code == 9109 and "token" in lowered:
        return True
    return False


def map_cf_api_error(
    *,
    code: Optional[int] = None,
    message: str = "",
    http_status: int = 0,
    had_valid_zone_id: bool = True,
) -> str:
    """Map a Cloudflare API v4 error to a short user-facing message."""
    return _map_cf_zone_error(
        code=code,
        message=message,
        http_status=http_status,
        had_valid_zone_id=had_valid_zone_id,
    )


def _map_cf_zone_error(
    *,
    code: Optional[int],
    message: str,
    http_status: int,
    had_valid_zone_id: bool,
) -> str:
    if _is_zone_error(code=code, message=message):
        if had_valid_zone_id:
            return ERR_ZONE_NOT_FOUND
        return ERR_ZONE_ID_FORMAT

    if _is_auth_error(code=code, message=message, http_status=http_status):
        return ERR_TOKEN_NO_ACCESS

    if code == 9109 or http_status == 403:
        if had_valid_zone_id:
            return ERR_ZONE_NOT_FOUND
        return ERR_ZONE_ID_FORMAT

    if message:
        return message[:200]

    if had_valid_zone_id:
        return ERR_ZONE_NOT_FOUND
    return ERR_ZONE_ID_FORMAT


def _get_zone_by_id(zone_id: str, token: str) -> tuple[bool, str]:
    try:
        resp = requests.get(
            f"{CF_API_BASE}/zones/{zone_id}",
            headers=_cf_headers(token),
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, ERR_CF_UNREACHABLE.format(detail=exc)

    payload, parse_err = _parse_cf_payload(resp)
    if parse_err:
        return False, parse_err

    if payload.get("success"):
        result = payload.get("result") or {}
        if result.get("id"):
            return True, ""
        return False, ERR_ZONE_NOT_FOUND

    code, message = _first_cf_error(payload)
    return False, _map_cf_zone_error(
        code=code,
        message=message,
        http_status=resp.status_code,
        had_valid_zone_id=True,
    )


def _lookup_zone_by_name(domain_name: str, token: str) -> tuple[bool, str, str]:
    domain_name = normalize_domain_name(domain_name)
    if not domain_name:
        return False, ERR_ZONE_NOT_FOUND, ""

    try:
        resp = requests.get(
            f"{CF_API_BASE}/zones",
            headers=_cf_headers(token),
            params={"name": domain_name, "per_page": 50},
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, ERR_CF_UNREACHABLE.format(detail=exc), ""

    payload, parse_err = _parse_cf_payload(resp)
    if parse_err:
        return False, parse_err, ""

    if not payload.get("success"):
        code, message = _first_cf_error(payload)
        return (
            False,
            _map_cf_zone_error(
                code=code,
                message=message,
                http_status=resp.status_code,
                had_valid_zone_id=False,
            ),
            "",
        )

    for zone in payload.get("result") or []:
        if normalize_domain_name(zone.get("name") or "") != domain_name:
            continue
        resolved = normalize_zone_id(zone.get("id") or "")
        if is_valid_zone_id_format(resolved):
            return True, "", resolved

    return False, ERR_ZONE_NOT_FOUND, ""


def verify_cloudflare_zone(
    zone_id: str,
    api_token: str,
    *,
    domain_name: Optional[str] = None,
) -> tuple[bool, str, str]:
    """
    Verify the token can access the zone.

    Tries GET /zones/{zone_id} when the ID looks valid; on failure or invalid
    format, falls back to GET /zones?name={domain_name}.

    Returns (ok, error_message, resolved_zone_id).
    """
    zone_id = normalize_zone_id(zone_id)
    domain_name = normalize_domain_name(domain_name or "")
    token = (api_token or "").strip()

    if not zone_id and not domain_name:
        return False, ERR_ZONE_ID_REQUIRED, ""
    if not token:
        return False, ERR_TOKEN_REQUIRED, ""

    if is_valid_zone_id_format(zone_id):
        ok, err = _get_zone_by_id(zone_id, token)
        if ok:
            return True, "", zone_id

        if domain_name:
            looked_up, lookup_err, resolved = _lookup_zone_by_name(domain_name, token)
            if looked_up:
                if resolved == zone_id:
                    return True, "", resolved
                ok_id, id_err = _get_zone_by_id(resolved, token)
                if ok_id:
                    return True, "", resolved
                return False, lookup_err or id_err or ERR_ZONE_NOT_FOUND, ""
            return False, err or lookup_err or ERR_ZONE_NOT_FOUND, ""

        return False, err or ERR_ZONE_NOT_FOUND, ""

    if domain_name:
        looked_up, lookup_err, resolved = _lookup_zone_by_name(domain_name, token)
        if looked_up:
            return True, "", resolved
        return False, lookup_err or ERR_ZONE_ID_FORMAT, ""

    return False, ERR_ZONE_ID_FORMAT, ""
