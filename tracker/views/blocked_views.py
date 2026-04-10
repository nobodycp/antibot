import ipaddress

from django.contrib import messages
from core.decorators import superuser_required

from ..models import (
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
    BlockedSubnet,
)
from .list_flow import (
    blocked_after_post_htmx_or_redirect,
    blocked_render_full_page,
    blocked_render_partial,
    blocked_render_table,
)


@superuser_required
def blocked_subnets_view(request):
    if request.method == 'POST':
        cidr = request.POST.get('cidr')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if cidr:
            cidr = cidr.strip()
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                cidr_norm = str(net)
            except ValueError:
                cidr_norm = None

            if not cidr_norm:
                messages.error(request, "❌ Invalid CIDR. Example: 192.168.1.0/24")
            else:
                if not BlockedSubnet.objects.filter(cidr=cidr_norm).exists():
                    BlockedSubnet.objects.create(cidr=cidr_norm)
                    messages.success(request, f"✅ Subnet {cidr_norm} added successfully.")
                else:
                    messages.warning(request, f"⚠️ Subnet {cidr_norm} already exists.")

        elif delete_id:
            try:
                obj = BlockedSubnet.objects.get(id=delete_id)
                messages.error(request, f"🗑️ Subnet {obj.cidr} deleted.")
                obj.delete()
            except BlockedSubnet.DoesNotExist:
                messages.error(request, "❌ Subnet not found.")

        elif delete_all:
            count = BlockedSubnet.objects.count()
            BlockedSubnet.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} Subnet(s).")
        else:
            messages.error(request, "Invalid action.")

        return blocked_after_post_htmx_or_redirect(
            request,
            ordered_qs=BlockedSubnet.objects.all().order_by('-id'),
            search_field="cidr",
            list_key="blocked_subnets",
            partial_template="tracker/partials/blocked_subnets_partial.html",
            redirect_to="tracker:blocked_subnets",
        )

    return blocked_render_full_page(
        request,
        ordered_qs=BlockedSubnet.objects.all().order_by('-id'),
        search_field="cidr",
        list_key="blocked_subnets",
        template="tracker/blocked_subnets.html",
    )


@superuser_required
def blocked_subnets_partial(request):
    return blocked_render_partial(
        request,
        ordered_qs=BlockedSubnet.objects.all().order_by('-id'),
        search_field="cidr",
        list_key="blocked_subnets",
        partial_template="tracker/partials/blocked_subnets_partial.html",
    )


@superuser_required
def blocked_subnets_table(request):
    return blocked_render_table(
        request,
        ordered_qs=BlockedSubnet.objects.all().order_by('-id'),
        search_field="cidr",
        list_key="blocked_subnets",
        table_template="tracker/partials/blocked_subnets_table.html",
        table_only=False,
    )


######################################################################
@superuser_required
def blocked_ips_view(request):
    if request.method == 'POST':
        ip = request.POST.get('ip_address')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if ip:
            ip = ip.strip()
            if not BlockedIP.objects.filter(ip_address=ip).exists():
                BlockedIP.objects.create(ip_address=ip)
                messages.success(request, f"✅ IP {ip} added successfully.")
            else:
                messages.warning(request, f"⚠️ IP {ip} already exists.")
        elif delete_id:
            try:
                obj = BlockedIP.objects.get(id=delete_id)
                messages.error(request, f"🗑️ IP {obj.ip_address} deleted.")
                obj.delete()
            except BlockedIP.DoesNotExist:
                messages.error(request, "❌ IP not found.")
        elif delete_all:
            count = BlockedIP.objects.count()
            BlockedIP.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} IP(s).")
        else:
            messages.error(request, "Invalid action.")

        return blocked_after_post_htmx_or_redirect(
            request,
            ordered_qs=BlockedIP.objects.all().order_by('-id'),
            search_field="ip_address",
            list_key="blocked_ips",
            partial_template="tracker/partials/blocked_ips_partial.html",
            redirect_to="tracker:blocked_ips",
        )

    return blocked_render_full_page(
        request,
        ordered_qs=BlockedIP.objects.all().order_by('-id'),
        search_field="ip_address",
        list_key="blocked_ips",
        template="tracker/blocked_ips.html",
    )


