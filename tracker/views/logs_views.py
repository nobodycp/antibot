from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.decorators import superuser_required

from ..helpers.logs_views_helper import (
    apply_country_code_filter,
    apply_visitor_like_fields_search,
    list_search_q,
    logs_list_page_context,
    logs_partial_context,
    paginated_page,
    visitor_logs_search_q,
)
from ..models import AllowedCountry, RejectedVisitor, Visitor


@superuser_required
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
            q = list_search_q(request)
            queryset = apply_country_code_filter(
                AllowedCountry.objects.all().order_by("code"), q
            )
            page_obj = paginated_page(request, queryset, force_first_page=True)
            return render(
                request,
                "tracker/partials/allowed_country_partial.html",
                logs_partial_context("tracker/allowed_countries", page_obj, q, request),
            )

        return redirect('tracker:allowed_country')

    q = list_search_q(request)
    queryset = apply_country_code_filter(
        AllowedCountry.objects.all().order_by("code"), q
    )
    page_obj = paginated_page(request, queryset)
    return render(
        request,
        "tracker/allowed_country.html",
        logs_list_page_context("tracker/allowed_countries", page_obj, q),
    )


@superuser_required
def allowed_country_partial(request):
    q = list_search_q(request)
    queryset = apply_country_code_filter(
        AllowedCountry.objects.all().order_by("code"), q
    )
    page_obj = paginated_page(request, queryset)
    return render(
        request,
        "tracker/partials/allowed_country_partial.html",
        logs_partial_context("tracker/allowed_countries", page_obj, q, request),
    )


@superuser_required
def allowed_country_table(request):
    q = list_search_q(request)
    queryset = apply_country_code_filter(
        AllowedCountry.objects.all().order_by("code"), q
    )
    page_obj = paginated_page(request, queryset)
    return render(
        request,
        "tracker/partials/allowed_country_table.html",
        logs_list_page_context("tracker/allowed_countries", page_obj, q),
    )


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
            q = visitor_logs_search_q(request)
            queryset = apply_visitor_like_fields_search(
                Visitor.objects.all().order_by("-timestamp"), q
            )
            page_obj = paginated_page(request, queryset, force_first_page=True)
            return render(
                request,
                "tracker/partials/allowed_logs_partial.html",
                logs_partial_context("logs", page_obj, q, request),
            )

        return redirect('tracker:allowed_logs')

    q = visitor_logs_search_q(request)
    queryset = apply_visitor_like_fields_search(
        Visitor.objects.all().order_by("-timestamp"), q
    )
    page_obj = paginated_page(request, queryset)
    return render(
        request,
        "tracker/allowed_logs.html",
        logs_list_page_context("logs", page_obj, q),
    )


@login_required
def allowed_logs_partial(request):
    q = visitor_logs_search_q(request)
    queryset = apply_visitor_like_fields_search(
        Visitor.objects.all().order_by("-timestamp"), q
    )
    page_obj = paginated_page(request, queryset)
    return render(
        request,
        "tracker/partials/allowed_logs_partial.html",
        logs_partial_context("logs", page_obj, q, request),
    )


@login_required
def allowed_logs_table(request):
    q = visitor_logs_search_q(request)
    queryset = apply_visitor_like_fields_search(
        Visitor.objects.all().order_by("-timestamp"), q
    )
    page_obj = paginated_page(request, queryset)
    return render(
        request,
        "tracker/partials/allowed_logs_table.html",
        logs_list_page_context("logs", page_obj, q),
    )


######################################################################
@superuser_required
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
            q = visitor_logs_search_q(request)
            queryset = apply_visitor_like_fields_search(
                RejectedVisitor.objects.exclude(reason="Subnet").order_by("-timestamp"),
                q,
            )
            page_obj = paginated_page(request, queryset, per_page=10, force_first_page=True)
            return render(
                request,
                "tracker/partials/denied_logs_partial.html",
                logs_partial_context("logs", page_obj, q, request),
            )

        return redirect('tracker:denied_logs')

    q = visitor_logs_search_q(request)
    queryset = apply_visitor_like_fields_search(
        RejectedVisitor.objects.exclude(reason="Subnet").order_by("-timestamp"),
        q,
    )
    page_obj = paginated_page(request, queryset, per_page=10)
    return render(
        request,
        "tracker/denied_logs.html",
        logs_list_page_context("logs", page_obj, q),
    )


@superuser_required
def denied_logs_partial(request):
    q = visitor_logs_search_q(request)
    queryset = apply_visitor_like_fields_search(
        RejectedVisitor.objects.exclude(reason="Subnet").order_by("-timestamp"),
        q,
    )
    page_obj = paginated_page(request, queryset, per_page=10)
    return render(
        request,
        "tracker/partials/denied_logs_partial.html",
        logs_partial_context("logs", page_obj, q, request),
    )


@superuser_required
def denied_logs_table(request):
    q = visitor_logs_search_q(request)
    queryset = apply_visitor_like_fields_search(
        RejectedVisitor.objects.exclude(reason="Subnet").order_by("-timestamp"),
        q,
    )
    page_obj = paginated_page(request, queryset, per_page=10)
    return render(
        request,
        "tracker/partials/denied_logs_table.html",
        logs_list_page_context("logs", page_obj, q),
    )
