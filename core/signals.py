"""Fire automation rules when an employee's status changes (any code path)."""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from . import automation
from .models import User


@receiver(pre_save, sender=User)
def _capture_old_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_status = sender.objects.only("status").get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=User)
def _fire_automation(sender, instance, created, **kwargs):
    old = getattr(instance, "_old_status", None)
    if not created and old is not None and old != instance.status:
        try:
            automation.fire_status_change(instance, old, instance.status)
        except Exception:
            pass  # automation must never block a save
