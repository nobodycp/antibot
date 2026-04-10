from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('dashboard/', include('dashboard.urls')),  # بدون namespace
    path('tracker/', include('tracker.urls', namespace='tracker')),  # كل مسارات التتبع والحظر
    path('tools/', include('tools.urls', namespace='tools')),        # الأدوات مثل الفاحص ورفع الملفات
    path('accounts/', include('django.contrib.auth.urls')),          # تسجيل الدخول/الخروج من Django
]

# Local dev: DEBUG serves /media/. Production: use Nginx location /media/ → MEDIA_ROOT,
# or set DJANGO_SERVE_MEDIA=1 so uploads (avatars) are reachable without Nginx media.
if settings.DEBUG or getattr(settings, "SERVE_MEDIA", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
