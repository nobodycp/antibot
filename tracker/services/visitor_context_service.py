"""
Build enriched visitor context from User-Agent, reverse DNS, and external IP APIs.

All network/API enrichment is applied atomically: if any step raises, every
API-derived field falls back to the same empty defaults as before (no partial
enrichment), preserving historical behavior.

Successful API enrichment is cached (see ``TRACKER_IP_CONTEXT_CACHE_TIMEOUT`` in
settings); failures are not cached so the next request can retry.
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

import requests
import user_agents
from django.conf import settings
from django.core.cache import cache


_CONNECT_TIMEOUT_SEC = 3
_READ_TIMEOUT_SEC = 5
_REQUEST_TIMEOUT = (_CONNECT_TIMEOUT_SEC, _READ_TIMEOUT_SEC)

# Short-lived negative cache after enrichment failure to protect upstream APIs.
_ENRICHMENT_FAILURE_TTL_SEC = 60


@dataclass
class VisitorContext:
    os: str
    browser: str
    hostname: str
    isp: str
    country_code: str
    b_subnet: str
    as_type: str
    is_anonymous: bool
    is_hosting: bool
    is_proxy: bool
    is_vpn: bool
    is_tor: bool
    is_satellite: bool


@dataclass
class _ApiEnrichment:
    isp: str
    country_code: str
    b_subnet: str
    as_type: str
    is_anonymous: bool
    is_hosting: bool
    is_proxy: bool
    is_vpn: bool
    is_tor: bool
    is_satellite: bool


def _parse_user_agent(user_agent_str: str) -> tuple[str, str]:
    parsed = user_agents.parse(user_agent_str)
    os_str = f"{parsed.os.family} {parsed.os.version_string}"
    browser_str = f"{parsed.browser.family} {parsed.browser.version_string}"
    return os_str, browser_str


def _reverse_dns_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _enrichment_failure_cache_key(ip: str) -> str:
    return f"tracker:ip_enrich_fail_v1:{ip}"


def _fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=_REQUEST_TIMEOUT)
    return r.json()


def _load_api_enrichment(ip: str) -> _ApiEnrichment:
    """Fetch ISP, geo, subnet, and privacy flags from external APIs in parallel."""
    urls = (
        f"https://ipwho.is/{ip}",
        f"https://api.ipapi.is/?q={ip}",
        f"https://ipinfo.io/api/pricing/samples/{ip}",
    )
    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_map = {pool.submit(_fetch_json, u): i for i, u in enumerate(urls)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            results[idx] = fut.result()

    response = results[0]
    isp = response.get("connection", {}).get("isp", "") or ""
    country_code = (response.get("country_code", "") or "").upper()

    response3 = results[1]
    b_subnet = response3.get("asn", {}).get("route", "") or ""

    response2 = results[2]
    as_type = response2.get("core", {}).get("sample", {}).get("as", {}).get("type", "") or ""
    is_anonymous = bool(response2.get("core", {}).get("sample", {}).get("is_anonymous", False))
    is_hosting = bool(response2.get("core", {}).get("sample", {}).get("is_hosting", False))
    privacy = response2.get("business", {}).get("sample", {}).get("privacy", {}) or {}
    is_proxy = bool(privacy.get("proxy", False))
    is_vpn = bool(privacy.get("vpn", False))
    is_tor = bool(privacy.get("tor", False))
    is_satellite = bool(response2.get("core", {}).get("sample", {}).get("is_mobile", False))

    return _ApiEnrichment(
        isp=isp,
        country_code=country_code,
        b_subnet=b_subnet,
        as_type=as_type,
        is_anonymous=is_anonymous,
        is_hosting=is_hosting,
        is_proxy=is_proxy,
        is_vpn=is_vpn,
        is_tor=is_tor,
        is_satellite=is_satellite,
    )


def _empty_api_enrichment() -> _ApiEnrichment:
    return _ApiEnrichment(
        isp="",
        country_code="",
        b_subnet="",
        as_type="",
        is_anonymous=False,
        is_hosting=False,
        is_proxy=False,
        is_vpn=False,
        is_tor=False,
        is_satellite=False,
    )


def _ip_enrichment_cache_key(ip: str) -> str:
    return f"ip_context_{ip}"


def _ip_context_cache_timeout() -> int:
    return int(getattr(settings, "TRACKER_IP_CONTEXT_CACHE_TIMEOUT", 21600))


def _get_cached_api_enrichment(ip: str) -> _ApiEnrichment | None:
    raw = cache.get(_ip_enrichment_cache_key(ip))
    if not isinstance(raw, dict):
        return None
    try:
        return _ApiEnrichment(**raw)
    except TypeError:
        return None


def _set_cached_api_enrichment(ip: str, enrichment: _ApiEnrichment) -> None:
    cache.set(
        _ip_enrichment_cache_key(ip),
        asdict(enrichment),
        _ip_context_cache_timeout(),
    )


def build_visitor_context(ip: str, user_agent_str: str) -> VisitorContext:
    """Assemble ``VisitorContext``; external IP enrichment is all-or-nothing on failure."""
    ua = user_agent_str or ""
    os_str, browser_str = _parse_user_agent(ua)
    hostname = _reverse_dns_hostname(ip)

    api = _get_cached_api_enrichment(ip)
    if api is None:
        fail_key = _enrichment_failure_cache_key(ip)
        if cache.get(fail_key):
            api = _empty_api_enrichment()
        else:
            try:
                api = _load_api_enrichment(ip)
            except Exception:
                cache.set(fail_key, 1, _ENRICHMENT_FAILURE_TTL_SEC)
                api = _empty_api_enrichment()
            else:
                cache.delete(fail_key)
                _set_cached_api_enrichment(ip, api)

    return VisitorContext(
        os=os_str,
        browser=browser_str,
        hostname=hostname,
        isp=api.isp,
        country_code=api.country_code,
        b_subnet=api.b_subnet,
        as_type=api.as_type,
        is_anonymous=api.is_anonymous,
        is_hosting=api.is_hosting,
        is_proxy=api.is_proxy,
        is_vpn=api.is_vpn,
        is_tor=api.is_tor,
        is_satellite=api.is_satellite,
    )
