import ipaddress

from django.contrib import messages
from django.shortcuts import redirect, render

from core.decorators import superuser_required

from ..helpers.blocked_views_helper import (
    apply_search_filter,
    blocked_list_page_context,
    blocked_partial_context,
    blocked_table_only_context,
    list_search_q,
    paginated_page,
)
from ..models import (
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
    BlockedSubnet,
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

        if request.headers.get("HX-Request"):
            q = list_search_q(request)
            qs = apply_search_filter(BlockedSubnet.objects.all().order_by('-id'), q, "cidr")
            page_obj = paginated_page(request, qs, force_first_page=True)
            return render(
                request,
                "tracker/partials/blocked_subnets_partial.html",
                blocked_partial_context("blocked_subnets", page_obj, q, request),
            )

        return redirect('tracker:blocked_subnets')

    q = list_search_q(request)
    qs = apply_search_filter(BlockedSubnet.objects.all().order_by('-id'), q, "cidr")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/blocked_subnets.html",
        blocked_list_page_context("blocked_subnets", page_obj, q),
    )


@superuser_required
def blocked_subnets_partial(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedSubnet.objects.all().order_by('-id'), q, "cidr")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_subnets_partial.html",
        blocked_partial_context("blocked_subnets", page_obj, q, request),
    )


@superuser_required
def blocked_subnets_table(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedSubnet.objects.all().order_by('-id'), q, "cidr")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_subnets_table.html",
        blocked_list_page_context("blocked_subnets", page_obj, q),
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

        if request.headers.get("HX-Request"):
            q = list_search_q(request)
            qs = apply_search_filter(BlockedIP.objects.all().order_by('-id'), q, "ip_address")
            page_obj = paginated_page(request, qs, force_first_page=True)
            return render(
                request,
                "tracker/partials/blocked_ips_partial.html",
                blocked_partial_context("blocked_ips", page_obj, q, request),
            )

        return redirect('tracker:blocked_ips')

    q = list_search_q(request)
    qs = apply_search_filter(BlockedIP.objects.all().order_by('-id'), q, "ip_address")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/blocked_ips.html",
        blocked_list_page_context("blocked_ips", page_obj, q),
    )


@superuser_required
def blocked_ips_partial(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedIP.objects.all().order_by('-id'), q, "ip_address")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_ips_partial.html",
        blocked_partial_context("blocked_ips", page_obj, q, request),
    )


@superuser_required
def blocked_ips_table(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedIP.objects.all().order_by('-id'), q, "ip_address")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        'tracker/partials/blocked_ips_table.html',
        blocked_list_page_context("blocked_ips", page_obj, q),
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

        if request.headers.get("HX-Request"):
            q = list_search_q(request)
            qs = apply_search_filter(BlockedISP.objects.all().order_by('-id'), q, "isp")
            page_obj = paginated_page(request, qs, force_first_page=False)
            return render(
                request,
                "tracker/partials/blocked_isp_partial.html",
                blocked_partial_context("blocked_isps", page_obj, q, request),
            )

        return redirect("tracker:blocked_isp")

    q = list_search_q(request)
    qs = apply_search_filter(BlockedISP.objects.all().order_by('-id'), q, "isp")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/blocked_isp.html",
        blocked_list_page_context("blocked_isps", page_obj, q),
    )


@superuser_required
def blocked_isp_partial(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedISP.objects.all().order_by('-id'), q, "isp")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_isp_partial.html",
        blocked_partial_context("blocked_isps", page_obj, q, request),
    )


@superuser_required
def blocked_isp_table(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedISP.objects.all().order_by('-id'), q, "isp")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_isp_table.html",
        blocked_table_only_context("blocked_isps", page_obj, q),
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

        if request.headers.get("HX-Request"):
            q = list_search_q(request)
            qs = apply_search_filter(BlockedBrowser.objects.all().order_by('-id'), q, "browser")
            page_obj = paginated_page(request, qs, force_first_page=True)
            return render(
                request,
                "tracker/partials/blocked_browser_partial.html",
                blocked_partial_context("blocked_browsers", page_obj, q, request),
            )

        return redirect('tracker:blocked_browser')

    q = list_search_q(request)
    qs = apply_search_filter(BlockedBrowser.objects.all().order_by('-id'), q, "browser")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        'tracker/blocked_browser.html',
        blocked_list_page_context("blocked_browsers", page_obj, q),
    )


@superuser_required
def blocked_browser_partial(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedBrowser.objects.all().order_by('-id'), q, "browser")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_browser_partial.html",
        blocked_partial_context("blocked_browsers", page_obj, q, request),
    )


@superuser_required
def blocked_browser_table(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedBrowser.objects.all().order_by('-id'), q, "browser")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_browser_table.html",
        blocked_list_page_context("blocked_browsers", page_obj, q),
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

        if request.headers.get("HX-Request"):
            q = list_search_q(request)
            qs = apply_search_filter(BlockedOS.objects.all().order_by('-id'), q, "os")
            page_obj = paginated_page(request, qs, force_first_page=True)
            return render(
                request,
                "tracker/partials/blocked_os_partial.html",
                blocked_partial_context("blocked_os", page_obj, q, request),
            )

        return redirect('tracker:blocked_os')

    q = list_search_q(request)
    qs = apply_search_filter(BlockedOS.objects.all().order_by('-id'), q, "os")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/blocked_os.html",
        blocked_list_page_context("blocked_os", page_obj, q),
    )


@superuser_required
def blocked_os_partial(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedOS.objects.all().order_by('-id'), q, "os")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_os_partial.html",
        blocked_partial_context("blocked_os", page_obj, q, request),
    )


@superuser_required
def blocked_os_table(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedOS.objects.all().order_by('-id'), q, "os")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        'tracker/partials/blocked_os_table.html',
        blocked_list_page_context("blocked_os", page_obj, q),
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

        if request.headers.get("HX-Request"):
            q = list_search_q(request)
            qs = apply_search_filter(BlockedHostname.objects.all().order_by('-id'), q, "hostname")
            page_obj = paginated_page(request, qs, force_first_page=True)
            return render(
                request,
                "tracker/partials/blocked_hostname_partial.html",
                blocked_partial_context("blocked_hostnames", page_obj, q, request),
            )

        return redirect('tracker:blocked_hostname')

    q = list_search_q(request)
    qs = apply_search_filter(BlockedHostname.objects.all().order_by('-id'), q, "hostname")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/blocked_hostname.html",
        blocked_list_page_context("blocked_hostnames", page_obj, q),
    )


@superuser_required
def blocked_hostname_partial(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedHostname.objects.all().order_by('-id'), q, "hostname")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_hostname_partial.html",
        blocked_partial_context("blocked_hostnames", page_obj, q, request),
    )


@superuser_required
def blocked_hostname_table(request):
    q = list_search_q(request)
    qs = apply_search_filter(BlockedHostname.objects.all().order_by('-id'), q, "hostname")
    page_obj = paginated_page(request, qs)
    return render(
        request,
        "tracker/partials/blocked_hostname_table.html",
        blocked_list_page_context("blocked_hostnames", page_obj, q),
    )
