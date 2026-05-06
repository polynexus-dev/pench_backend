import logging
from django.db import transaction
from inventory.models import (
    BottleType, BottleInventory, BottleTransaction, BottleTransactionType
)

logger = logging.getLogger(__name__)

@transaction.atomic
def issue_bottles(order):
    """
    Records bottles issued to a customer based on the products in their order.
    Called when an order is delivered.
    """
    for item in order.items.select_related('product__bottle_type').all():
        if item.product.is_returnable and item.product.bottle_type:
            BottleTransaction.objects.create(
                bottle_type=item.product.bottle_type,
                customer=order.customer,
                order=order,
                transaction_type=BottleTransactionType.ISSUED,
                quantity=item.quantity,
                notes=f"Issued for Order #{order.id}"
            )
            # Logic to decrement filled_count from warehouse inventory could go here
            logger.info(f"Issued {item.quantity} {item.product.bottle_type.name} for Order #{order.id}")

@transaction.atomic
def record_bottle_return(customer, bottle_type, quantity, warehouse, order=None, driver=None, notes="", qr_codes=None):
    """
    Records bottles returned by a customer to a driver or directly to a warehouse.
    Updates the empty_count in BottleInventory.
    """
    transaction = BottleTransaction.objects.create(
        bottle_type=bottle_type,
        customer=customer,
        order=order,
        transaction_type=BottleTransactionType.RETURNED,
        quantity=quantity,
        qr_codes=qr_codes or [],
        notes=notes,
        recorded_by=driver.user if driver else None
    )

    # Update warehouse inventory
    inventory, created = BottleInventory.objects.get_or_create(
        bottle_type=bottle_type,
        warehouse=warehouse
    )
    inventory.empty_count += quantity
    inventory.save(update_fields=['empty_count'])

    logger.info(f"Recorded return of {quantity} {bottle_type.name} from {customer.name} to {warehouse.name}")
    return transaction

def generate_bottle_qr(bottle_type, batch_size):
    """
    Stub for generating unique QR identifiers for bottles.
    In a real system, this might interface with a label printing service.
    """
    import uuid
    return [f"BTL-{bottle_type.id}-{uuid.uuid4().hex[:8].upper()}" for _ in range(batch_size)]
