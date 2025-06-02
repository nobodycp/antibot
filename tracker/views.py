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


def home_redirect(request):
    return redirect('dashboard')

@login_required
def dashboard_view(request):
    return render(request, 'dashboard.html')

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
            paginator = Paginator(all_ips, 50)
            page_obj = paginator.get_page(1)

            return render(request, "partials/blocked_ips_partial.html", {
                "blocked_ips": page_obj.object_list,
                "page_obj": page_obj,
                "messages": messages.get_messages(request)
            })

        return redirect("blocked_ips")

    # GET العادي
    all_ips = BlockedIP.objects.all().order_by('-id')
    paginator = Paginator(all_ips, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blocked_ips.html", {
        "blocked_ips": page_obj.object_list,
        "page_obj": page_obj
    })
def blocked_ips_table(request):
    blocked_ips = BlockedIP.objects.all().order_by('-id')
    return render(request, 'partials/blocked_ips_table.html', {'blocked_ips': blocked_ips})
@login_required
def blocked_ips_partial(request):
    blocked_ips = BlockedIP.objects.all().order_by('-id')
    return render(request, 'partials/blocked_ips_partial.html', {
        'blocked_ips': blocked_ips,
        'messages': messages.get_messages(request)
    })
@login_required
def blocked_isp_view(request):
    if request.method == 'POST':
        name = request.POST.get('isp_name')
        delete_id = request.POST.get('delete_id')

        # إضافة ISP
        if name:
            if not BlockedISP.objects.filter(isp__iexact=name).exists():
                BlockedISP.objects.create(isp=name)
                messages.success(request, f"Blocked ISP: {name}")
            else:
                messages.warning(request, f"{name} is already blocked.")

        # حذف ISP
        elif delete_id:
            try:
                isp = BlockedISP.objects.get(id=delete_id)
                isp.delete()
                messages.success(request, f"Deleted ISP: {isp.isp}")
            except BlockedISP.DoesNotExist:
                messages.error(request, "ISP not found.")

        else:
            messages.error(request, "Invalid action.")

        return redirect('blocked_isp')

    blocked_isps = BlockedISP.objects.all().order_by('-id')
    return render(request, 'blocked_isp.html', {'blocked_isps': blocked_isps})

@login_required
def blocked_os_view(request):
    if request.method == 'POST':
        name = request.POST.get('os_name')
        delete_id = request.POST.get('delete_id')

        if name:
            if not BlockedOS.objects.filter(os__iexact=name).exists():
                BlockedOS.objects.create(os=name)
                messages.success(request, f"Blocked OS: {name}")
            else:
                messages.warning(request, f"{name} is already blocked.")
        elif delete_id:
            try:
                os_entry = BlockedOS.objects.get(id=delete_id)
                os_entry.delete()
                messages.success(request, f"Deleted OS: {os_entry.os}")
            except BlockedOS.DoesNotExist:
                messages.error(request, "OS not found.")
        else:
            messages.error(request, "Invalid action.")

        return redirect('blocked_os')

    blocked_os_list = BlockedOS.objects.all().order_by('-id')
    return render(request, 'blocked_os.html', {'blocked_os_list': blocked_os_list})

@login_required
def blocked_browser_view(request):
    if request.method == 'POST':
        name = request.POST.get('browser_name')
        delete_id = request.POST.get('delete_id')

        if name:
            if not BlockedBrowser.objects.filter(browser__iexact=name).exists():
                BlockedBrowser.objects.create(browser=name)
                messages.success(request, f"Blocked Browser: {name}")
            else:
                messages.warning(request, f"{name} is already blocked.")
        elif delete_id:
            try:
                browser_obj = BlockedBrowser.objects.get(id=delete_id)
                browser_obj.delete()
                messages.success(request, f"Deleted Browser: {browser_obj.browser}")
            except BlockedBrowser.DoesNotExist:
                messages.error(request, "Browser not found.")
        else:
            messages.error(request, "Invalid action.")

        return redirect('blocked_browser')

    blocked_browser_list = BlockedBrowser.objects.all().order_by('-id')
    return render(request, 'blocked_browser.html', {'blocked_browser_list': blocked_browser_list})

@login_required
def allowed_country_view(request):
    if request.method == 'POST':
        code = request.POST.get('country')
        delete_id = request.POST.get('delete_id')

        if code:
            code = code.strip().upper()
            if not AllowedCountry.objects.filter(code=code).exists():
                AllowedCountry.objects.create(code=code)
                messages.success(request, f"Added country code {code}")
            else:
                messages.warning(request, f"Country code {code} is already allowed.")
        elif delete_id:
            try:
                obj = AllowedCountry.objects.get(id=delete_id)
                obj.delete()
                messages.success(request, f"Deleted country code {obj.code}")
            except AllowedCountry.DoesNotExist:
                messages.error(request, "Entry not found.")

        return redirect('allowed_country')

    allowed_countries = AllowedCountry.objects.all().order_by('code')
    return render(request, 'allowed_country.html', {'allowed_countries': allowed_countries})

