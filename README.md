# AntiBot

منصة **Django** لمراقبة الزوار، تطبيق قواعد الحظر (IP، شبكات فرعية، ISP، متصفح، نظام تشغيل، hostname)، وتسجيل الزيارات المسموحة والمرفوضة مع لوحة تحكم وواجهة برمجية بسيطة لدمجها مع مواقعك أو بواباتك.

---

## ما الفائدة؟ ولأي سيناريوهات؟

| الاستخدام | الوصف |
|-----------|--------|
| **حماية من البوتات والزيارات غير المرغوبة** | تقييم الطلب وفق IP ووكيل المستخدم (User-Agent) وقواعدك المخزنة في قاعدة البيانات. |
| **سياسات دولة مسموحة** | قائمة دول مسموحة (`AllowedCountry`) تُدمج في قرار السماح أو الرفض. |
| **سجلات وتحليل** | صفحات للزيارات المسموحة/المرفوضة، معلومات IP، وإضافة قواعد حظر من السجلات. |
| **لوحة تحكم** | إحصائيات، إدارة مستخدمين، إعدادات الملف الشخصي، ونسخ احتياطي عبر Telegram (حسب الإعداد). |
| **أدوات مساعدة** | رفع ملفات، فحص Google Safe Browsing، وفحص إعادة التوجيه. |

**نقطة الدمج الأساسية للموقع الخارجي:** `POST /tracker/api/log/` — ترسل منها عنوان IP وسلسلة User-Agent؛ الاستجابة توضح السماح (`201`) أو الرفض (`403`) مع سبب مقروء.

---

## المتطلبات

- **Python 3.9+** (متوافق مع إصدارات Django المستخدمة في `requirements.txt`)
- **قاعدة بيانات:** SQLite افتراضياً (مناسبة للتطوير؛ للإنتاج يُفضّل PostgreSQL مع تعديل الإعدادات)

---

## التثبيت على الخادم (الموصى به) — `install.sh`

المستودع يتضمن **`install.sh`** لنشر تلقائي على **Debian/Ubuntu**: تثبيت الحزم، استنساخ المشروع إلى `/opt/antibot`، بيئة افتراضية `env`، `migrate`، مستخدم مشرف، خدمة **systemd** تشغّل `runserver` على `0.0.0.0:8000`، ومهمة **cron** لأمر النسخ الاحتياطي عبر Telegram.

من جهازك (بعد استنساخ المستودع):

```bash
git clone https://github.com/nobodycp/antibot.git
cd antibot
sudo bash install.sh
```

(السكربت ينشئ `/opt/antibot` إن لزم قبل كتابة ملف التثبيت الداخلي.)

**ماذا يحدث داخلياً؟**

1. يضمن وجود `/opt/antibot`، يكتب السكربت «الحقيقي» إلى `/opt/antibot/install.sh` ثم ينفّذه.
2. يوقف خدمة `antibot` القديمة إن وُجدت، **يحذف** مجلد `/opt/antibot` بالكامل، ثم يستنسخ المستودع من جديد (لا تعتمد على تعديلات يدوية داخل `/opt` دون نسخها إلى Git).
3. ينشئ `venv` في `/opt/antibot/env` ويثبّت `requirements.txt`.
4. يشغّل `migrate` و`createsuperuser` بقيم افتراضية داخل السكربت (`admin` / `adminpass` — **غيّرها فوراً** من لوحة الإدارة أو من Django).
5. يفعّل خدمة systemd ويعرض حالة التشغيل.

بعدها: **لوحة التحكم** على `http://<عنوان-الخادم>:8000/dashboard/` وتسجيل الدخول على `/accounts/login/`.

> للإنتاج الثقيل يُفضّل لاحقاً استبدال `runserver` بـ **Gunicorn/uWSGI** خلف **Nginx** وتعطيل `DEBUG` وضبط `SECRET_KEY` عبر `.env` (انظر `.env.example`).

---

## التطوير المحلي (بدون `install.sh`)

إذا كنت تطوّر على macOS أو Windows، أو لا تريد systemd و`/opt/`:

```bash
git clone https://github.com/nobodycp/antibot.git
cd antibot

python3 -m venv .venv
source .venv/bin/activate          # على Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- [http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)
- [http://127.0.0.1:8000/accounts/login/](http://127.0.0.1:8000/accounts/login/)

الإعدادات الافتراضية: `analytics_project.settings` (بيئة `dev`). المتغيرات الحساسة في `.env`.

---

## المسارات (Endpoints) — نظرة عامة

الجذر النسبي هنا يفترض تشغيل المشروع على نطاقك بدون بادئة إضافية (مثل `https://example.com`). استبدل النطاق حسب نشرك.

