import json

with open('Bad_IPs.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for d in data:
    print(d)