@login_required
def blocked_hostname_view(request):
    if request.method == 'POST':
        name = request.POST.get('hostname')
        delete_id = request.POST.get('delete_id')

        if name:
            name = name.strip().lower()
            if not BlockedHostname.objects.filter(hostname__iexact=name).exists():
                BlockedHostname.objects.create(hostname=name)
                messages.success(request, f"Blocked Hostname: {name}")
            else:
                messages.warning(request, f"{name} is already blocked.")
        elif delete_id:
            try:
                host = BlockedHostname.objects.get(id=delete_id)
                host.delete()
                messages.success(request, f"Deleted Hostname: {host.hostname}")
            except BlockedHostname.DoesNotExist:
                messages.error(request, "Hostname not found.")
        else:
            messages.error(request, "Invalid input.")

        return redirect('blocked_hostname')

    blocked_hostnames = BlockedHostname.objects.all().order_by('-id')
    return render(request, 'blocked_hostname.html', {'hostnames': blocked_hostnames})

@login_required
def allowed_logs_view(request):
    if request.method == 'POST':
        delete_id = request.POST.get('delete_id')
        delete_all = request.POST.get('delete_all')

        if delete_all == '1':
            Visitor.objects.all().delete()
            messages.success(request, "All allowed logs have been deleted.")
        elif delete_id:
            try:
                log = Visitor.objects.get(id=delete_id)
                log.delete()
                messages.success(request, f"Deleted Allowed Log: {log.ip_address}")
            except Visitor.DoesNotExist:
                messages.error(request, "Log not found.")
        else:
            messages.error(request, "Invalid input.")

        return redirect('allowed_logs')

    logs = Visitor.objects.all().order_by('-id')
    search = request.GET.get('search', '')
    if search:
        logs = logs.filter(
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search) |
            Q(isp__icontains=search) |
            Q(os__icontains=search) |
            Q(browser__icontains=search) |
            Q(country__icontains=search)
        )

    return render(request, 'allowed_logs.html', {'logs': logs})

@login_required
def allowed_logs_table(request):
    logs = Visitor.objects.all().order_by('-timestamp')
    search = request.GET.get('search', '')
    if search:
        logs = logs.filter(
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search) |
            Q(isp__icontains=search) |
            Q(os__icontains=search) |
            Q(browser__icontains=search) |
            Q(country__icontains=search)
        )
    return render(request, 'partials/allowed_logs_table.html', {'logs': logs})

@login_required
def denied_logs_view(request):
    if request.method == 'POST':
        if 'delete_all' in request.POST:
            RejectedVisitor.objects.all().delete()
            messages.success(request, "All denied logs have been deleted.")
            return redirect('denied_logs')

        delete_id = request.POST.get('delete_id')
        if delete_id:
            try:
                log = RejectedVisitor.objects.get(id=delete_id)
                ip = log.ip_address
                RejectedVisitor.objects.filter(ip_address=ip).delete()
                messages.success(request, f"Deleted all logs for IP: {ip}")
            except RejectedVisitor.DoesNotExist:
                messages.error(request, "Log not found.")
            return redirect('denied_logs')

    # فلترة بالسيرش
    search = request.GET.get('search', '')
    queryset = RejectedVisitor.objects.all().order_by('-timestamp')
    if search:
        queryset = queryset.filter(
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search) |
            Q(isp__icontains=search) |
            Q(os__icontains=search) |
            Q(browser__icontains=search) |
            Q(country__icontains=search)
        )

    # إلغاء التكرار حسب IP يدويًا
    logs = []
    seen_ips = set()
    for log in queryset:
        if log.ip_address not in seen_ips:
            logs.append(log)
            seen_ips.add(log.ip_address)

    return render(request, 'denied_logs.html', {'logs': logs})

@login_required
def denied_logs_table(request):
    search = request.GET.get('search', '')

    # خطوة 1: فلترة بالسيرش أولاً
    queryset = RejectedVisitor.objects.all().order_by('-timestamp')
    if search:
        queryset = queryset.filter(
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search) |
            Q(isp__icontains=search) |
            Q(os__icontains=search) |
            Q(browser__icontains=search) |
            Q(country__icontains=search)
        )

    # خطوة 2: إزالة التكرار حسب IP
    logs = []
    seen_ips = set()
    for log in queryset:
        if log.ip_address not in seen_ips:
            logs.append(log)
            seen_ips.add(log.ip_address)

    return render(request, 'partials/denied_logs_table.html', {'logs': logs})

@login_required
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
        if BlockedISP.objects.filter(isp__icontains=isp).exists():
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

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@login_required
@require_POST
def delete_log(request, pk):
    Visitor.objects.filter(pk=pk).delete()
    logs = Visitor.objects.all().order_by('-timestamp')
    return render(request, 'partials/allowed_logs_table.html', {'logs': logs})