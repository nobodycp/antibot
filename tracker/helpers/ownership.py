"""Querysets scoped by log row owner (superuser sees all)."""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from ..models import IPInfo, IPLog, RejectedVisitor, Visitor


def visitor_logs_queryset(user: AbstractUser):
    qs = Visitor.objects.all()
    if not user.is_superuser:
        qs = qs.filter(owner=user)
    return qs


def rejected_logs_queryset(user: AbstractUser):
    qs = RejectedVisitor.objects.exclude(reason="Subnet")
    if not user.is_superuser:
        qs = qs.filter(owner=user)
    return qs


def ip_info_queryset(user: AbstractUser):
    qs = IPInfo.objects.all()
    if not user.is_superuser:
        qs = qs.filter(owner=user)
    return qs


def ip_log_queryset(user: AbstractUser):
    qs = IPLog.objects.all()
    if not user.is_superuser:
        qs = qs.filter(owner=user)
    return qs
