from . import views
from django.urls import path
from tracker.views import (
    blocked_ips_view, blocked_ips_table, blocked_ips_partial,
    blocked_isp_view, blocked_isp_table, blocked_isp_partial,
    blocked_os_view, allowed_logs_view,
    allowed_logs_table, denied_logs_view, denied_logs_table,
    allowed_country_view, blocked_hostname_view, dinger_ip_view,
    delete_log,blocked_browser_view, blocked_browser_partial, blocked_browser_table, blocked_os_table, blocked_os_partial
)
from uploader.views import uploader_files_view


app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('blocked-ips/', blocked_ips_view, name='blocked_ips'),
    path('blocked-ips/table/', blocked_ips_table, name='blocked_ips_table'),
    path('blocked-ips/partial/', blocked_ips_partial, name='blocked_ips_partial'),
    #
    path('blocked-isp/', blocked_isp_view, name='blocked_isp'),
    path("blocked-isps/partial/", blocked_isp_partial, name="blocked_isp_partial"),
    path("blocked-isps/table/", blocked_isp_table, name="blocked_isp_table"),
    #
    path('blocked-browser/', blocked_browser_view, name='blocked_browser'),
    path("blocked-browsers/partial/", blocked_browser_partial, name="blocked_browser_partial"),
    path("blocked-browsers/table/", blocked_browser_table, name="blocked_browser_table"),
    #
    path('blocked-os/', blocked_os_view, name='blocked_os'),
    path('blocked-os-table/', blocked_os_table, name='blocked_os_table'),
    path('blocked-os-partial/', blocked_os_partial, name='blocked_os_partial'),


    #
    path('allowed-country/', allowed_country_view, name='allowed_country'),
    #
    path('blocked-hostname/', blocked_hostname_view, name='blocked_hostname'),
    #
    path('allowed-logs/', allowed_logs_view, name='allowed_logs'),
    path('allowed-logs/table/', allowed_logs_table, name='allowed_logs_table'),
    path("allowed-logs/delete/<int:pk>/", delete_log, name="delete_log"),
    #
    path('denied-logs/', denied_logs_view, name='denied_logs'),
    path('denied-logs/table/', denied_logs_table, name='denied_logs_table'),
    #
    path('dinger-ip/', dinger_ip_view, name='dinger_ip'),
    #
    path('upload-files/', uploader_files_view, name='uploader_files'),
    #
]
