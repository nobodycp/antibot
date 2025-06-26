from django.urls import path
from .views import (
    LogVisitorAPIView,
    blocked_ips_view, blocked_ips_table, blocked_ips_partial,
    blocked_isp_view, blocked_isp_table, blocked_isp_partial,
    blocked_browser_view, blocked_browser_table, blocked_browser_partial,
    blocked_os_view, blocked_os_table, blocked_os_partial,
    blocked_hostname_view, blocked_hostname_table, blocked_hostname_partial,
    allowed_country_view, allowed_country_table, allowed_country_partial,
    allowed_logs_view, allowed_logs_table, allowed_logs_partial,
    denied_logs_view, denied_logs_table, denied_logs_partial,
    dinger_ip_view,
    add_block_rule,
)

app_name = 'tracker'

urlpatterns = [
    path('api/log/', LogVisitorAPIView.as_view(), name='log_visitor'),

    path('blocked-ips/', blocked_ips_view, name='blocked_ips'),
    path('blocked-ips/table/', blocked_ips_table, name='blocked_ips_table'),
    path('blocked-ips/partial/', blocked_ips_partial, name='blocked_ips_partial'),

    path('blocked-isp/', blocked_isp_view, name='blocked_isp'),
    path("blocked-isps/partial/", blocked_isp_partial, name="blocked_isp_partial"),
    path("blocked-isps/table/", blocked_isp_table, name="blocked_isp_table"),

    path('blocked-browser/', blocked_browser_view, name='blocked_browser'),
    path("blocked-browsers/partial/", blocked_browser_partial, name="blocked_browser_partial"),
    path("blocked-browsers/table/", blocked_browser_table, name="blocked_browser_table"),

    path('blocked-os/', blocked_os_view, name='blocked_os'),
    path('blocked-os-table/', blocked_os_table, name='blocked_os_table'),
    path('blocked-os-partial/', blocked_os_partial, name='blocked_os_partial'),

    path('blocked-hostname/', blocked_hostname_view, name='blocked_hostname'),
    path('blocked-hostname-table/', blocked_hostname_table, name='blocked_hostname_table'),
    path('blocked-hostname-partial/', blocked_hostname_partial, name='blocked_hostname_partial'),

    path('allowed-country/', allowed_country_view, name='allowed_country'),
    path('allowed-country-table/', allowed_country_table, name='allowed_country_table'),
    path('allowed-country-partial/', allowed_country_partial, name='allowed_country_partial'),

    path('allowed-logs/', allowed_logs_view, name='allowed_logs'),
    path('allowed-logs-table/', allowed_logs_table, name='allowed_logs_table'),
    path('allowed-logs-partial/', allowed_logs_partial, name='allowed_logs_partial'),

    path("denied-logs/", denied_logs_view, name="denied_logs"),
    path("denied-logs-partial/", denied_logs_partial, name="denied_logs_partial"),
    path("denied-logs-table/", denied_logs_table, name="denied_logs_table"),
    path("denied-logs/add-rule/", add_block_rule, name="add_block_rule"),

    path('dinger-ip/', dinger_ip_view, name='dinger_ip'),
]