@superuser_required
def blocked_ips_partial(request):
    return blocked_render_partial(
        request,
        ordered_qs=BlockedIP.objects.all().order_by('-id'),
        search_field="ip_address",
        list_key="blocked_ips",
        partial_template="tracker/partials/blocked_ips_partial.html",
    )


@superuser_required
def blocked_ips_table(request):
    return blocked_render_table(
        request,
        ordered_qs=BlockedIP.objects.all().order_by('-id'),
        search_field="ip_address",
        list_key="blocked_ips",
        table_template="tracker/partials/blocked_ips_table.html",
        table_only=False,
    )


######################################################################
@superuser_required
def blocked_isp_view(request):
    if request.method == 'POST':
        name = request.POST.get('isp_name')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if name:
            name = name.strip()
            if not BlockedISP.objects.filter(isp__iexact=name).exists():
                BlockedISP.objects.create(isp=name)
                messages.success(request, f"ISP {name} added successfully.")
            else:
                messages.warning(request, f"ISP {name} already exists.")
        elif delete_id:
            try:
                obj = BlockedISP.objects.get(id=delete_id)
                messages.error(request, f"ISP {obj.isp} deleted.")
                obj.delete()
            except BlockedISP.DoesNotExist:
                messages.error(request, "ISP not found.")
        elif delete_all:
            count = BlockedISP.objects.count()
            BlockedISP.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} ISP(s).")
        else:
            messages.error(request, "Invalid action.")

        return blocked_after_post_htmx_or_redirect(
            request,
            ordered_qs=BlockedISP.objects.all().order_by('-id'),
            search_field="isp",
            list_key="blocked_isps",
            partial_template="tracker/partials/blocked_isp_partial.html",
            redirect_to="tracker:blocked_isp",
            force_first_page=False,
        )

    return blocked_render_full_page(
        request,
        ordered_qs=BlockedISP.objects.all().order_by('-id'),
        search_field="isp",
        list_key="blocked_isps",
        template="tracker/blocked_isp.html",
    )


@superuser_required
def blocked_isp_partial(request):
    return blocked_render_partial(
        request,
        ordered_qs=BlockedISP.objects.all().order_by('-id'),
        search_field="isp",
        list_key="blocked_isps",
        partial_template="tracker/partials/blocked_isp_partial.html",
    )


@superuser_required
def blocked_isp_table(request):
    return blocked_render_table(
        request,
        ordered_qs=BlockedISP.objects.all().order_by('-id'),
        search_field="isp",
        list_key="blocked_isps",
        table_template="tracker/partials/blocked_isp_table.html",
        table_only=True,
    )


######################################################################
@superuser_required
def blocked_browser_view(request):
    if request.method == 'POST':
        name = request.POST.get('browser_name')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if name:
            name = name.strip()
            if not BlockedBrowser.objects.filter(browser__iexact=name).exists():
                BlockedBrowser.objects.create(browser=name)
                messages.success(request, f"✅ Browser {name} added successfully.")
            else:
                messages.warning(request, f"⚠️ Browser {name} already exists.")
        elif delete_id:
            try:
                browser_obj = BlockedBrowser.objects.get(id=delete_id)
                messages.error(request, f"🗑️ Browser {browser_obj.browser} deleted.")
                browser_obj.delete()
            except BlockedBrowser.DoesNotExist:
                messages.error(request, "❌ Browser not found.")
        elif delete_all:
            count = BlockedBrowser.objects.count()
            BlockedBrowser.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} browser(s).")
        else:
            messages.error(request, "Invalid action.")

        return blocked_after_post_htmx_or_redirect(
            request,
            ordered_qs=BlockedBrowser.objects.all().order_by('-id'),
            search_field="browser",
            list_key="blocked_browsers",
            partial_template="tracker/partials/blocked_browser_partial.html",
            redirect_to="tracker:blocked_browser",
        )

    return blocked_render_full_page(
        request,
        ordered_qs=BlockedBrowser.objects.all().order_by('-id'),
        search_field="browser",
        list_key="blocked_browsers",
        template="tracker/blocked_browser.html",
    )


@superuser_required
def blocked_browser_partial(request):
    return blocked_render_partial(
        request,
        ordered_qs=BlockedBrowser.objects.all().order_by('-id'),
        search_field="browser",
        list_key="blocked_browsers",
        partial_template="tracker/partials/blocked_browser_partial.html",
    )


