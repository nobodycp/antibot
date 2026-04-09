import json

with open('rejected_remaining.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

subnets = set()

for item in data:
    fields = item.get('fields', {})
    subnet = fields.get('b_subnet', '').strip()

    if subnet:
        subnets.add(subnet)

# حفظ TXT
with open('remaining_subnets.txt', 'w', encoding='utf-8') as f:
    for s in sorted(subnets):
        f.write(s + '\n')

print(f"Total subnets: {len(subnets)}")