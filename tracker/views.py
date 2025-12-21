from rest_framework.views import APIView
from rest_framework.response import Response
from .models import AllowedCountry
from django.db.models import Q
from .models import (
    Visitor, IPLog,
    BlockedIP, BlockedHostname, BlockedISP, BlockedOS, BlockedBrowser, RejectedVisitor, BlockedSubnet, IPInfo
)
import user_agents
import socket
import requests
from django.views.decorators.http import require_POST
import ipaddress
from django.core.paginator import Paginator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


@login_required
def dashboard_view(request):
    return render(request, 'dashboard.html')
######################################################################
@login_required
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
            q = (request.GET.get("q") or "").strip()
            all_subnets = BlockedSubnet.objects.all().order_by('-id')
            if q:
                all_subnets = all_subnets.filter(cidr__icontains=q)

            paginator = Paginator(all_subnets, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_subnets_partial.html", {
                "blocked_subnets": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:blocked_subnets')

    q = (request.GET.get("q") or "").strip()
    all_subnets = BlockedSubnet.objects.all().order_by('-id')
    if q:
        all_subnets = all_subnets.filter(cidr__icontains=q)

    paginator = Paginator(all_subnets, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_subnets.html", {
        "blocked_subnets": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def blocked_subnets_partial(request):
    q = (request.GET.get("q") or "").strip()
    all_subnets = BlockedSubnet.objects.all().order_by('-id')
    if q:
        all_subnets = all_subnets.filter(cidr__icontains=q)

    paginator = Paginator(all_subnets, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_subnets_partial.html", {
        "blocked_subnets": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_subnets_table(request):
    q = (request.GET.get("q") or "").strip()
    all_subnets = BlockedSubnet.objects.all().order_by('-id')
    if q:
        all_subnets = all_subnets.filter(cidr__icontains=q)

    paginator = Paginator(all_subnets, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_subnets_table.html", {
        "blocked_subnets": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
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
            q = (request.GET.get("q") or "").strip()

            all_ips = BlockedIP.objects.all().order_by('-id')
            if q:
                all_ips = all_ips.filter(Q(ip_address__icontains=q))

            paginator = Paginator(all_ips, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_ips_partial.html", {
                "blocked_ips": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:blocked_ips')

    q = (request.GET.get("q") or "").strip()

    all_ips = BlockedIP.objects.all().order_by('-id')
    if q:
        all_ips = all_ips.filter(Q(ip_address__icontains=q))

    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_ips.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def blocked_ips_partial(request):
    q = (request.GET.get("q") or "").strip()

    all_ips = BlockedIP.objects.all().order_by('-id')
    if q:
        all_ips = all_ips.filter(Q(ip_address__icontains=q))

    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_ips_partial.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_ips_table(request):
    q = (request.GET.get("q") or "").strip()

    all_ips = BlockedIP.objects.all().order_by('-id')
    if q:
        all_ips = all_ips.filter(Q(ip_address__icontains=q))

    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'partials/blocked_ips_table.html', {
        'blocked_ips': page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
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
            q = (request.GET.get("q") or "").strip()
            all_isps = BlockedISP.objects.all().order_by('-id')
            if q:
                all_isps = all_isps.filter(Q(isp__icontains=q))

            paginator = Paginator(all_isps, 20)
            page_number = request.GET.get("page")
            page_obj = paginator.get_page(page_number)

            return render(request, "partials/blocked_isp_partial.html", {
                "blocked_isps": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect("tracker:blocked_isp")

    q = (request.GET.get("q") or "").strip()
    all_isps = BlockedISP.objects.all().order_by('-id')
    if q:
        all_isps = all_isps.filter(Q(isp__icontains=q))

    paginator = Paginator(all_isps, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_isp.html", {
        "blocked_isps": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def blocked_isp_partial(request):
    q = (request.GET.get("q") or "").strip()
    all_isps = BlockedISP.objects.all().order_by('-id')
    if q:
        all_isps = all_isps.filter(Q(isp__icontains=q))

    paginator = Paginator(all_isps, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_isp_partial.html", {
        "blocked_isps": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_isp_table(request):
    q = (request.GET.get("q") or "").strip()
    all_isps = BlockedISP.objects.all().order_by('-id')
    if q:
        all_isps = all_isps.filter(Q(isp__icontains=q))

    paginator = Paginator(all_isps, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_isp_table.html", {
        "blocked_isps": page_obj.object_list,
        "q": q
    })
######################################################################
@login_required
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
            q = (request.GET.get("q") or "").strip()

            all_browsers = BlockedBrowser.objects.all().order_by('-id')
            if q:
                all_browsers = all_browsers.filter(Q(browser__icontains=q))

            paginator = Paginator(all_browsers, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_browser_partial.html", {
                "blocked_browsers": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:blocked_browser')

    q = (request.GET.get("q") or "").strip()

    all_browsers = BlockedBrowser.objects.all().order_by('-id')
    if q:
        all_browsers = all_browsers.filter(Q(browser__icontains=q))

    paginator = Paginator(all_browsers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'blocked_browser.html', {
        'blocked_browsers': page_obj.object_list,
        'page_obj': page_obj,
        'q': q
    })
@login_required
def blocked_browser_partial(request):
    q = (request.GET.get("q") or "").strip()

    all_browsers = BlockedBrowser.objects.all().order_by('-id')
    if q:
        all_browsers = all_browsers.filter(Q(browser__icontains=q))

    paginator = Paginator(all_browsers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_browser_partial.html", {
        "blocked_browsers": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_browser_table(request):
    q = (request.GET.get("q") or "").strip()

    all_browsers = BlockedBrowser.objects.all().order_by('-id')
    if q:
        all_browsers = all_browsers.filter(Q(browser__icontains=q))

    paginator = Paginator(all_browsers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_browser_table.html", {
        "blocked_browsers": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
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
            q = (request.GET.get("q") or "").strip()

            all_os = BlockedOS.objects.all().order_by('-id')
            if q:
                all_os = all_os.filter(Q(os__icontains=q))

            paginator = Paginator(all_os, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_os_partial.html", {
                "blocked_os": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:blocked_os')

    q = (request.GET.get("q") or "").strip()

    all_os = BlockedOS.objects.all().order_by('-id')
    if q:
        all_os = all_os.filter(Q(os__icontains=q))

    paginator = Paginator(all_os, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_os.html", {
        "blocked_os": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def blocked_os_partial(request):
    q = (request.GET.get("q") or "").strip()

    all_os = BlockedOS.objects.all().order_by('-id')
    if q:
        all_os = all_os.filter(Q(os__icontains=q))

    paginator = Paginator(all_os, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_os_partial.html", {
        "blocked_os": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_os_table(request):
    q = (request.GET.get("q") or "").strip()

    all_os = BlockedOS.objects.all().order_by('-id')
    if q:
        all_os = all_os.filter(Q(os__icontains=q))

    paginator = Paginator(all_os, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'partials/blocked_os_table.html', {
        'blocked_os': page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
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
            q = (request.GET.get("q") or "").strip()

            all_items = BlockedHostname.objects.all().order_by('-id')
            if q:
                all_items = all_items.filter(Q(hostname__icontains=q))

            paginator = Paginator(all_items, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_hostname_partial.html", {
                "blocked_hostnames": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:blocked_hostname')

    q = (request.GET.get("q") or "").strip()

    all_items = BlockedHostname.objects.all().order_by('-id')
    if q:
        all_items = all_items.filter(Q(hostname__icontains=q))

    paginator = Paginator(all_items, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_hostname.html", {
        "blocked_hostnames": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def blocked_hostname_partial(request):
    q = (request.GET.get("q") or "").strip()

    all_items = BlockedHostname.objects.all().order_by('-id')
    if q:
        all_items = all_items.filter(Q(hostname__icontains=q))

    paginator = Paginator(all_items, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_hostname_partial.html", {
        "blocked_hostnames": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_hostname_table(request):
    q = (request.GET.get("q") or "").strip()

    all_items = BlockedHostname.objects.all().order_by('-id')
    if q:
        all_items = all_items.filter(Q(hostname__icontains=q))

    paginator = Paginator(all_items, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_hostname_table.html", {
        "blocked_hostnames": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
def allowed_country_view(request):
    if request.method == 'POST':
        code = request.POST.get('country')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if code:
            code = code.strip().upper()
            if not AllowedCountry.objects.filter(code=code).exists():
                AllowedCountry.objects.create(code=code)
                messages.success(request, f"✅ Country code {code} added.")
            else:
                messages.warning(request, f"⚠️ {code} already exists.")
        elif delete_id:
            try:
                obj = AllowedCountry.objects.get(id=delete_id)
                messages.error(request, f"🗑️ {obj.code} deleted.")
                obj.delete()
            except AllowedCountry.DoesNotExist:
                messages.error(request, "❌ Entry not found.")
        elif delete_all:
            count = AllowedCountry.objects.count()
            AllowedCountry.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} country codes.")
        else:
            messages.error(request, "Invalid action.")

        if request.headers.get("HX-Request"):
            q = (request.GET.get("q") or "").strip()

            queryset = AllowedCountry.objects.all().order_by("code")
            if q:
                queryset = queryset.filter(Q(code__icontains=q))

            paginator = Paginator(queryset, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/allowed_country_partial.html", {
                "allowed_countries": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:allowed_country')

    q = (request.GET.get("q") or "").strip()

    queryset = AllowedCountry.objects.all().order_by("code")
    if q:
        queryset = queryset.filter(Q(code__icontains=q))

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "allowed_country.html", {
        "allowed_countries": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def allowed_country_partial(request):
    q = (request.GET.get("q") or "").strip()

    queryset = AllowedCountry.objects.all().order_by("code")
    if q:
        queryset = queryset.filter(Q(code__icontains=q))

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_country_partial.html", {
        "allowed_countries": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def allowed_country_table(request):
    q = (request.GET.get("q") or "").strip()

    queryset = AllowedCountry.objects.all().order_by("code")
    if q:
        queryset = queryset.filter(Q(code__icontains=q))

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_country_table.html", {
        "allowed_countries": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
def allowed_logs_view(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if delete_id:
            try:
                log = Visitor.objects.get(id=delete_id)
                ip = log.ip_address
                Visitor.objects.filter(ip_address=ip).delete()
                messages.error(request, f"🗑️ Deleted all logs for IP: {ip}")
            except Visitor.DoesNotExist:
                messages.error(request, "Log not found.")
        elif delete_all:
            Visitor.objects.all().delete()
            messages.success(request, "✅ All allowed logs have been deleted.")
        else:
            messages.error(request, "Invalid action.")

        if request.headers.get("HX-Request"):
            q = (request.GET.get("q") or request.GET.get("search") or "").strip()

            queryset = Visitor.objects.all().order_by("-timestamp")
            if q:
                queryset = queryset.filter(
                    Q(ip_address__icontains=q) |
                    Q(hostname__icontains=q) |
                    Q(isp__icontains=q) |
                    Q(os__icontains=q) |
                    Q(browser__icontains=q) |
                    Q(country__icontains=q)
                )

            paginator = Paginator(queryset, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/allowed_logs_partial.html", {
                "logs": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:allowed_logs')

    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = Visitor.objects.all().order_by("-timestamp")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(hostname__icontains=q) |
            Q(isp__icontains=q) |
            Q(os__icontains=q) |
            Q(browser__icontains=q) |
            Q(country__icontains=q)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "allowed_logs.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def allowed_logs_partial(request):
    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = Visitor.objects.all().order_by("-timestamp")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(hostname__icontains=q) |
            Q(isp__icontains=q) |
            Q(os__icontains=q) |
            Q(browser__icontains=q) |
            Q(country__icontains=q)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_logs_partial.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def allowed_logs_table(request):
    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = Visitor.objects.all().order_by("-timestamp")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(hostname__icontains=q) |
            Q(isp__icontains=q) |
            Q(os__icontains=q) |
            Q(browser__icontains=q) |
            Q(country__icontains=q)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_logs_table.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
def denied_logs_view(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if delete_id:
            try:
                log = RejectedVisitor.objects.get(id=delete_id)
                ip = log.ip_address
                RejectedVisitor.objects.filter(ip_address=ip).delete()
                messages.success(request, f"🗑️ Deleted all logs for IP: {ip}")
            except RejectedVisitor.DoesNotExist:
                messages.error(request, "Log not found.")
        elif delete_all:
            RejectedVisitor.objects.all().delete()
            messages.success(request, "✅ All denied logs have been deleted.")
        else:
            messages.error(request, "Invalid action.")

        if request.headers.get("HX-Request"):
            q = (request.GET.get("q") or request.GET.get("search") or "").strip()

            queryset = RejectedVisitor.objects.all().order_by("-timestamp")
            if q:
                queryset = queryset.filter(
                    Q(ip_address__icontains=q) |
                    Q(hostname__icontains=q) |
                    Q(isp__icontains=q) |
                    Q(os__icontains=q) |
                    Q(browser__icontains=q) |
                    Q(country__icontains=q)
                )

            paginator = Paginator(queryset, 10)
            page_obj = paginator.get_page(1)

            return render(request, "partials/denied_logs_partial.html", {
                "logs": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:denied_logs')

    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = RejectedVisitor.objects.all().order_by("-timestamp")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(hostname__icontains=q) |
            Q(isp__icontains=q) |
            Q(os__icontains=q) |
            Q(browser__icontains=q) |
            Q(country__icontains=q)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "denied_logs.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def denied_logs_partial(request):
    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = RejectedVisitor.objects.all().order_by("-timestamp")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(hostname__icontains=q) |
            Q(isp__icontains=q) |
            Q(os__icontains=q) |
            Q(browser__icontains=q) |
            Q(country__icontains=q)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/denied_logs_partial.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def denied_logs_table(request):
    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = RejectedVisitor.objects.all().order_by("-timestamp")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(hostname__icontains=q) |
            Q(isp__icontains=q) |
            Q(os__icontains=q) |
            Q(browser__icontains=q) |
            Q(country__icontains=q)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/denied_logs_table.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@login_required
def ip_info_view(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        block_type = request.POST.get("block_type")
        block_value = request.POST.get("block_value")
        if block_type and block_value:
            return add_block_rule(request)

        if delete_id:
            try:
                row = IPInfo.objects.get(id=delete_id)
                ip = row.ip_address
                IPInfo.objects.filter(ip_address=ip).delete()
                messages.success(request, f"🗑️ Deleted IP info for IP: {ip}")
            except IPInfo.DoesNotExist:
                messages.error(request, "Row not found.")
        elif delete_all:
            IPInfo.objects.all().delete()
            messages.success(request, "✅ All IP info records have been deleted.")
        else:
            messages.error(request, "Invalid action.")

        if request.headers.get("HX-Request"):
            q = (request.GET.get("q") or request.GET.get("search") or "").strip()

            queryset = IPInfo.objects.all().order_by("-last_seen")
            if q:
                queryset = queryset.filter(
                    Q(ip_address__icontains=q) |
                    Q(isp__icontains=q) |
                    Q(subnet__icontains=q) |
                    Q(as_type__icontains=q)
                )

            paginator = Paginator(queryset, 10)
            page_obj = paginator.get_page(1)

            return render(request, "partials/ip_info_partial.html", {
                "ips": page_obj.object_list,
                "page_obj": page_obj,
                "q": q,
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:ip_info')

    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = IPInfo.objects.all().order_by("-last_seen")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(isp__icontains=q) |
            Q(subnet__icontains=q) |
            Q(as_type__icontains=q)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "ip_info.html", {
        "ips": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
@login_required
def ip_info_partial(request):
    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = IPInfo.objects.all().order_by("-last_seen")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(isp__icontains=q) |
            Q(subnet__icontains=q) |
            Q(as_type__icontains=q)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/ip_info_partial.html", {
        "ips": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "messages": messages.get_messages(request)
    })
@login_required
def ip_info_table(request):
    q = (request.GET.get("q") or request.GET.get("search") or "").strip()

    queryset = IPInfo.objects.all().order_by("-last_seen")
    if q:
        queryset = queryset.filter(
            Q(ip_address__icontains=q) |
            Q(isp__icontains=q) |
            Q(subnet__icontains=q) |
            Q(as_type__icontains=q)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/ip_info_table.html", {
        "ips": page_obj.object_list,
        "page_obj": page_obj,
        "q": q
    })
######################################################################
@require_POST
@login_required
def add_block_rule(request):
    if request.method == 'POST':
        block_type = request.POST.get("block_type")
        block_value = request.POST.get("block_value", "").strip()

        if not block_type or not block_value:
            messages.error(request, "Both type and value are required.")
        else:
            model_map = {
                'ip': BlockedIP,
                'isp': BlockedISP,
                'hostname': BlockedHostname,
                'os': BlockedOS,
                'browser': BlockedBrowser,
                'subnet': BlockedSubnet,  # ✅ صح
            }

            model = model_map.get(block_type.lower())
            if model:
                if not model.objects.filter(**{model._meta.fields[1].name + "__iexact": block_value}).exists():
                    model.objects.create(**{model._meta.fields[1].name: block_value})
                    messages.success(request, f"✅ Block rule added: {block_value}")
                else:
                    messages.warning(request, f"⚠️ Rule already exists: {block_value}")
            else:
                messages.error(request, "Invalid rule type.")

        # HTMX Response
        if request.headers.get("HX-Request"):
            return render(request, "partials/messages.html", {
                "messages": messages.get_messages(request)
            })

        return redirect('tracker:denied_logs')
######################################################################
@login_required()
def dinger_ip_view(request):
    if request.method == 'POST':
        ip_to_delete = request.POST.get('delete_ip')
        if ip_to_delete:
            deleted, _ = IPLog.objects.filter(ip_address=ip_to_delete).delete()
            if deleted:
                messages.success(request, f"IP {ip_to_delete} deleted successfully.")
            else:
                messages.error(request, f"Failed to delete IP {ip_to_delete}.")
        return redirect('/tracker/dinger-ip/')  # اسم الـ URL في urls.py

    dingers = (
        IPLog.objects
        .filter(count__gt=10)
        .values('ip_address', 'count', 'last_seen')
        .order_by('-count')
    )
    return render(request, 'dinger_ip.html', {'dingers': dingers})
######################################################################
class LogVisitorAPIView(APIView):
    def post(self, request):
        allowed_codes = list(AllowedCountry.objects.values_list('code', flat=True))
        ip = request.data.get('ip')
        user_agent_str = request.data.get('useragent', '')

        if not ip or not user_agent_str:
            return Response({'error': 'Missing ip or useragent'}, status=400)

        # تحليل User Agent
        parsed_ua = user_agents.parse(user_agent_str)
        os = f"{parsed_ua.os.family} {parsed_ua.os.version_string}"
        browser = f"{parsed_ua.browser.family} {parsed_ua.browser.version_string}"

        # جلب hostname
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except:
            hostname = ''

        try:
            response = requests.get(f'https://ipwho.is/{ip}').json()
            isp = response.get('connection', {}).get('isp', '') or ''
            country_code = (response.get('country_code', '') or '').upper()

            response2 = requests.get(f'https://ipinfo.io/api/pricing/samples/{ip}').json()

            b_subnet = response2.get('business', {}).get('sample', {}).get('asn', {}).get('route', '') or ''
            as_type = response2.get('core', {}).get('sample', {}).get('as', {}).get('type', '') or ''

            is_anonymous = bool(response2.get('core', {}).get('sample', {}).get('is_anonymous', False))
            is_hosting = bool(response2.get('core', {}).get('sample', {}).get('is_hosting', False))

            privacy = response2.get('business', {}).get('sample', {}).get('privacy', {}) or {}
            is_proxy = bool(privacy.get('proxy', False))
            is_vpn = bool(privacy.get('vpn', False))
            is_tor = bool(privacy.get('tor', False))

            # إضافي
            is_satellite = bool(response2.get('core', {}).get('sample', {}).get('is_satellite', False))

        except Exception:
            isp = ''
            country_code = ''
            b_subnet = ''
            as_type = ''
            is_anonymous = False
            is_hosting = False
            is_proxy = False
            is_vpn = False
            is_tor = False
            is_satellite = False

        # Blocked Subnet (CIDR)
        try:
            ip_obj = ipaddress.ip_address(ip)
            for cidr in BlockedSubnet.objects.values_list('cidr', flat=True):
                try:
                    if ip_obj in ipaddress.ip_network(cidr, strict=False):
                        RejectedVisitor.objects.create(
                            ip_address=ip,
                            b_subnet=b_subnet,
                            hostname=hostname,
                            isp=isp,
                            os=os,
                            browser=browser,
                            country=country_code,
                            reason="Blocked Subnet"
                        )
                        return Response({'status': 'access_denied', 'reason': 'Blocked Subnet'}, status=403)
                except ValueError:
                    continue
        except ValueError:
            pass

        # IP
        if BlockedIP.objects.filter(ip_address=ip).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                b_subnet=b_subnet,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked IP"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked IP'}, status=403)

        # ISP
        if BlockedISP.objects.filter(isp__iexact=isp).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                b_subnet=b_subnet,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked ISP"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked ISP'}, status=403)

        # OS
        if BlockedOS.objects.filter(os__iexact=os.strip()).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                b_subnet=b_subnet,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked OS"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked OS'}, status=403)

        # Browser
        if BlockedBrowser.objects.filter(browser__iexact=browser.strip()).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                b_subnet=b_subnet,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked Browser"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked Browser'}, status=403)

        # Country Code check
        if country_code not in allowed_codes:
            RejectedVisitor.objects.create(
                ip_address=ip,
                b_subnet=b_subnet,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked Country"
            )
            return Response({'status': 'access_denied', 'reason': f'Country code \"{country_code}\" is not allowed'}, status=403)

        # Hostname
        if hostname and BlockedHostname.objects.filter(
                Q(hostname__icontains=hostname) | Q(hostname__in=hostname.split('.'))
        ).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                b_subnet=b_subnet,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked Hostname"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked Hostname'}, status=403)

        # Save visitor (ALLOWED)
        Visitor.objects.create(
            ip_address=ip,
            b_subnet=b_subnet,
            hostname=hostname,
            isp=isp,
            os=os,
            browser=browser,
            user_agent=user_agent_str,
            country=country_code
        )

        # Save / Update IPInfo (ALLOWED IPs ONLY)
        IPInfo.objects.update_or_create(
            ip_address=ip,
            defaults={
                'isp': isp,
                'subnet': b_subnet,
                'as_type': as_type,
                'is_anonymous': is_anonymous,
                'is_proxy': is_proxy,
                'is_hosting': is_hosting,
                'is_tor': is_tor,
                'is_vpn': is_vpn,
                'is_satellite': is_satellite,
            }
        )

        # Update IPLog
        ip_log, created = IPLog.objects.get_or_create(ip_address=ip)
        if not created:
            ip_log.count += 1
            ip_log.save()

        return Response({'status': 'access_granted'}, status=201)


######################################################################
# @login_required
# @require_POST
# def delete_log(request, pk):
#     Visitor.objects.filter(pk=pk).delete()
#     logs = Visitor.objects.all().order_by('-timestamp')
#     return render(request, 'partials/allowed_logs_table.html', {'logs': logs})
#
