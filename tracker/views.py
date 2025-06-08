from rest_framework.views import APIView
from rest_framework.response import Response
from .models import AllowedCountry
from django.db.models import Q
from .models import (
    Visitor, IPLog,
    BlockedIP, BlockedHostname, BlockedISP, BlockedOS, BlockedBrowser, RejectedVisitor
)
import user_agents
import socket
import requests
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.http import HttpResponse


def home_redirect(request):
    return redirect('dashboard')

@login_required
def dashboard_view(request):
    return render(request, 'dashboard.html')
################################### start block ip in blouk rouls
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
            # بعد العملية نرجّع أول صفحة محدثة
            all_ips = BlockedIP.objects.all().order_by('-id')
            paginator = Paginator(all_ips, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_ips_partial.html", {
                "blocked_ips": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:blocked_ips')

    # GET العادي
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_ips.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def blocked_ips_table(request):
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'partials/blocked_ips_table.html', {'blocked_ips': page_obj.object_list})
@login_required
def blocked_ips_partial(request):
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 20)  # عرض 50 IP في كل صفحة
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_ips_partial.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj
    })
################################### end block ip in blouk rouls
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
            all_isps = BlockedISP.objects.all().order_by('-id')
            paginator = Paginator(all_isps, 20)
            page_number = request.GET.get("page")
            page_obj = paginator.get_page(page_number)

            return render(request, "partials/blocked_isp_partial.html", {
                "blocked_isps": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect("dashboard:blocked_isp")

    all_isps = BlockedISP.objects.all().order_by('-id')
    paginator = Paginator(all_isps, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_isp.html", {
        "blocked_isps": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def blocked_isp_partial(request):
    all_isps = BlockedISP.objects.all().order_by('-id')
    paginator = Paginator(all_isps, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_isp_partial.html", {
        "blocked_isps": page_obj.object_list,
        "page_obj": page_obj,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_isp_table(request):
    all_isps = BlockedISP.objects.all().order_by('-id')
    paginator = Paginator(all_isps, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_isp_table.html", {
        "blocked_isps": page_obj.object_list
    })
################################### end block ip in blouk rouls
@login_required
def blocked_browser_view(request):
    if request.method == 'POST':
        name = request.POST.get('browser_name')
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if name:
            if not BlockedBrowser.objects.filter(browser__iexact=name).exists():
                BlockedBrowser.objects.create(browser=name)
                messages.success(request, f"✅ Browser {name} added successfully.")
            else:
                messages.warning(request, f"⚠️ Browser {name} already exists.")
        elif delete_id:
            try:
                browser_obj = BlockedBrowser.objects.get(id=delete_id)
                browser_obj.delete()
                messages.error(request, f"🗑️ Browser {browser_obj.browser} deleted.")
            except BlockedBrowser.DoesNotExist:
                messages.error(request, "❌ Browser not found.")
        elif delete_all:
            count = BlockedBrowser.objects.count()
            BlockedBrowser.objects.all().delete()
            messages.error(request, f"🧹 Deleted {count} browser(s).")
        else:
            messages.error(request, "Invalid action.")

        if request.headers.get("HX-Request"):
            all_browsers = BlockedBrowser.objects.all().order_by('-id')
            paginator = Paginator(all_browsers, 20)
            page_number = request.GET.get("page")
            page_obj = paginator.get_page(page_number)
            return render(request, "partials/blocked_browser_partial.html", {
                "blocked_browsers": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:blocked_browser')

    all_browsers = BlockedBrowser.objects.all().order_by('-id')
    paginator = Paginator(all_browsers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'blocked_browser.html', {
        'blocked_browsers': page_obj.object_list,
        'page_obj': page_obj
    })
@login_required
def blocked_browser_partial(request):
    all_browsers = BlockedBrowser.objects.all().order_by('-id')
    paginator = Paginator(all_browsers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "partials/blocked_browser_partial.html", {
        "blocked_browsers": page_obj.object_list,
        "page_obj": page_obj,
        "messages": messages.get_messages(request)
    })
@login_required
def blocked_browser_table(request):
    all_browsers = BlockedBrowser.objects.all().order_by('-id')
    paginator = Paginator(all_browsers, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "partials/blocked_browser_table.html", {
        "blocked_browsers": page_obj.object_list
    })
################################### end block ip in blouk rouls
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
            all_os = BlockedOS.objects.all().order_by('-id')
            paginator = Paginator(all_os, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_os_partial.html", {
                "blocked_os": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:blocked_os')

    all_os = BlockedOS.objects.all().order_by('-id')
    paginator = Paginator(all_os, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_os.html", {
        "blocked_os": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def blocked_os_table(request):
    all_os = BlockedOS.objects.all().order_by('-id')
    paginator = Paginator(all_os, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'partials/blocked_os_table.html', {
        'blocked_os': page_obj.object_list
    })
@login_required
def blocked_os_partial(request):
    all_os = BlockedOS.objects.all().order_by('-id')
    paginator = Paginator(all_os, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_os_partial.html", {
        "blocked_os": page_obj.object_list,
        "page_obj": page_obj
    })
##################################
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
            all_items = BlockedHostname.objects.all().order_by('-id')
            paginator = Paginator(all_items, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_hostname_partial.html", {
                "blocked_hostnames": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:blocked_hostname')

    all_items = BlockedHostname.objects.all().order_by('-id')
    paginator = Paginator(all_items, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_hostname.html", {
        "blocked_hostnames": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def blocked_hostname_table(request):
    all_items = BlockedHostname.objects.all().order_by('-id')
    paginator = Paginator(all_items, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_hostname_table.html", {
        "blocked_hostnames": page_obj.object_list
    })
@login_required
def blocked_hostname_partial(request):
    all_items = BlockedHostname.objects.all().order_by('-id')
    paginator = Paginator(all_items, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/blocked_hostname_partial.html", {
        "blocked_hostnames": page_obj.object_list,
        "page_obj": page_obj
    })
#######################
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
            queryset = AllowedCountry.objects.all().order_by("code")
            paginator = Paginator(queryset, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/allowed_country_partial.html", {
                "allowed_countries": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:allowed_country')

    queryset = AllowedCountry.objects.all().order_by("code")
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "allowed_country.html", {
        "allowed_countries": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def allowed_country_table(request):
    queryset = AllowedCountry.objects.all().order_by("code")
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_country_table.html", {
        "allowed_countries": page_obj.object_list
    })
@login_required
def allowed_country_partial(request):
    queryset = AllowedCountry.objects.all().order_by("code")
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_country_partial.html", {
        "allowed_countries": page_obj.object_list,
        "page_obj": page_obj
    })
#######################
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
            queryset = Visitor.objects.all().order_by('-timestamp')
            paginator = Paginator(queryset, 20)
            page_obj = paginator.get_page(1)

            return render(request, "partials/allowed_logs_partial.html", {
                "logs": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:allowed_logs')

    # GET العادي
    search = request.GET.get("search", "")
    queryset = Visitor.objects.all().order_by("-timestamp")
    if search:
        queryset = queryset.filter(
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search) |
            Q(isp__icontains=search) |
            Q(os__icontains=search) |
            Q(browser__icontains=search) |
            Q(country__icontains=search)
        )

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "allowed_logs.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def allowed_logs_table(request):
    queryset = Visitor.objects.all().order_by("-timestamp")
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_logs_table.html", {
        "logs": page_obj.object_list
    })
@login_required
def allowed_logs_partial(request):
    queryset = Visitor.objects.all().order_by("-timestamp")
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/allowed_logs_partial.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj
    })
##########################
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
            queryset = RejectedVisitor.objects.all().order_by('-timestamp')
            paginator = Paginator(queryset, 10)
            page_obj = paginator.get_page(1)

            return render(request, "partials/denied_logs_partial.html", {
                "logs": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect('dashboard:denied_logs')

    # GET
    search = request.GET.get("search", "")
    queryset = RejectedVisitor.objects.all().order_by("-timestamp")
    if search:
        queryset = queryset.filter(
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search) |
            Q(isp__icontains=search) |
            Q(os__icontains=search) |
            Q(browser__icontains=search) |
            Q(country__icontains=search)
        )

    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "denied_logs.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def denied_logs_partial(request):
    queryset = RejectedVisitor.objects.all().order_by("-timestamp")
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/denied_logs_partial.html", {
        "logs": page_obj.object_list,
        "page_obj": page_obj
    })
