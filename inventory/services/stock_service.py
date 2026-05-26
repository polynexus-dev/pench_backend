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
            name="Main Warehouse", address="Main Depot", is_active=True
        )
        logger.info("Created default Main Warehouse for stock management.")

    for item in order.items.select_related(
        "product", "product__raw_material", "product__bottle_type"
    ).all():
        product = item.product
        raw_mat = product.raw_material

        # If product is not associated with a raw material, no warehouse stock deduction is tracked
        if not raw_mat:
            logger.info(
                f"Product '{product.name}' has no raw material link. Skipping stock deduction."
            )
            continue

        # Convert quantity to raw material units based on bottle size (ml to L)
        volume_ml = (
            product.bottle_type.volume_ml
            if (product.bottle_type and product.is_returnable)
            else 1000
        )
        # If measured in Litres, convert ml to L. Otherwise, treat as raw pieces/kg
        factor = float(volume_ml) / 1000.0 if raw_mat.unit.lower() == "litre" else 1.0
        deduct_qty = int(round(item.quantity * factor))

        # Lock the stock record for update to prevent race conditions
        stock_qs = Stock.objects.select_for_update().filter(
            raw_material=raw_mat, warehouse=warehouse
        )

        if not stock_qs.exists():
            # If stock record doesn't exist, initialize it at 0 to avoid breaking dispatches
            stock = Stock.objects.create(
                raw_material=raw_mat, warehouse=warehouse, quantity=0
            )
        else:
            stock = stock_qs.first()

        stock.quantity -= deduct_qty
        stock.save()

        # Record outbound movement
        from inventory.models import StockMovement, StockMovementType

        StockMovement.objects.create(
            warehouse=warehouse,
            raw_material=raw_mat,
            movement_type=StockMovementType.OUTBOUND,
            quantity=-deduct_qty,
            reference=f"Order ID: {order.id}",
            notes=f"Auto deduction for delivered Order #{order.id} ({item.quantity} x {product.name}).",
        )

        logger.info(
            f"Deducted {deduct_qty} {raw_mat.unit} of raw material '{raw_mat.name}' for product '{product.name}' from warehouse '{warehouse.name}'. "
            f"New stock level: {stock.quantity}."
        )
