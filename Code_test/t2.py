import json

with open('rejected_updated.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

subnets = set()
remaining_data = []

for item in data:
    fields = item.get('fields', {})
    reason = fields.get('reason', '')
    subnet = fields.get('b_subnet', '').strip()

    if reason == 'ISP':
        if subnet:
            subnets.add(subnet)
    else:
        remaining_data.append(item)

# حفظ TXT للـ ISP
with open('isp_subnets.txt', 'w', encoding='utf-8') as f:
    for s in sorted(subnets):
        f.write(s + '\n')

# حفظ باقي البيانات JSON
with open('rejected_remaining.json', 'w', encoding='utf-8') as f:
    json.dump(remaining_data, f, ensure_ascii=False, indent=2)

print(f"Subnets: {len(subnets)}")
print(f"Remaining: {len(remaining_data)}")