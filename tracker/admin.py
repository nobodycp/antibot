from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import localtime
from django.utils.timesince import timesince
from .models import (
    Visitor, IPLog,
    BlockedIP, BlockedHostname, BlockedISP, BlockedOS, BlockedBrowser, AllowedCountry, RejectedVisitor
)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp_ago', 'ip_address', 'isp', 'hostname', 'os',  'browser', 'country',
         'delete_link'
    )
    ordering = ('-timestamp',)

    def timestamp_ago(self, obj):
        ago = timesince(obj.timestamp) + " ago"
        full_time = localtime(obj.timestamp).strftime("%b %d, %Y - %I:%M %p")
        return format_html('<span title="{}">{}</span>', full_time, ago)
    timestamp_ago.short_description = "log time"

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/visitor/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        blocked_ips = BlockedIP.objects.values_list('ip_address', flat=True)
        blocked_hostnames = BlockedHostname.objects.values_list('hostname', flat=True)
        blocked_os = BlockedOS.objects.values_list('os', flat=True)
        blocked_browsers = BlockedBrowser.objects.values_list('browser', flat=True)
        blocked_isps = BlockedISP.objects.values_list('isp', flat=True)

        return qs.exclude(ip_address__in=blocked_ips) \
                 .exclude(hostname__in=blocked_hostnames) \
                 .exclude(os__in=blocked_os) \
                 .exclude(browser__in=blocked_browsers) \
                 .exclude(isp__in=blocked_isps)
@admin.register(RejectedVisitor)
class RejectedVisitorAdmin(admin.ModelAdmin):
    list_display = (
        'timestamp_ago', 'ip_address', 'reason', 'isp', 'country', 'os', 'browser',
         'hostname', 'delete_link'
    )
    ordering = ('-timestamp',)

    def get_queryset(self, request):
        qs = super().get_queryset(request).order_by('-timestamp')
        unique_ips = {}
        for obj in qs:
            if obj.ip_address not in unique_ips:
                unique_ips[obj.ip_address] = obj.id
        return qs.filter(id__in=unique_ips.values())

    def timestamp_ago(self, obj):
        return timesince(obj.timestamp) + " ago"
    timestamp_ago.short_description = "log time"

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/rejectedvisitor/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"


@admin.register(BlockedIP)
class BlockedIPAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'delete_link')

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/blockedip/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"


@admin.register(BlockedHostname)
class BlockedHostnameAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'delete_link')

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/blockedhostname/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"


@admin.register(BlockedISP)
class BlockedISPAdmin(admin.ModelAdmin):
    list_display = ('isp', 'delete_link')

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/blockedisp/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"


@admin.register(BlockedOS)
class BlockedOSAdmin(admin.ModelAdmin):
    list_display = ('os', 'delete_link')

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/blockedos/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"


@admin.register(BlockedBrowser)
class BlockedBrowserAdmin(admin.ModelAdmin):
    list_display = ('browser', 'delete_link')

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/blockedbrowser/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )
    delete_link.short_description = "Delete"


@admin.register(IPLog)
class IPLogAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'count')
    ordering = ('-count',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(count__gte=10)


@admin.register(AllowedCountry)
class AllowedCountryAdmin(admin.ModelAdmin):
    list_display = ('name', 'delete_link')

    def delete_link(self, obj):
        return format_html(
            '<a href="/admin/tracker/allowedcountry/{}/delete/" '
            'style="color: white; background-color: red; padding: 4px 8px; border-radius: 4px; text-decoration: none;">Delete</a>',
            obj.id
        )

    delete_link.short_description = "Delete"
