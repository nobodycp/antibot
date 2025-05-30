from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import render, redirect, get_object_or_404
from .models import AllowedCountry

from .models import (
    Visitor, IPLog,
    BlockedIP, BlockedHostname, BlockedISP, BlockedOS, BlockedBrowser, RejectedVisitor
)

import user_agents
import socket
import requests




class LogVisitorAPIView(APIView):
    def post(self, request):
        allowed_countries_qs = AllowedCountry.objects.values_list('name', flat=True)
        allowed_countries = list(allowed_countries_qs)
        allowed_countries_lower = [c.strip().lower() for c in allowed_countries]
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
            # print("✅ قائمة الدول المسموحة:", allowed_countries)
            # print("🔍 مقارنة الدولة القادمة:", country.strip(), "| as lower():", country.strip().lower())

        except:
            isp = ''
            country = ''

        # التحقق من الدولة
        if country.strip().lower() not in allowed_countries_lower:
            RejectedVisitor.objects.create(
                ip_address=ip,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country,
                reason=f"Blocked Country "
            )
            return Response({'status': 'access_denied','reason': f'Country \"{country}\" is not allowed'}, status=403)

        # التحقق من الحظر
        if BlockedIP.objects.filter(ip_address=ip).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country,
                reason="Blocked IP"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked IP'}, status=403)

        if BlockedHostname.objects.filter(hostname__iexact=hostname).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country,
                reason=f"Blocked Hostname"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked Hostname'}, status=403)

        if BlockedOS.objects.filter(os__iexact=os.strip()).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country,
                reason=f"Blocked OS"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked OS'}, status=403)

        if BlockedBrowser.objects.filter(browser__iexact=browser.strip()).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country,
                reason=f"Blocked Browser"
            )
            #print(f"🧪 المتصفح: [{browser}], النظام: [{os}]")

            return Response({'status': 'access_denied', 'reason': 'Blocked Browser'}, status=403)

        if BlockedISP.objects.filter(isp__icontains=isp).exists():
            RejectedVisitor.objects.create(
                ip_address=ip,
                hostname=hostname,
                isp=isp,
                os=os,
                browser=browser,
                country=country,
                reason=f"Blocked ISP"
            )
            return Response({'status': 'access_denied', 'reason': 'Blocked ISP'}, status=403)

        # حفظ الزائر
        Visitor.objects.create(
            ip_address=ip,
            hostname=hostname,
            isp=isp,
            os=os,
            browser=browser,
            user_agent=user_agent_str,
            country=country
        )

        # تحديث أو إنشاء IPLog
        ip_log, created = IPLog.objects.get_or_create(ip_address=ip)
        if not created:
            ip_log.count += 1
            ip_log.save()

        return Response({'status': 'access_granted'}, status=201)
