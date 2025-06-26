from django.urls import path
from .views import (
    uploader_files_view,
    google_safe_check_view,
    google_safe_check_table_partial,
    redirect_check_view,
    redirect_check_table_view,
)

app_name = 'tools'

urlpatterns = [
    path('upload-files/', uploader_files_view, name='uploader_files'),

    path('google-safe-check/', google_safe_check_view, name='google_safe_check'),
    path('google-safe-check/partial/', google_safe_check_table_partial, name='google_safe_check_table'),

    path('redirect-check/', redirect_check_view, name='redirect_check'),
    path('redirect-check/table/', redirect_check_table_view, name='redirect_check_table'),
]
