from django.urls import path

from .views.file_views import uploader_files_view
from .views.google_safe_views import (
    google_safe_check_table_partial,
    google_safe_check_view,
)
from .views.redirect_views import redirect_check_table_view, redirect_check_view
from .views.rsa_decrypt_views import rsa_decrypt_view

app_name = 'tools'

urlpatterns = [
    path('upload-files/', uploader_files_view, name='uploader_files'),

    path('google-safe-check/', google_safe_check_view, name='google_safe_check'),
    path('google-safe-check/partial/', google_safe_check_table_partial, name='google_safe_check_table'),

    path('redirect-check/', redirect_check_view, name='redirect_check'),
    path('redirect-check/table/', redirect_check_table_view, name='redirect_check_table'),

    path('rsa-decrypt/', rsa_decrypt_view, name='rsa_decrypt'),

]
