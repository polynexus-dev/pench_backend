import datetime
import logging
from django.db import transaction
from django.db.models import Sum

from crm.models import Customer
from subscriptions.models import Subscription, SubscriptionStatus, SubscriptionItem
from inventory.models import Product, Stock, ProductAvailability, CustomerProductPrice
from orders.models import Order, OrderItem, OrderStatus, Route, RouteStop, DeliveryLog
from orders.services import create_optimized_route

logger = logging.getLogger(__name__)


def is_product_available(product, target_date):
    """
    Checks if a product is available on a specific date.
    Returns True if available, False otherwise.
    """
    # 1. Check ProductAvailability override first
    avail_override = ProductAvailability.objects.filter(product=product, date=target_date).first()
    if avail_override:
        return avail_override.is_available

    # 2. Check if product is active
    if not product.is_active:
        return False

    # 3. Check stock level (if any stock is defined, must be > 0)
    stock_sum = Stock.objects.filter(product=product).aggregate(total_qty=Sum('quantity')).get('total_qty')
    if stock_sum is not None and stock_sum <= 0:
        return False

    return True


def generate_daily_routes_for_date(target_date):
    """
    Core business logic: Generates orders and optimized routes for all active
    customer subscriptions on the target date.
    """
    logger.info("Starting Daily Route Generation for Date: %s", target_date)
    
    # 1. Fetch active subscriptions
    active_subscriptions = Subscription.objects.filter(
        status=SubscriptionStatus.ACTIVE,
        start_date__lte=target_date
    ).select_related('customer').prefetch_related('items__product')

    orders_created = 0
    skipped_duplicates = 0
    skipped_no_delivery = 0
    skipped_unavailable_products = 0

    created_order_ids = []

    for sub in active_subscriptions:
        # Check end date
        if sub.end_date and sub.end_date < target_date:
            continue

        # Check skip dates
        if sub.skip_dates.filter(skip_date=target_date).exists():
            skipped_no_delivery += 1
            continue

        # Check frequency logic
        if not sub.should_deliver_on(target_date):
            skipped_no_delivery += 1
            continue

        # Check for duplicate order for the same subscription and date
        if Order.objects.filter(subscription=sub, scheduled_delivery_date=target_date).exists():
            skipped_duplicates += 1
            continue

        # Check product availability for all subscription items
        items = list(sub.items.all())
        valid_items = []
        unavailable_items = []

        for item in items:
            if is_product_available(item.product, target_date):
                valid_items.append(item)
            else:
                unavailable_items.append(item.product.name)

        if not valid_items:
            skipped_unavailable_products += 1
            continue

        # If some items are unavailable, we notify/log and build order with remaining items
        if unavailable_items:
            details = f"Subscription #{sub.id[:8]}: Products {', '.join(unavailable_items)} are unavailable. Proceeding with remaining products."
            DeliveryLog.objects.create(
                action="Product Unavailable",
                details=details
            )
            logger.warning(details)

        # Create Order & OrderItems in atomic transaction
        with transaction.atomic():
            order = Order.objects.create(
                customer=sub.customer,
                subscription=sub,
                scheduled_delivery_date=target_date,
                status=OrderStatus.PENDING,
                delivery_address=sub.delivery_address or sub.customer.address,
                delivery_notes=sub.special_instructions
            )

            total_amount = 0
            for item in valid_items:
                # Resolve product price (check for custom customer product prices)
                custom_price_obj = CustomerProductPrice.objects.filter(
                    customer=sub.customer, 
                    product=item.product
                ).first()
                unit_price = custom_price_obj.custom_price if custom_price_obj else item.product.unit_price

                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    unit_price=unit_price
                )
                total_amount += item.quantity * unit_price

            order.total = total_amount
            order.save(update_fields=['total'])
            created_order_ids.append(order.id)
            orders_created += 1

    # 2. Group all pending orders (including newly created ones) for this date by Zone
    pending_orders = Order.objects.filter(
        scheduled_delivery_date=target_date,
        status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
        customer__zone__isnull=False
    ).select_related('customer__zone', 'customer__zone__assigned_driver')

    zone_orders = {}
    for order in pending_orders:
        zone = order.customer.zone
        if zone:
            zone_orders.setdefault(zone, []).append(order)

    routes_created = 0
    route_errors = []

    for zone, z_orders in zone_orders.items():
        driver = zone.assigned_driver
        if not driver:
            msg = f"Zone {zone.name}: No primary driver assigned. Skipping automatic route optimization."
            route_errors.append(msg)
            logger.warning(msg)
            continue

        # Check if an incomplete/active route already exists for this driver and date
        if Route.objects.filter(driver=driver, delivery_date=target_date, is_completed=False).exists():
            msg = f"Route for driver {driver.username} on {target_date} already exists. Skipping duplicate creation."
            logger.info(msg)
            continue

        order_ids = [str(o.id) for o in z_orders]
        route_count = Route.objects.filter(delivery_date=target_date).count()
        route_name = f"{zone.name} - {target_date.strftime('%Y-%m-%d')} #{route_count + 1}"

        try:
            route = create_optimized_route(route_name, driver, target_date, order_ids)
            routes_created += 1
            DeliveryLog.objects.create(
                action="Route Generated",
                route=route,
                details=f"Automatically generated and optimized route for Zone: {zone.name} with {len(order_ids)} stops."
            )
        except Exception as e:
            err_msg = f"Failed to generate route for Zone {zone.name}: {str(e)}"
            route_errors.append(err_msg)
            logger.error(err_msg)

    summary = {
        "date": str(target_date),
        "orders_created": orders_created,
        "skipped_duplicates": skipped_duplicates,
        "skipped_no_delivery": skipped_no_delivery,
        "skipped_unavailable_products": skipped_unavailable_products,
        "routes_created": routes_created,
        "route_errors": route_errors
    }
    logger.info("Daily Route Generation Completed: %s", summary)
    return summary


def regenerate_daily_routes_for_date(target_date):
    """
    Cancels and deletes existing incomplete routes and stops for the target date,
    and runs the generation process again.
    """
    logger.info("Regenerating daily routes for date: %s", target_date)
    
    with transaction.atomic():
        # Find incomplete routes for the target date
        routes_to_delete = Route.objects.filter(delivery_date=target_date, is_completed=False)
        
        for route in routes_to_delete:
            DeliveryLog.objects.create(
                action="Route Cancelled",
                details=f"Cancelling route '{route.name}' (ID: {route.id}) for regeneration."
            )
            # Delete associated stops (Order reverse lookup is deleted automatically)
            route.stops.all().delete()
            route.delete()

    return generate_daily_routes_for_date(target_date)
