from django.urls import path

from .views.file_views import uploader_files_view
from .views.google_safe_views import (
    google_safe_check_table_partial,
    google_safe_check_view,
)
from .views.redirect_views import redirect_check_table_view, redirect_check_view
from .views.cloud_sync_views import (
    cloud_sync_domain_sync,
    cloud_sync_start,
    cloud_sync_status_partial,
    cloud_sync_view,
)
from .views.cloudflare_domains_views import (
    cloudflare_domain_add,
    cloudflare_domain_delete,
    cloudflare_domain_sync,
    cloudflare_domain_toggle,
    cloudflare_domain_update,
    cloudflare_domains_view,
)
from .views.rsa_decrypt_views import rsa_decrypt_view
from .views.whatsapp_views import (
    whatsapp_accounts_status_partial,
    whatsapp_check_status_partial,
    whatsapp_check_view,
    whatsapp_pairing_status_partial,
)

app_name = 'tools'

urlpatterns = [
    path('upload-files/', uploader_files_view, name='uploader_files'),

    path('google-safe-check/', google_safe_check_view, name='google_safe_check'),
    path('google-safe-check/partial/', google_safe_check_table_partial, name='google_safe_check_table'),

    path('redirect-check/', redirect_check_view, name='redirect_check'),
    path('redirect-check/table/', redirect_check_table_view, name='redirect_check_table'),

    path('rsa-decrypt/', rsa_decrypt_view, name='rsa_decrypt'),

    path('cloudflare-domains/', cloudflare_domains_view, name='cloudflare_domains'),
    path(
        'cloudflare-domains/add/',
        cloudflare_domain_add,
        name='cloudflare_domain_add',
    ),
    path(
        'cloudflare-domains/<int:domain_id>/delete/',
        cloudflare_domain_delete,
        name='cloudflare_domain_delete',
    ),
    path(
        'cloudflare-domains/<int:domain_id>/toggle/',
        cloudflare_domain_toggle,
        name='cloudflare_domain_toggle',
    ),
    path(
        'cloudflare-domains/<int:domain_id>/update/',
        cloudflare_domain_update,
        name='cloudflare_domain_update',
    ),
    path(
        'cloudflare-domains/<int:domain_id>/sync/',
        cloudflare_domain_sync,
        name='cloudflare_domain_sync',
    ),

    path('cloud-sync/', cloud_sync_view, name='cloud_sync'),
    path('cloud-sync/start/', cloud_sync_start, name='cloud_sync_start'),
    path(
        'cloud-sync/<int:domain_id>/sync/',
        cloud_sync_domain_sync,
        name='cloud_sync_domain_sync',
    ),
    path('cloud-sync/status/', cloud_sync_status_partial, name='cloud_sync_status'),

    path('whatsapp-check/', whatsapp_check_view, name='whatsapp_check'),
    path(
        'whatsapp-check/accounts/status/',
        whatsapp_accounts_status_partial,
        name='whatsapp_accounts_status',
    ),
    path(
        'whatsapp-check/jobs/<int:job_id>/status/',
        whatsapp_check_status_partial,
        name='whatsapp_check_status',
    ),
    path(
        'whatsapp-check/accounts/<str:account_name>/pairing/',
        whatsapp_pairing_status_partial,
        name='whatsapp_pairing_status',
    ),

]
