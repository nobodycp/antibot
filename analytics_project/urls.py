import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path
from django.views.static import serve

from core.health import health

urlpatterns = [
    path("health/", health, name="health"),
    path('dashboard/', include('dashboard.urls')),  # بدون namespace
    path('tracker/', include('tracker.urls', namespace='tracker')),  # كل مسارات التتبع والحظر
    path('tools/', include('tools.urls', namespace='tools')),        # الأدوات مثل الفاحص ورفع الملفات
    path('accounts/', include('django.contrib.auth.urls')),          # تسجيل الدخول/الخروج من Django
]

# DEBUG: django.conf.urls.static.static() mounts /media/.
# Production + DJANGO_SERVE_MEDIA=1: static() is a no-op when DEBUG=False (Django design),
# so we mount the same URL with django.views.static.serve explicitly.
_serve_media = getattr(settings, "SERVE_MEDIA", False)
if settings.DEBUG:
    # خدمة /static/ من مجلدات التطبيقات (مثل dashboard/static/...) عبر staticfiles.
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Fallback إذا تعطّل WhiteNoise أو طُلب الملف قبل اكتمال الـ middleware: خدمة من STATIC_ROOT
    _static_prefix = settings.STATIC_URL.lstrip("/")
    if _static_prefix:
        urlpatterns += [
            re_path(
                r"^%s(?P<path>.*)$" % re.escape(_static_prefix),
                serve,
                {"document_root": str(settings.STATIC_ROOT)},
            ),
        ]
    if _serve_media:
        _media_prefix = settings.MEDIA_URL.lstrip("/")
        if _media_prefix:
            urlpatterns += [
                re_path(
                    r"^%s(?P<path>.*)$" % re.escape(_media_prefix),
                    serve,
                    {"document_root": settings.MEDIA_ROOT},
                ),
            ]
