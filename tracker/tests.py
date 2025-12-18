import requests
ip = '5.29.87.1'
response2 = requests.get(f'https://ipinfo.io/api/pricing/samples/{ip}').json()
b_subnet = response2['business']['sample']['asn']['route']
print(b_subnet)