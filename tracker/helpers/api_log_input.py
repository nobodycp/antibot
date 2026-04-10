"""Validate and normalize inputs for POST /tracker/api/log/ (client-supplied ip + useragent)."""

from __future__ import annotations

import ipaddress

# Typical browsers stay under ~1KB; cap avoids huge payloads and DB bloat.
MAX_USER_AGENT_LENGTH = 2048


def normalize_client_ip(raw) -> tuple[str | None, str | None]:
    """Return (canonical_ip, None) or (None, error_message)."""
    if raw is None:
        return None, "Missing ip"
    if not isinstance(raw, str):
        return None, "Invalid ip"
    s = raw.strip()
    if not s:
        return None, "Missing ip"
    if "\x00" in s:
        return None, "Invalid ip"
    try:
        addr = ipaddress.ip_address(s)
    except ValueError:
        return None, "Invalid ip address"
    return str(addr), None


def normalize_user_agent(raw) -> tuple[str | None, str | None]:
    """Return (user_agent, None) or (None, error_message). Truncates to MAX_USER_AGENT_LENGTH."""
    if raw is None:
        return None, "Missing useragent"
    if not isinstance(raw, str):
        return None, "Invalid useragent"
    s = raw.strip()
    s = "".join(ch for ch in s if ch == "\t" or ord(ch) >= 32)
    if not s:
        return None, "Missing useragent"
    if "\x00" in s:
        return None, "Invalid useragent"
    if len(s) > MAX_USER_AGENT_LENGTH:
        s = s[:MAX_USER_AGENT_LENGTH]
    return s, None
