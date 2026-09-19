import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import InventoryBatch

logger = logging.getLogger('inventory.alerts')


@receiver(pre_save, sender=InventoryBatch)
def capture_previous_quantity(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_qty_kg = None
        return
    instance._previous_qty_kg = sender.objects.filter(pk=instance.pk).values_list('qty_kg', flat=True).first()


@receiver(post_save, sender=InventoryBatch)
def log_low_stock_alert(sender, instance, created, **kwargs):
    previous_qty = getattr(instance, '_previous_qty_kg', None)
    crossed_threshold = previous_qty is None or previous_qty >= 5000
    if instance.qty_kg < 5000 and crossed_threshold:
        logger.warning(
            'LOW_STOCK_ALERT batch_id=%s rice_type=%s qty_kg=%s threshold_kg=5000',
            instance.pk,
            instance.rice_type,
            instance.qty_kg,
        )
