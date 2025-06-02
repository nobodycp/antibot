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
}

@register.filter
def icon_name(value):
    """
    يستخرج اسم الأيقونة المناسب من أول كلمة في قيمة المتصفح أو النظام.
    """
    if not value:
        return "unknown"
    name = value.lower().split(" ")[0]  # التقاط أول كلمة فقط
    return ICON_OVERRIDES.get(name, slugify(name))  # استخدام override أو slugify تلقائي

@register.filter
def slugify_filter(value):
    """
    يحول النص إلى slug صالح للاستخدام كـ class أو اسم ملف.
    """
    return slugify(value)
