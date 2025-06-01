from django import template
from django.utils.text import slugify as django_slugify

register = template.Library()

@register.filter
def slugify_filter(value):
    return django_slugify(value)

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
    "edge": "edge"
}

@register.filter
def icon_name(value):
    if not value:
        return "unknown"
    name = value.lower().split(" ")[0]  # يلتقط أول كلمة فقط مثل "Chrome"
    return ICON_OVERRIDES.get(name, slugify(name))
