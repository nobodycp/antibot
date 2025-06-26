from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import os
import requests
from django.utils import timezone
from .models import GoogleSafeCheck, RedirectCheck, ArchiveFile
from .forms import GoogleSafeCheckForm, RedirectCheckForm, ArchiveFileForm
from datetime import timedelta
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.template.context_processors import csrf
from django.middleware.csrf import get_token

@login_required
def uploader_files_view(request):
    if request.method == 'POST':
        if 'delete_id' in request.POST:
            try:
                file_obj = ArchiveFile.objects.get(id=request.POST['delete_id'])

                # ✅ حذف الملف الفعلي من media/zips
                if file_obj.zip_file and os.path.isfile(file_obj.zip_file.path):
                    os.remove(file_obj.zip_file.path)

                # ✅ حذف السجل من قاعدة البيانات
                file_obj.delete()

                messages.error(request, "File deleted successfully.")
            except ArchiveFile.DoesNotExist:
                messages.error(request, "File not found.")

            return redirect('tools:uploader_files')

        # ✅ رفع ملف جديد
        form = ArchiveFileForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "File uploaded successfully.")
            return redirect('tools:uploader_files')

    else:
        form = ArchiveFileForm()

    files = ArchiveFile.objects.all().order_by('-id')
    return render(request, 'files.html', {
        'files': files,
        'form': form
    })

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

@login_required
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
    return render(request, 'google_safe_check.html', {
        'form': form,
        'links': links
    })

@login_required
def google_safe_check_table_partial(request):
    links = GoogleSafeCheck.objects.all().order_by('-last_checked')

    context = {
        'links': links
    }
    context.update(csrf(request))  # ✅ هذا أهم سطر

    html = render_to_string('partials/google_safe_check_table.html', context)
    return HttpResponse(html)

def redirect_checker(link, keyword):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:139.0) Gecko/20100101 Firefox/139.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
    }
    try:
        req = requests.get(link, headers=headers, allow_redirects=False, timeout=10)
        if req.status_code == 302:
            location = req.headers.get("Location", "")
            return "working" if keyword in location else "not working"
        return "error"
    except:
        return "error"

@login_required
def redirect_check_view(request):
    one_hour_ago = timezone.now() - timedelta(hours=1)
    for entry in RedirectCheck.objects.filter(last_checked__lt=one_hour_ago):
        entry.status = redirect_checker(entry.url, entry.keyword)
        entry.last_checked = timezone.now()
        entry.save()

    if request.method == 'POST':
        if 'delete_id' in request.POST:
            try:
                obj = RedirectCheck.objects.get(id=request.POST['delete_id'])
                obj.delete()
                messages.error(request, f"Deleted: {obj.url}")
            except RedirectCheck.DoesNotExist:
                messages.error(request, "Entry not found.")
            return redirect('tools:redirect_check')

        form = RedirectCheckForm(request.POST)
        if form.is_valid():
            obj, created = RedirectCheck.objects.get_or_create(
                url=form.cleaned_data['url'],
                keyword=form.cleaned_data['keyword']
            )
            obj.status = redirect_checker(obj.url, obj.keyword)
            obj.last_checked = timezone.now()
            obj.save()
            messages.success(request, f"Checked: {obj.url}")
            # إعادة تحميل الصفحة بالكامل ليظهر الرابط الجديد مباشرة
            entries = RedirectCheck.objects.all().order_by('-last_checked')
            return render(request, 'redirect_check.html', {
                'form': RedirectCheckForm(),
                'entries': entries
            })
    else:
        form = RedirectCheckForm()

    entries = RedirectCheck.objects.all().order_by('-last_checked')
    return render(request, 'redirect_check.html', {
        'form': form,
        'entries': entries
    })

@login_required
def redirect_check_table_view(request):
    entries = RedirectCheck.objects.all().order_by('-last_checked')
    for entry in entries:
        entry.status = redirect_checker(entry.url, entry.keyword)
        entry.last_checked = timezone.now()
        entry.save(update_fields=['status', 'last_checked'])

    context = {
        'entries': entries,
        'csrf_token': get_token(request)
    }
    html = render_to_string('redirect_check_table.html', context)
    return HttpResponse(html)
