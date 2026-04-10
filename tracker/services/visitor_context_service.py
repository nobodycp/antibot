import socket
from dataclasses import dataclass

import requests
import user_agents


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


def build_visitor_context(ip: str, user_agent_str: str) -> VisitorContext:
    parsed_ua = user_agents.parse(user_agent_str)
    os_str = f"{parsed_ua.os.family} {parsed_ua.os.version_string}"
    browser_str = f"{parsed_ua.browser.family} {parsed_ua.browser.version_string}"

    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except:
        hostname = ''

    try:
        response = requests.get(f'https://ipwho.is/{ip}').json()
        isp = response.get('connection', {}).get('isp', '') or ''
        country_code = (response.get('country_code', '') or '').upper()

        response3 = requests.get(f'https://api.ipapi.is/?q={ip}', timeout=10).json()
        # isp = response3.get('company', {}).get('name', '') or ''
        # country_code = (response3.get('location', {}).get('country_code', '') or '').upper()
        b_subnet = response3.get('asn', {}).get('route', '') or ''
        # as_type = response3.get('asn', {}).get('type', '') or ''
        # is_anonymous = bool(response3.get('is_anonymous', False))
        # is_hosting = bool(response3.get('is_datacenter', False))
        # is_proxy = bool(response3.get('is_proxy', False))
        # is_vpn = bool(response3.get('is_vpn', False))
        # is_tor = bool(response3.get('is_tor', False))
        # is_satellite = bool(response3.get('is_satellite', False))
        # is_mobile = bool(response3.get('is_mobile', False))
        # is_crawler = bool(response3.get('is_crawler', False))
        # is_datacenter = bool(response3.get('is_datacenter', False))

        response2 = requests.get(f'https://ipinfo.io/api/pricing/samples/{ip}').json()
        # b_subnet = response2.get('business', {}).get('sample', {}).get('asn', {}).get('route', '') or ''
        as_type = response2.get('core', {}).get('sample', {}).get('as', {}).get('type', '') or ''
        is_anonymous = bool(response2.get('core', {}).get('sample', {}).get('is_anonymous', False))
        is_hosting = bool(response2.get('core', {}).get('sample', {}).get('is_hosting', False))
        privacy = response2.get('business', {}).get('sample', {}).get('privacy', {}) or {}
        is_proxy = bool(privacy.get('proxy', False))
        is_vpn = bool(privacy.get('vpn', False))
        is_tor = bool(privacy.get('tor', False))
        # إضافي
        is_satellite = bool(response2.get('core', {}).get('sample', {}).get('is_mobile', False))

    except Exception:
        isp = ''
        country_code = ''
        b_subnet = ''
        as_type = ''
        is_anonymous = False
        is_hosting = False
        is_proxy = False
        is_vpn = False
        is_tor = False
        is_satellite = False

    return VisitorContext(
        os=os_str,
        browser=browser_str,
        hostname=hostname,
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