### واجهة برمجية (API)

| الطريقة | المسار | الوصف |
|--------|--------|--------|
| `POST` | `/tracker/api/log/` | يرسل JSON: `ip` و `useragent`. يُرجع `access_granted` أو `access_denied` مع سبب عند الرفض. |

**مثال طلب:**

```bash
curl -s -X POST http://127.0.0.1:8000/tracker/api/log/ \
  -H "Content-Type: application/json" \
  -d '{"ip":"203.0.113.10","useragent":"Mozilla/5.0 ..."}'
```

### المصادقة (Django)

| المسار | الوصف |
|--------|--------|
| `/accounts/login/` | تسجيل الدخول |
| `/accounts/logout/` | تسجيل الخروج |
| `/accounts/password_change/` | تغيير كلمة المرور (للمستخدم المسجّل) |

> بقية مسارات `django.contrib.auth.urls` متاحة تحت `/accounts/`.

### لوحة التحكم — `dashboard`

| المسار | الوصف |
|--------|--------|
| `/dashboard/` | الصفحة الرئيسية للوحة |
| `/dashboard/home/stats/` | جزئية إحصائيات (HTMX) |
| `/dashboard/home/secondary-stats/` | إحصائيات ثانوية |
| `/dashboard/home/alerts/` | التنبيهات |
| `/dashboard/home/latest-logs/` | آخر السجلات |
| `/dashboard/home/top-ips/` | أعلى الـ IPs |
| `/dashboard/users/` | إدارة المستخدمين |
| `/dashboard/users/add/` | إضافة مستخدم |
| `/dashboard/users/edit/<id>/` | تعديل مستخدم |
| `/dashboard/users/delete/<id>/` | حذف مستخدم |
| `/dashboard/profile-settings/` | إعدادات الملف الشخصي |
| `/dashboard/telegram-backup-settings/` | إعداد نسخ Telegram |
| `/dashboard/telegram-test/` | اختبار Telegram |
| `/dashboard/telegram-send-db-backup/` | إرسال نسخة قاعدة البيانات |

### التتبع والحظر — `tracker`

| المسار | الوصف |
|--------|--------|
| `/tracker/blocked-ips/` | قواعد حظر عناوين IP |
| `/tracker/blocked-subnets/` | حظر الشبكات الفرعية |
| `/tracker/blocked-isp/` | حظر مزوّدي خدمة (ISP) |
| `/tracker/blocked-browser/` | حظر متصفحات |
| `/tracker/blocked-os/` | حظر أنظمة تشغيل |
| `/tracker/blocked-hostname/` | حظر أسماء مضيف (hostname) |
| `/tracker/allowed-country/` | الدول المسموحة |
| `/tracker/allowed-logs/` | سجل الزيارات المسموحة |
| `/tracker/denied-logs/` | سجل الزيارات المرفوضة (+ إضافة قاعدة حظر) |
| `/tracker/ip-info/` | معلومات وتفاصيل IP (+ إضافة قاعدة حظر) |
| `/tracker/dinger-ip/` | IPs ذات تكرار زيارة عالٍ (`count > 10`) مع إمكانية حذف السجلات من `IPLog` |

**جزئيات الجداول (للتحديث عبر HTMX)** — لكل صفحة أعلاه توجد مسارات فرعية مثل `.../table/` و `.../partial/` أو أسماء مشابهة (مثال: `blocked-isps/partial/` لصفحة ISP). تُستخدم من القوالب وليست عادةً نقاط دخول يدوية.

### الأدوات — `tools`

| المسار | الوصف |
|--------|--------|
| `/tools/upload-files/` | رفع الملفات |
| `/tools/google-safe-check/` | فحص Google Safe Browsing |
| `/tools/google-safe-check/partial/` | جدول النتائج (جزئي) |
| `/tools/redirect-check/` | فحص إعادة التوجيه |
| `/tools/redirect-check/table/` | جدول إعادة التوجيه (جزئي) |

---

## الاختبارات

```bash
source .venv/bin/activate
python manage.py test tracker.tests
```

---

## الترخيص والمساهمة

راجع ملفات المستودع للترخيص إن وُجدت. للمساهمات: فروع منفصلة وطلبات دمج واضحة تسهّل المراجعة.
