import requests
ip = '8.8.8.8'
response2 = requests.get(f'https://ipinfo.io/api/pricing/samples/{ip}').json()
b_subnet = response2['business']['sample']['asn']['route']
as_type = response2['core']['sample']['as']['type']
is_anonymous = response2['core']['sample']['is_anonymous']
is_hosting = response2['core']['sample']['is_hosting']
is_proxy = response2['business']['sample']['privacy']['proxy']
is_vpn = response2['business']['sample']['privacy']['vpn']
is_tor = response2['business']['sample']['privacy']['tor']

print(is_tor)
# print(b_subnet)