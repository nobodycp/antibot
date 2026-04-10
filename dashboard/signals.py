import secrets

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserAPIKey


@receiver(post_save, sender=get_user_model())
def create_user_api_key_on_signup(sender, instance, created, **kwargs):
    if created:
        UserAPIKey.objects.get_or_create(
            user=instance,
            defaults={"api_key": secrets.token_urlsafe(32)},
        )
