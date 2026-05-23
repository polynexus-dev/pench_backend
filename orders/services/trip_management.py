import datetime
import logging
from django.db import transaction
from django.utils import timezone

from orders.models import Route, RouteStatus, RouteStop, Order, OrderStatus, DeliveryLog
from routing.models import Driver

logger = logging.getLogger(__name__)


def lock_route_for_trip(route_id):
    """
    Locks a route, preventing any further product additions, removals, or quantity modifications.
    """
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        logger.error("lock_route_for_trip: Route %s not found.", route_id)
        return False

    route.is_locked = True
    route.save(update_fields=['is_locked'])
    
    DeliveryLog.objects.create(
        action="Route Locked",
        route=route,
        details=f"Route '{route.name}' has been locked. Modifying stops or order items is now disabled."
    )
    logger.info("Route %s locked successfully.", route_id)
    return True


def unlock_route_for_trip(route_id):
    """
    Unlocks a route, enabling product adjustments.
    """
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        logger.error("unlock_route_for_trip: Route %s not found.", route_id)
        return False

    route.is_locked = False
    route.save(update_fields=['is_locked'])
    
    DeliveryLog.objects.create(
        action="Route Unlocked",
        route=route,
        details=f"Route '{route.name}' has been unlocked. Modifying stops or order items is now enabled."
    )
    logger.info("Route %s unlocked successfully.", route_id)
    return True


def start_trip_for_route(route_id, driver_user):
    """
    Marks a route as started/in_progress, sets started_at, locks the route,
    sets the driver profile to busy/on_trip, and marks all associated orders as IN_TRANSIT.
    """
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        logger.error("start_trip_for_route: Route %s not found.", route_id)
        return None

    if route.driver != driver_user:
        logger.warning("User %s attempted to start trip on Route %s which is assigned to another driver.", driver_user, route_id)
        raise PermissionError("This route is assigned to another driver.")

    with transaction.atomic():
        route.status = RouteStatus.IN_PROGRESS
        route.started_at = timezone.now()
        route.is_locked = True  # Automatically lock the route once started
        route.save(update_fields=['status', 'started_at', 'is_locked'])

        # Update associated Driver Profile in routing app
        driver_profile = Driver.objects.filter(user=driver_user).first()
        if driver_profile:
            driver_profile.is_available = False
            driver_profile.on_trip = True
            driver_profile.save(update_fields=['is_available', 'on_trip'])

        # Mark all pending/confirmed orders in this route as IN_TRANSIT
        stops = route.stops.select_related('order')
        for stop in stops:
            if stop.order.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
                stop.order.status = OrderStatus.IN_TRANSIT
                stop.order.save(update_fields=['status'])

        DeliveryLog.objects.create(
            action="Trip Started",
            route=route,
            details=f"Driver {driver_user.get_full_name() or driver_user.username} started trip. Route status changed to IN_PROGRESS."
        )

    logger.info("Trip started successfully for Route %s by Driver %s", route_id, driver_user.username)
    return route


def stop_trip_for_route(route_id, driver_user):
    """
    Marks a route as completed/stopped, sets completed_at, marks is_completed = True,
    frees the driver, and marks any remaining IN_TRANSIT orders as UNDELIVERED.
    """
    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        logger.error("stop_trip_for_route: Route %s not found.", route_id)
        return None

    if route.driver != driver_user:
        logger.warning("User %s attempted to stop trip on Route %s which is assigned to another driver.", driver_user, route_id)
        raise PermissionError("This route is assigned to another driver.")

    with transaction.atomic():
        route.status = RouteStatus.COMPLETED
        route.completed_at = timezone.now()
        route.is_completed = True
        route.save(update_fields=['status', 'completed_at', 'is_completed'])

        # Free the driver
        driver_profile = Driver.objects.filter(user=driver_user).first()
        if driver_profile:
            driver_profile.is_available = True
            driver_profile.on_trip = False
            driver_profile.save(update_fields=['is_available', 'on_trip'])

        # Set any non-delivered, non-cancelled orders inside this route to UNDELIVERED
        stops = route.stops.select_related('order')
        undelivered_count = 0
        for stop in stops:
            if stop.order.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.IN_TRANSIT]:
                stop.order.status = OrderStatus.UNDELIVERED
                stop.order.delivered_at = timezone.now()
                stop.order.save(update_fields=['status', 'delivered_at'])
                undelivered_count += 1

                DeliveryLog.objects.create(
                    action="Order Force Undelivered",
                    route=route,
                    order=stop.order,
                    details="Order marked as undelivered due to manual trip completion/stop."
                )

        DeliveryLog.objects.create(
            action="Trip Completed",
            route=route,
            details=f"Driver completed trip. Marked {undelivered_count} remaining orders as undelivered."
        )

    logger.info("Trip completed successfully for Route %s. Undelivered orders: %d", route_id, undelivered_count)
    return route


def auto_stop_active_trips_at_noon():
    """
    Finds all active, incomplete routes for the current day and stops them.
    Toggles all remaining orders inside them to UNDELIVERED.
    """
    today = datetime.date.today()
    active_routes = Route.objects.filter(
        delivery_date=today,
        is_completed=False,
        status__in=[RouteStatus.PENDING, RouteStatus.STARTED, RouteStatus.IN_PROGRESS]
    ).select_related('driver')

    stopped_count = 0
    orders_affected = 0

    for route in active_routes:
        with transaction.atomic():
            route.status = RouteStatus.STOPPED
            route.is_completed = True
            route.completed_at = timezone.now()
            route.save(update_fields=['status', 'is_completed', 'completed_at'])

            # Free the driver profile
            if route.driver:
                driver_profile = Driver.objects.filter(user=route.driver).first()
                if driver_profile:
                    driver_profile.is_available = True
                    driver_profile.on_trip = False
                    driver_profile.save(update_fields=['is_available', 'on_trip'])

            # Update remaining orders to undelivered
            stops = route.stops.select_related('order')
            for stop in stops:
                if stop.order.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.IN_TRANSIT]:
                    stop.order.status = OrderStatus.UNDELIVERED
                    stop.order.delivered_at = timezone.now()
                    stop.order.save(update_fields=['status', 'delivered_at'])
                    orders_affected += 1

                    DeliveryLog.objects.create(
                        action="Noon Cutoff Stop",
                        route=route,
                        order=stop.order,
                        details="Order marked undelivered automatically at 12:00 PM cutoff."
                    )

            DeliveryLog.objects.create(
                action="Noon Cutoff Stop",
                route=route,
                details=f"Route automatically stopped at 12:00 PM cutoff. Affected orders: {orders_affected}"
            )
            stopped_count += 1

    return {"stopped_routes_count": stopped_count, "orders_affected_count": orders_affected}


def process_pre_delivery_product_cutoff():
    """
    Runs at 6:00 AM cutoff time on delivery day.
    Locks all routes scheduled for today.
    """
    today = datetime.date.today()
    routes_to_lock = Route.objects.filter(delivery_date=today, is_locked=False)
    
    locked_count = 0
    for route in routes_to_lock:
        route.is_locked = True
        route.save(update_fields=['is_locked'])
        
        DeliveryLog.objects.create(
            action="Route Locked",
            route=route,
            details="Route locked automatically at 6:00 AM pre-delivery cutoff."
        )
        locked_count += 1

    logger.info("Cutoff 6:00 AM processing completed. Locked %d routes.", locked_count)
    return {"locked_routes_count": locked_count}
