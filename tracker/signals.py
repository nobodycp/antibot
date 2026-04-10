from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import RejectedVisitor

@receiver(post_delete, sender=RejectedVisitor)
def delete_all_same_ip(sender, instance, **kwargs):
    # Remove remaining denied rows for the same IP and owner (post-delete hook).
    # Scoped by owner so one tenant cannot wipe another user's rows for the same IP.
    if instance.owner_id:
        RejectedVisitor.objects.filter(
            ip_address=instance.ip_address,
            owner_id=instance.owner_id,
        ).delete()
