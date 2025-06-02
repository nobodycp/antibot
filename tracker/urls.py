from django.urls import path
from .views import LogVisitorAPIView
from .views import dashboard_view,blocked_ips_partial, blocked_ips_table, dinger_ip_view, delete_log, denied_logs_table, denied_logs_view, allowed_logs_table, home_redirect, blocked_ips_view, blocked_isp_view, blocked_os_view, blocked_browser_view,allowed_logs_view, allowed_country_view, blocked_hostname_view
from uploader.views import uploader_files_view

urlpatterns = [
    path('api/log/', LogVisitorAPIView.as_view(), name='log-visitor'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('', home_redirect),  # يحوّل / إلى /dashboard/
    path('dashboard/blocked-ips/', blocked_ips_view, name='blocked_ips'),
    path('dashboard/blocked-ips/table/', blocked_ips_table, name='blocked_ips_table'),
    path('dashboard/blocked-ips/partial/', blocked_ips_partial, name='blocked_ips_partial'),

    path('dashboard/blocked-isp/', blocked_isp_view, name='blocked_isp'),
    path('dashboard/blocked-os/', blocked_os_view, name='blocked_os'),
    path('dashboard/blocked-browser/', blocked_browser_view, name='blocked_browser'),
    path('dashboard/allowed-country/', allowed_country_view, name='allowed_country'),
    path('dashboard/blocked-hostname/', blocked_hostname_view, name='blocked_hostname'),
    path('dashboard/allowed-logs/', allowed_logs_view, name='allowed_logs'),
    path('dashboard/allowed-logs/table/', allowed_logs_table, name='allowed_logs_table'),
    path("dashboard/allowed-logs/delete/<int:pk>/", delete_log, name="delete_log"),
    path('dashboard/denied-logs/', denied_logs_view, name='denied_logs'),
    path('dashboard/denied-logs/table/', denied_logs_table, name='denied_logs_table'),
    path('dashboard/dinger-ip/', dinger_ip_view, name='dinger_ip'),
    path('dashboard/upload-files/', uploader_files_view, name='uploader_files'),

]