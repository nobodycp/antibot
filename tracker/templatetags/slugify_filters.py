from django import template
from django.utils.text import slugify

register = template.Library()

# تعيين أسماء أيقونات مخصصة
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
    "yandex": "yandex",  # ← مضافة حديثاً

}


@register.filter
def icon_name(value):
    """
    يحلل user agent أو أي وصف، ويرجع اسم أيقونة مناسب.
    """
    if not value:
        return "unknown"

    value = value.lower()
    for keyword in ICON_OVERRIDES:
        if keyword in value:
            return ICON_OVERRIDES[keyword]

    return slugify(value.split(" ")[0])  # fallback

@register.filter
def slugify_filter(value):
    """
    يحول النص إلى slug صالح للاستخدام كـ class أو اسم ملف.
    """
    return slugify(value)
