import logging
from django.db import transaction
from inventory.models import (
    BottleType,
    BottleTransaction,
    BottleTransactionType,
    CustomerBottleBalance,
)

logger = logging.getLogger(__name__)


@transaction.atomic
def record_bottle_transaction(
    bottle_type, quantity, transaction_type, customer=None, order=None, user=None
):
    """
    Records a bottle movement and updates the customer's balance.
    """
    # 1. Create Transaction Log
    txn = BottleTransaction.objects.create(
        bottle_type=bottle_type,
        customer=customer,
        order=order,
        transaction_type=transaction_type,
        quantity=quantity,
        recorded_by=user,
    )

    # 2. Update Customer Balance if applicable
    if customer:
        balance_obj, _ = CustomerBottleBalance.objects.get_or_create(
            customer=customer, bottle_type=bottle_type
        )

        if transaction_type == BottleTransactionType.ISSUED:
            balance_obj.balance += quantity
        elif transaction_type == BottleTransactionType.RETURNED:
            balance_obj.balance -= quantity
        elif transaction_type == BottleTransactionType.BROKEN:
            balance_obj.balance -= quantity
            balance_obj.broken_balance += quantity

        balance_obj.save()

    return txn


@transaction.atomic
def issue_bottles(order):
    """
    Records bottles issued to a customer based on the products in their order.
    Called when an order is delivered.
    """
    for item in order.items.select_related("product__bottle_type").all():
        if item.product.is_returnable and item.product.bottle_type:
            record_bottle_transaction(
                bottle_type=item.product.bottle_type,
                quantity=item.quantity,
                transaction_type=BottleTransactionType.ISSUED,
                customer=order.customer,
                order=order,
            )
            logger.info(
                f"Issued {item.quantity} {item.product.bottle_type.name} for Order #{order.id}"
            )


@transaction.atomic
def record_bottle_return(
    customer, bottle_type, quantity, warehouse=None, order=None, driver=None, notes=""
):
    """
    Records bottles returned by a customer to a driver or directly to a warehouse.
    Updates the CustomerBottleBalance.
    """
    transaction_obj = record_bottle_transaction(
        bottle_type=bottle_type,
        quantity=quantity,
        transaction_type=BottleTransactionType.RETURNED,
        customer=customer,
        order=order,
        user=driver.user if driver else None,
    )

    logger.info(
        f"Recorded return of {quantity} {bottle_type.name} from {customer.name}"
    )
    return transaction_obj


def generate_bottle_qr(bottle_type, batch_size):
    """
    Stub for generating unique QR identifiers for bottles.
    """
    import uuid

    return [
        f"BTL-{bottle_type.id}-{uuid.uuid4().hex[:8].upper()}"
        for _ in range(batch_size)
    ]
