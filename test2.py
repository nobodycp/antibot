import json

with open('Blacklist_ISP.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for d in data:
    print(f"{d['isp']}")