# import json
#
# with open('Blacklist_ISP.json', 'r', encoding='utf-8') as f:
#     data = json.load(f)
#
# for d in data:
#     print(f"{d['isp']}")

import requests

ip = '136.118.135.192'

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

