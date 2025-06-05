from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('', include('dashboard.urls', namespace='dashboard')),  # الواجهة الرئيسية
    path('dashboard/', include('dashboard.urls', namespace='dashboard')),  # اختياري
    path('accounts/', include('django.contrib.auth.urls')),  # تسجيل الدخول
    path('', include('tracker.urls')),  # ← هذا هو اللي يرجّع api/log/
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
