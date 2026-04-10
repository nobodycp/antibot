from datetime import timedelta

import requests
from django.contrib import messages
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from core.decorators import superuser_required
from core.htmx_navigation import render_page_or_shell

from ..forms import RedirectCheckForm
from ..models import RedirectCheck


def _refresh_stale_redirect_entries():
    """Recheck only rows older than one hour (same rule as full page GET)."""
    one_hour_ago = timezone.now() - timedelta(hours=1)
    for entry in RedirectCheck.objects.filter(last_checked__lt=one_hour_ago):
        entry.status = redirect_checker(entry.url, entry.keyword)
        entry.last_checked = timezone.now()
        entry.save(update_fields=["status", "last_checked"])


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


@superuser_required
def redirect_check_view(request):
    _refresh_stale_redirect_entries()

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
            return render(request, 'tools/redirect_check.html', {
                'form': RedirectCheckForm(),
                'entries': entries
            })
    else:
        form = RedirectCheckForm()

    entries = RedirectCheck.objects.all().order_by('-last_checked')
    ctx = {'form': form, 'entries': entries}
    return render_page_or_shell(
        request,
        full_template='tools/redirect_check.html',
        shell_template='tools/partials/shell/redirect_check.html',
        context=ctx,
    )


@superuser_required
def redirect_check_table_view(request):
    _refresh_stale_redirect_entries()

    entries = RedirectCheck.objects.all().order_by('-last_checked')

    context = {
        'entries': entries,
        'csrf_token': get_token(request)
    }
    html = render_to_string('tools/partials/redirect_check_table.html', context)
    return HttpResponse(html)
