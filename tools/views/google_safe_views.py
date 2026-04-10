from datetime import timedelta

import requests
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.context_processors import csrf
from django.template.loader import render_to_string
from django.utils import timezone

from core.decorators import superuser_required

from ..forms import GoogleSafeCheckForm
from ..models import GoogleSafeCheck


def fetch_google_safe_status(url):
    headers = {
        'Host': 'transparencyreport.google.com',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:139.0) Gecko/20100101 Firefox/139.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Alt-Used': 'transparencyreport.google.com',
    }
    try:
        req = requests.get(
            f'https://transparencyreport.google.com/transparencyreport/api/v3/safebrowsing/status?site={url}',
            headers=headers, timeout=10)
        if 'true' in req.text:
            return "Red Flag"
        return "Working"
    except:
        return "Error"


@superuser_required
def google_safe_check_view(request):
    # ✅ فحص تلقائي للروابط القديمة كل ساعة
    one_hour_ago = timezone.now() - timedelta(hours=1)
    outdated_links = GoogleSafeCheck.objects.filter(last_checked__lt=one_hour_ago)
    for link in outdated_links:
        link.status = fetch_google_safe_status(link.url)
        link.last_checked = timezone.now()
        link.save()

    # ✅ حذف
    if request.method == 'POST':
        if 'delete_id' in request.POST:
            try:
                obj = GoogleSafeCheck.objects.get(id=request.POST['delete_id'])
                obj.delete()
                messages.success(request, f"Deleted: {obj.url}")
            except GoogleSafeCheck.DoesNotExist:
                messages.error(request, "Link not found.")
            return redirect('tools:google_safe_check')

        # ✅ إضافة
        form = GoogleSafeCheckForm(request.POST)
        if form.is_valid():
            obj, created = GoogleSafeCheck.objects.get_or_create(url=form.cleaned_data['url'])
            obj.status = fetch_google_safe_status(obj.url)
            obj.last_checked = timezone.now()
            obj.save()
            messages.success(request, f"Checked: {obj.url}")
            return redirect('tools:google_safe_check')
    else:
        form = GoogleSafeCheckForm()

    links = GoogleSafeCheck.objects.all().order_by('-last_checked')
    return render(request, 'tools/google_safe_check.html', {
        'form': form,
        'links': links
    })


@superuser_required
def google_safe_check_table_partial(request):
    links = GoogleSafeCheck.objects.all().order_by('-last_checked')

    context = {
        'links': links
    }
    context.update(csrf(request))  # ✅ هذا أهم سطر

    html = render_to_string('tools/partials/google_safe_check_table.html', context)
    return HttpResponse(html)
