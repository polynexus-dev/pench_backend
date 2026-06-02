import logging
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="routing.TrackingEvent")
def on_tracking_event_saved(sender, instance, created, **kwargs):
    """
    Fires after every TrackingEvent save.

    When status == 'delivered' and a specific order is linked:
        1. Deduct stock for all order items (atomic)
        2. Auto-generate invoice for the order (with GST breakdown)
        3. Record bottle issuance (if applicable)
        4. Auto-debit from customer wallet (if balance exists)
        5. Update order status
        6. Trigger daily reconciliation check

    Both operations run inside a single transaction.
    """
    if not created:
        return
    if instance.status != "delivered":
        return
    if not instance.order:
        return

    order = instance.order

    try:
        with transaction.atomic():
            from inventory.services import deduct_stock_on_delivery
            from inventory.services.bottle_service import issue_bottles
            from routing.services.reconciliation_service import (
                generate_daily_reconciliation,
            )
            from orders.models import OrderStatus

            # 1. Deduct stock
            deduct_stock_on_delivery(order)

            # 2. Issue bottles (dairy specific asset tracking)
            issue_bottles(order)

            # 3. Update order status
            order.status = OrderStatus.DELIVERED
            order.save(update_fields=["status"])

            # 4. Update/Generate daily reconciliation for the route
            generate_daily_reconciliation(instance.route.id)

            logger.info(
                "Delivery complete hooks processed for order %s. Route: %s",
                order.id,
                instance.route.id,
            )

    except Exception as exc:
        logger.exception("Post-delivery hook failed for order %s: %s", order.id, exc)
        # Re-raise so the caller knows something went wrong
        raise
