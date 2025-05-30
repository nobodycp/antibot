from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import RejectedVisitor

@receiver(post_delete, sender=RejectedVisitor)
def delete_all_same_ip(sender, instance, **kwargs):
    # نحذف باقي السجلات بنفس IP (عدا هذا اللي انحذف أصلاً)
    RejectedVisitor.objects.filter(ip_address=instance.ip_address).delete()
