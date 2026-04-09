import json
import requests
import time

def get_sub(ip):
    try:
        response = requests.get(f'https://api.ipapi.is/?q={ip}', timeout=10).json()
        return response.get('asn', {}).get('route', '') or ''
    except:
        return ''

with open('rejected.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

updated = 0
skipped = 0

for info in data:
    # إذا ما فيه subnet
    if not info['fields'].get('b_subnet'):
        ip = info['fields']['ip_address']
        subnet = get_sub(ip)

        if subnet:
            info['fields']['b_subnet'] = subnet  # ✅ تعديل مباشر
            updated += 1
            print(f"✔ {ip} → {subnet}")
        else:
            skipped += 1
            print(f"✖ {ip} no subnet")

        time.sleep(0.3)  # عشان ما ينحظر API
    else:
        continue  # اتركه زي ما هو

print(f"\nUpdated: {updated} | Skipped: {skipped}")

# حفظ كل الداتا (قديمة + المعدلة)
with open('rejected_updated.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)