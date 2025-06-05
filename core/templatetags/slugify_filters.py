import re
from django import template
from django.utils.text import slugify

register = template.Library()

ICON_OVERRIDES = {
    "mac": "macos",
    "windows": "windows",
    "ubuntu": "ubuntu",
    "android": "android",
    "ios": "ios",
    "linux": "linux",
    "chrome os": "chrome-os",   # ← أضفناها الآن
    "chrome": "chrome",
    "firefox": "firefox",
    "safari": "safari",
    "opera": "opera",
    "edge": "edge",
    "yandex": "yandex",
    "samsung": "samsung-internet",
    "samsung internet": "samsung-internet",
}

@register.filter
def icon_name(value):
    """
    يرجع اسم الأيقونة المناسبة من user-agent أو يعيد 'unknown' إذا ما تم التطابق.
    """
    if not value:
        return "unknown"

    value = value.lower().strip()

    # لو كان 'other' مباشرة
    if value == "other":
        return "unknown"

    # تطابق مع الكلمات والعبارات المسجلة
    for keyword in sorted(ICON_OVERRIDES, key=len, reverse=True):
        if re.search(rf'\b{re.escape(keyword)}\b', value):
            return ICON_OVERRIDES[keyword]

    return "unknown"  # fallback صريح


@register.filter
def slugify_filter(value):
    """
    يحول النص إلى slug صالح للاستخدام كـ class أو اسم ملف.
    """
    return slugify(value)
