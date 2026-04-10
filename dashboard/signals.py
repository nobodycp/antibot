import secrets

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserAPIKey, UserProfile


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=get_user_model())
def save_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)
    instance.profile.save()


@receiver(post_save, sender=get_user_model())
def ensure_user_has_api_key(sender, instance, **kwargs):
    """Ensure each user has a tracker API key (OneToOne); no-op if row exists."""
    UserAPIKey.objects.get_or_create(
        user=instance,
        defaults={"api_key": secrets.token_urlsafe(32)},
    )
