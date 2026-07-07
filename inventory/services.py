from django.db import transaction
from .models import BottleTransaction, BottleTransactionType, CustomerBottleBalance


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
