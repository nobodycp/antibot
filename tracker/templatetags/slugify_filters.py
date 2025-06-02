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
    "chrome": "chrome",
    "firefox": "firefox",
    "safari": "safari",
    "opera": "opera",
    "edge": "edge",
    "yandex": "yandex",
}

@register.filter
def icon_name(value):
    """
    يرجع اسم الأيقونة المطابق إذا وُجدت كلمة كاملة مثل 'chrome' داخل السلسلة.
    """
    if not value:
        return "unknown"

    value = value.lower()

    for keyword in ICON_OVERRIDES:
        if re.search(rf'\b{re.escape(keyword)}\b', value):
            return ICON_OVERRIDES[keyword]

    return slugify(value.split(" ")[0])  # fallback: أول كلمة


@register.filter
def slugify_filter(value):
    """
    يحول النص إلى slug صالح للاستخدام كـ class أو اسم ملف.
    """
    return slugify(value)
