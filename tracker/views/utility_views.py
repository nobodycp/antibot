from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from core.decorators import superuser_required

from ..forms import AddBlockRuleForm, DeleteIpLogForm
from ..models import (
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
    BlockedSubnet,
    IPLog,
)

@require_POST
@superuser_required
def add_block_rule(request):
    if request.method == 'POST':
        form = AddBlockRuleForm(request.POST)
        if form.is_valid():
            block_type = form.cleaned_data["block_type"]
            block_value = form.cleaned_data["block_value"]
            if not block_type or not block_value:
                messages.error(request, "Both type and value are required.")
            else:
                block_rule_model_field = {
                    "ip": (BlockedIP, "ip_address"),
                    "isp": (BlockedISP, "isp"),
                    "hostname": (BlockedHostname, "hostname"),
                    "os": (BlockedOS, "os"),
                    "browser": (BlockedBrowser, "browser"),
                    "subnet": (BlockedSubnet, "cidr"),
                }

                spec = block_rule_model_field.get(block_type.lower())
                if spec:
                    model, value_field = spec
                    if not model.objects.filter(
                        **{f"{value_field}__iexact": block_value}
                    ).exists():
                        model.objects.create(**{value_field: block_value})
                        messages.success(request, f"✅ Block rule added: {block_value}")
                    else:
                        messages.warning(request, f"⚠️ Rule already exists: {block_value}")
                else:
                    messages.error(request, "Invalid rule type.")
        else:
            messages.error(request, "Both type and value are required.")

        # HTMX Response
        if request.headers.get("HX-Request"):
            return render(
                request,
                "core/partials/messages_list.html",
                {"messages": messages.get_messages(request)},
            )

        return redirect('tracker:denied_logs')
######################################################################
@superuser_required
def dinger_ip_view(request):
    if request.method == 'POST':
        dip_form = DeleteIpLogForm(request.POST)
        if dip_form.is_valid():
            ip_to_delete = dip_form.cleaned_data.get("delete_ip") or ""
        else:
            ip_to_delete = request.POST.get("delete_ip", "") or ""
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
    return render(request, 'tracker/dinger_ip.html', {'dingers': dingers})
