"""Per-user WhatsApp account ownership registry."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from tools.models import WhatsAppAccount, WhatsAppCheckJob
from tools.services import whatsapp_service as wa

User = get_user_model()


def is_wa_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_superuser)


def sync_accounts_from_disk() -> None:
    """Ensure each session folder has a DB registry row."""
    disk_names = {a.name for a in wa.list_accounts()}
    existing = set(WhatsAppAccount.objects.values_list("account_name", flat=True))
    for name in sorted(disk_names - existing):
        WhatsAppAccount.objects.create(account_name=name, owner=None)


def register_account(account_name: str, owner) -> WhatsAppAccount:
    name = wa.validate_account_name(account_name)
    record, created = WhatsAppAccount.objects.get_or_create(
        account_name=name,
        defaults={"owner": owner},
    )
    if not created and owner is not None and record.owner_id is None:
        record.owner = owner
        record.save(update_fields=["owner"])
    return record


def unregister_account(account_name: str) -> None:
    WhatsAppAccount.objects.filter(account_name=account_name).delete()


def user_can_access_account(user, account_name: str) -> bool:
    if is_wa_admin(user):
        return True
    return WhatsAppAccount.objects.filter(
        account_name=account_name, owner=user
    ).exists()


def visible_account_queryset(user):
    sync_accounts_from_disk()
    if is_wa_admin(user):
        return WhatsAppAccount.objects.select_related("owner").all()
    return WhatsAppAccount.objects.filter(owner=user)


def disk_accounts_for_user(user) -> list[wa.WhatsAppAccountInfo]:
    sync_accounts_from_disk()
    accounts = wa.list_accounts()
    if is_wa_admin(user):
        return accounts
    owned = set(visible_account_queryset(user).values_list("account_name", flat=True))
    return [a for a in accounts if a.name in owned]


def linked_account_names_for_user(user) -> list[str]:
    return sorted(a.name for a in disk_accounts_for_user(user) if a.has_session)


def account_choices_for_form(user) -> list[tuple[str, str]]:
    """Checkbox choices: (account_name, label). Admin labels include owner username."""
    linked = linked_account_names_for_user(user)
    if not linked:
        return []
    if not is_wa_admin(user):
        return [(n, n) for n in linked]

    owner_map = dict(
        WhatsAppAccount.objects.filter(account_name__in=linked)
        .select_related("owner")
        .values_list("account_name", "owner__username")
    )
    choices: list[tuple[str, str]] = []
    for name in linked:
        owner_name = owner_map.get(name)
        label = f"{name} ({owner_name})" if owner_name else f"{name} (unassigned)"
        choices.append((name, label))
    return choices


def owner_username_for(account_name: str) -> str | None:
    try:
        record = WhatsAppAccount.objects.select_related("owner").get(
            account_name=account_name
        )
    except WhatsAppAccount.DoesNotExist:
        return None
    return record.owner.username if record.owner_id else None


def jobs_queryset_for_user(user):
    qs = WhatsAppCheckJob.objects.select_related("user")
    if is_wa_admin(user):
        return qs
    return qs.filter(user=user)