@superuser_required
def blocked_browser_table(request):
    return blocked_render_table(
        request,
        ordered_qs=BlockedBrowser.objects.all().order_by('-id'),
        search_field="browser",
        list_key="blocked_browsers",
        table_template="tracker/partials/blocked_browser_table.html",
        table_only=False,
    )


######################################################################
@superuser_required
def blocked_os_view(request):
    if request.method == 'POST':
        os_name = request.POST.get('os_name')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if os_name:
            os_name = os_name.strip()
            if not BlockedOS.objects.filter(os__iexact=os_name).exists():
                BlockedOS.objects.create(os=os_name)
                messages.success(request, f"✅ OS {os_name} added successfully.")
            else:
                messages.warning(request, f"⚠️ OS {os_name} already exists.")
        elif delete_id:
            try:
                obj = BlockedOS.objects.get(id=delete_id)
                messages.error(request, f"🗑️ OS {obj.os} deleted.")
                obj.delete()
            except BlockedOS.DoesNotExist:
                messages.error(request, "❌ OS not found.")
        elif delete_all:
            count = BlockedOS.objects.count()
            BlockedOS.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} OS entries.")
        else:
            messages.error(request, "Invalid action.")

        return blocked_after_post_htmx_or_redirect(
            request,
            ordered_qs=BlockedOS.objects.all().order_by('-id'),
            search_field="os",
            list_key="blocked_os",
            partial_template="tracker/partials/blocked_os_partial.html",
            redirect_to="tracker:blocked_os",
        )

    return blocked_render_full_page(
        request,
        ordered_qs=BlockedOS.objects.all().order_by('-id'),
        search_field="os",
        list_key="blocked_os",
        template="tracker/blocked_os.html",
    )


@superuser_required
def blocked_os_partial(request):
    return blocked_render_partial(
        request,
        ordered_qs=BlockedOS.objects.all().order_by('-id'),
        search_field="os",
        list_key="blocked_os",
        partial_template="tracker/partials/blocked_os_partial.html",
    )


@superuser_required
def blocked_os_table(request):
    return blocked_render_table(
        request,
        ordered_qs=BlockedOS.objects.all().order_by('-id'),
        search_field="os",
        list_key="blocked_os",
        table_template="tracker/partials/blocked_os_table.html",
        table_only=False,
    )


######################################################################
@superuser_required
def blocked_hostname_view(request):
    if request.method == 'POST':
        name = request.POST.get('hostname_name')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if name:
            name = name.strip()
            if not BlockedHostname.objects.filter(hostname__iexact=name).exists():
                BlockedHostname.objects.create(hostname=name)
                messages.success(request, f"✅ Blocked Hostname: {name}")
            else:
                messages.warning(request, f"⚠️ {name} already exists.")
        elif delete_id:
            try:
                obj = BlockedHostname.objects.get(id=delete_id)
                messages.error(request, f"🗑️ Hostname {obj.hostname} deleted.")
                obj.delete()
            except BlockedHostname.DoesNotExist:
                messages.error(request, "❌ Hostname not found.")
        elif delete_all:
            count = BlockedHostname.objects.count()
            BlockedHostname.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} hostname(s).")
        else:
            messages.error(request, "Invalid action.")

        return blocked_after_post_htmx_or_redirect(
            request,
            ordered_qs=BlockedHostname.objects.all().order_by('-id'),
            search_field="hostname",
            list_key="blocked_hostnames",
            partial_template="tracker/partials/blocked_hostname_partial.html",
            redirect_to="tracker:blocked_hostname",
        )

    return blocked_render_full_page(
        request,
        ordered_qs=BlockedHostname.objects.all().order_by('-id'),
        search_field="hostname",
        list_key="blocked_hostnames",
        template="tracker/blocked_hostname.html",
    )


@superuser_required
def blocked_hostname_partial(request):
    return blocked_render_partial(
        request,
        ordered_qs=BlockedHostname.objects.all().order_by('-id'),
        search_field="hostname",
        list_key="blocked_hostnames",
        partial_template="tracker/partials/blocked_hostname_partial.html",
    )


@superuser_required
def blocked_hostname_table(request):
    return blocked_render_table(
        request,
        ordered_qs=BlockedHostname.objects.all().order_by('-id'),
        search_field="hostname",
        list_key="blocked_hostnames",
        table_template="tracker/partials/blocked_hostname_table.html",
        table_only=False,
    )
