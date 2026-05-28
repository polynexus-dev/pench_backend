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
    avail_override = ProductAvailability.objects.filter(
        product=product, date=target_date
    ).first()
    if avail_override:
        return avail_override.is_available

    # 2. Check if product is active
    if not product.is_active:
        return False

    # 3. Check stock level (if any stock is defined, must be > 0)
    if product.raw_material:
        stock_sum = (
            Stock.objects.filter(raw_material=product.raw_material)
            .aggregate(total_qty=Sum("quantity"))
            .get("total_qty")
        )
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
    active_subscriptions = (
        Subscription.objects.filter(
            status=SubscriptionStatus.ACTIVE, start_date__lte=target_date
        )
        .select_related("customer")
        .prefetch_related("items__product")
    )

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
        if Order.objects.filter(
            subscription=sub, scheduled_delivery_date=target_date
        ).exists():
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
            DeliveryLog.objects.create(action="Product Unavailable", details=details)
            logger.warning(details)

        # Create Order & OrderItems in atomic transaction
        with transaction.atomic():
            order = Order.objects.create(
                customer=sub.customer,
                subscription=sub,
                scheduled_delivery_date=target_date,
                status=OrderStatus.PENDING,
                delivery_address=sub.delivery_address or sub.customer.address,
                delivery_notes=sub.special_instructions,
            )

            total_amount = 0
            for item in valid_items:
                # Resolve product price (check for custom customer product prices)
                custom_price_obj = CustomerProductPrice.objects.filter(
                    customer=sub.customer, product=item.product
                ).first()
                unit_price = (
                    custom_price_obj.custom_price
                    if custom_price_obj
                    else item.product.unit_price
                )

                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    quantity=item.quantity,
                    unit_price=unit_price,
                )
                total_amount += item.quantity * unit_price

            order.total = total_amount
            order.save(update_fields=["total"])
            created_order_ids.append(order.id)
            orders_created += 1

    # 2. Group all pending orders (including newly created ones) for this date by Zone's driver's Warehouse (Logistical Hub Affinity)
    pending_orders = Order.objects.filter(
        scheduled_delivery_date=target_date,
        status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
        customer__zone__isnull=False,
    ).select_related("customer__zone", "customer__zone__assigned_driver")

    from routing.models import Driver

    # Pre-fetch all driver profiles to map driver User IDs to Driver profiles and Warehouses
    driver_profiles = {
        dp.user_id: dp for dp in Driver.objects.select_related("warehouse").all()
    }

    # Group orders by (warehouse, driver_user, driver_profile)
    grouped_orders = {}
    routes_created = 0
    route_errors = []

    for order in pending_orders:
        zone = order.customer.zone
        if not zone:
            continue

        driver_user = zone.assigned_driver
        if not driver_user:
            msg = f"Zone {zone.name}: No primary driver assigned. Skipping automatic route optimization."
            if msg not in route_errors:
                route_errors.append(msg)
                logger.warning(msg)
            continue

        driver_profile = driver_profiles.get(driver_user.id)
        if not driver_profile:
            msg = f"Zone {zone.name}: Primary driver '{driver_user.username}' has no Driver profile. Skipping automatic route optimization."
            if msg not in route_errors:
                route_errors.append(msg)
                logger.warning(msg)
            continue

        warehouse = driver_profile.warehouse
        if not warehouse:
            msg = f"Driver '{driver_user.username}' (Zone: {zone.name}) is not associated with any warehouse. Enforcing logistical hub affinity: Skipping route generation."
            if msg not in route_errors:
                route_errors.append(msg)
                logger.warning(msg)
            continue

        # Group by the unique combination of warehouse, driver User instance, and Driver profile instance
        key = (warehouse, driver_user, driver_profile)
        grouped_orders.setdefault(key, []).append(order)

    for (warehouse, driver_user, driver_profile), z_orders in grouped_orders.items():
        # Check if an incomplete/active route already exists for this driver (User) and date
        if Route.objects.filter(
            driver=driver_user, delivery_date=target_date, is_completed=False
        ).exists():
            msg = f"Route for driver {driver_user.username} on {target_date} already exists. Skipping duplicate creation."
            logger.info(msg)
            continue

        # Resolve warehouse_location coordinates for pathfinder depot
        warehouse_location = None
        if warehouse.latitude is not None and warehouse.longitude is not None:
            warehouse_location = {
                "longitude": float(warehouse.longitude),
                "latitude": float(warehouse.latitude),
            }

        order_ids = [str(o.id) for o in z_orders]
        route_count = Route.objects.filter(delivery_date=target_date).count()
        route_name = f"{warehouse.name} - {driver_user.get_full_name() or driver_user.username} - {target_date.strftime('%Y-%m-%d')} #{route_count + 1}"

        try:
            route = create_optimized_route(
                route_name,
                driver_user,  # Pass the User instance for orders.models.Route.driver
                target_date,
                order_ids,
                warehouse=warehouse,
                warehouse_location=warehouse_location,
            )
            routes_created += 1
            DeliveryLog.objects.create(
                action="Route Generated",
                route=route,
                details=f"Automatically generated and optimized route for Warehouse: {warehouse.name}, Driver: {driver_user.username} with {len(order_ids)} stops.",
            )
        except Exception as e:
            err_msg = f"Failed to generate route for Warehouse {warehouse.name}, Driver {driver_user.username}: {str(e)}"
            route_errors.append(err_msg)
            logger.error(err_msg)

    summary = {
        "date": str(target_date),
        "orders_created": orders_created,
        "skipped_duplicates": skipped_duplicates,
        "skipped_no_delivery": skipped_no_delivery,
        "skipped_unavailable_products": skipped_unavailable_products,
        "routes_created": routes_created,
        "route_errors": route_errors,
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
        routes_to_delete = Route.objects.filter(
            delivery_date=target_date, is_completed=False
        )

        for route in routes_to_delete:
            DeliveryLog.objects.create(
                action="Route Cancelled",
                details=f"Cancelling route '{route.name}' (ID: {route.id}) for regeneration.",
            )
            # Delete associated stops (Order reverse lookup is deleted automatically)
            route.stops.all().delete()
            route.delete()

    return generate_daily_routes_for_date(target_date)


def add_order_to_active_route_if_pending(order):
    """
    If a pending route exists for the order's customer's zone driver on the order's
    delivery date, and the route has not started yet, automatically add the order
    to the route and re-optimize the stops and geometry.
    """
    from orders.services.optimizer import optimize_route_ortools
    from django.db import transaction

    # 1. Resolve delivery date, customer zone, and driver
    delivery_date = order.scheduled_delivery_date
    if not delivery_date:
        return

    customer = getattr(order, "customer", None)
    if not customer or not customer.zone:
        return

    driver_user = customer.zone.assigned_driver
    if not driver_user:
        return

    # 2. Check if there is an existing, incomplete, unstarted route for this driver and date
    route = Route.objects.filter(
        driver=driver_user,
        delivery_date=delivery_date,
        is_completed=False,
        started_at__isnull=True
    ).first()

    if not route:
        return

    # 3. Get all order IDs currently in the route stops, plus this new order ID
    existing_order_ids = list(route.stops.values_list("order_id", flat=True))
    
    # If the order is already in the route stops, we don't need to do anything
    if order.id in existing_order_ids:
        return

    all_order_ids = [str(oid) for oid in existing_order_ids] + [str(order.id)]

    # 4. Resolve driver profile & warehouse location for pathfinder depot
    driver_profile = getattr(driver_user, "driver_profile", None)
    if not driver_profile:
        from routing.models import Driver
        driver_profile = Driver.objects.filter(user=driver_user).first()

    warehouse_location = None
    if driver_profile and driver_profile.warehouse:
        warehouse = driver_profile.warehouse
        if warehouse.latitude is not None and warehouse.longitude is not None:
            warehouse_location = {
                "longitude": float(warehouse.longitude),
                "latitude": float(warehouse.latitude),
            }

    # 5. Optimize the updated set of orders
    try:
        optimized_orders, road_geometry = optimize_route_ortools(
            all_order_ids, start_point=warehouse_location
        )
        
        with transaction.atomic():
            # Delete old stops for this route and recreate them in optimized order
            route.stops.all().delete()
            route.geometry = road_geometry
            route.save(update_fields=["geometry"])
            
            stops = []
            for index, opt_order in enumerate(optimized_orders):
                stops.append(RouteStop(route=route, order=opt_order, sequence_number=index + 1))
            RouteStop.objects.bulk_create(stops)
            
            # Log the change
            DeliveryLog.objects.create(
                action="Route Updated",
                route=route,
                order=order,
                details=f"Automatically added order #{order.id} to route and re-optimized stops before route start.",
            )
    except Exception as e:
        logger.error(f"Failed to automatically add order #{order.id} to route: {str(e)}")

