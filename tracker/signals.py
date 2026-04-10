from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (
    AllowedCountry,
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
    BlockedSubnet,
    RejectedVisitor,
)
from .rule_cache_invalidation import invalidate_tracker_rule_caches

_RULE_CACHE_MODELS = (
    AllowedCountry,
    BlockedIP,
    BlockedISP,
    BlockedSubnet,
    BlockedOS,
    BlockedBrowser,
    BlockedHostname,
)


def _invalidate_rule_caches_on_change(**kwargs):
    invalidate_tracker_rule_caches()


for _model in _RULE_CACHE_MODELS:
    post_save.connect(_invalidate_rule_caches_on_change, sender=_model)
    post_delete.connect(_invalidate_rule_caches_on_change, sender=_model)


@receiver(post_delete, sender=RejectedVisitor)
def delete_all_same_ip(sender, instance, **kwargs):
    # Remove remaining denied rows for the same IP and owner (post-delete hook).
    # Scoped by owner so one tenant cannot wipe another user's rows for the same IP.
    if instance.owner_id:
        RejectedVisitor.objects.filter(
            ip_address=instance.ip_address,
            owner_id=instance.owner_id,
        ).delete()