@login_required
def denied_logs_table(request):
    queryset = RejectedVisitor.objects.all().order_by("-timestamp")
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "partials/denied_logs_table.html", {
        "logs": page_obj.object_list
    })
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

        return redirect('dashboard:denied_logs')@login_required
def dinger_ip_view(request):
    if request.method == 'POST':
        ip_to_delete = request.POST.get('delete_ip')
        if ip_to_delete:
            deleted, _ = IPLog.objects.filter(ip_address=ip_to_delete).delete()
            if deleted:
                messages.success(request, f"IP {ip_to_delete} deleted successfully.")
            else:
                messages.error(request, f"Failed to delete IP {ip_to_delete}.")
        return redirect('/dashboard/dinger-ip/')  # اسم الـ URL في urls.py

    dingers = (
        IPLog.objects
        .filter(count__gt=10)
        .values('ip_address', 'count', 'last_seen')
        .order_by('-count')
    )
    return render(request, 'dinger_ip.html', {'dingers': dingers})

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
            isp = response.get('connection', {}).get('isp', '')
            country = response.get('country', '')
            country_code = response.get('country_code', '').upper()
        except:
            isp = ''
            country = ''
            country_code = ''

        # IP
        if BlockedIP.objects.filter(ip_address=ip).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
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
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country_code,
                reason="Blocked Hostname"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked Hostname'}, status=403)

        # Save visitor
        Visitor.objects.create(
            ip_address=ip,
            hostname=hostname,
            isp=isp,
            os=os,
            browser=browser,
            user_agent=user_agent_str,
            country=country_code
        )

        # Update IPLog
        ip_log, created = IPLog.objects.get_or_create(ip_address=ip)
        if not created:
            ip_log.count += 1
            ip_log.save()

        return Response({'status': 'access_granted'}, status=201)

# @login_required
# @require_POST
# def delete_log(request, pk):
#     Visitor.objects.filter(pk=pk).delete()
#     logs = Visitor.objects.all().order_by('-timestamp')
#     return render(request, 'partials/allowed_logs_table.html', {'logs': logs})
#
