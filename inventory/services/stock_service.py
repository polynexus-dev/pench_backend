import logging
from django.db import transaction
from inventory.models import Stock, Warehouse

logger = logging.getLogger(__name__)

class InsufficientStockError(Exception):
    """Raised when there is not enough stock in the warehouse to fulfill an order."""
    pass

@transaction.atomic
def deduct_stock_on_delivery(order):
    """
    Deducts stock for all items in the delivered order from the active warehouse.
    """
    warehouse = Warehouse.objects.filter(is_active=True).first()
    if not warehouse:
        warehouse = Warehouse.objects.create(
            name="Main Warehouse",
            address="Main Depot",
            is_active=True
        )
        logger.info("Created default Main Warehouse for stock management.")

    for item in order.items.select_related('product').all():
        # Lock the stock record for update to prevent race conditions
        stock_qs = Stock.objects.select_for_update().filter(
            product=item.product,
            warehouse=warehouse
        )
        
        if not stock_qs.exists():
            raise InsufficientStockError(
                f"No stock record found for product '{item.product.name}' in warehouse '{warehouse.name}'."
            )
            
        stock = stock_qs.first()
        if stock.quantity < item.quantity:
            raise InsufficientStockError(
                f"Insufficient stock for product '{item.product.name}'. "
                f"Required: {item.quantity}, Available: {stock.quantity}."
            )
            
        stock.quantity -= item.quantity
        stock.save()
        logger.info(
            f"Deducted {item.quantity} units of '{item.product.name}' from warehouse '{warehouse.name}'. "
            f"New stock level: {stock.quantity}."
        )
