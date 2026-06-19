import datetime
import logging
from django.db import transaction
from django.utils import timezone

from orders.models import Route, RouteStatus, RouteStop, Order, OrderStatus, DeliveryLog
from routing.models import Driver
from notifications.services import send_push_notification

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
    route.save(update_fields=["is_locked"])

    DeliveryLog.objects.create(
        action="Route Locked",
        route=route,
        details=f"Route '{route.name}' has been locked. Modifying stops or order items is now disabled.",
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
    route.save(update_fields=["is_locked"])

    DeliveryLog.objects.create(
        action="Route Unlocked",
        route=route,
        details=f"Route '{route.name}' has been unlocked. Modifying stops or order items is now enabled.",
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

    is_manager = (
        driver_user.is_superuser
        or getattr(driver_user, "is_erp_user", False)
        or driver_user.groups.filter(
            name__in=["Logistics_Managers", "ERP_Admins"]
        ).exists()
    )
    is_assigned = (route.driver == driver_user) or route.additional_drivers.filter(
        id=driver_user.id
    ).exists()
    if not is_assigned and not is_manager:
        logger.warning(
            "User %s attempted to start trip on Route %s which is assigned to another driver.",
            driver_user,
            route_id,
        )
        raise PermissionError("This route is assigned to another driver.")

    with transaction.atomic():
        route.status = RouteStatus.IN_PROGRESS
        route.started_at = timezone.now()
        route.completed_at = None
        route.is_completed = False
        route.is_locked = True  # Automatically lock the route once started
        route.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "is_completed",
                "is_locked",
            ]
        )

        # Update associated Driver Profile in routing app
        if route.driver:
            driver_profile = Driver.objects.filter(user=route.driver).first()
            if driver_profile:
                driver_profile.is_available = False
                driver_profile.on_trip = True
                driver_profile.save(update_fields=["is_available", "on_trip"])

        # Mark all pending/confirmed orders in this route as IN_TRANSIT
        stops = route.stops.select_related("order")
        for stop in stops:
            if stop.order.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
                stop.order.status = OrderStatus.IN_TRANSIT
                stop.order.save(update_fields=["status"])

                # Send out-for-delivery push notification
                order = stop.order
                if order.customer and order.customer.user:
                    title = "🚚 Out for Delivery!"
                    body = "Exciting news! Your Pench order is on its way. See you soon! 🚚✨"
                    try:
                        send_push_notification(
                            user=order.customer.user,
                            title=title,
                            body=body,
                            order=order,
                            notification_type='order_status'
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to send dispatch notification for order %s: %s",
                            order.id,
                            e,
                        )

        DeliveryLog.objects.create(
            action="Trip Started",
            route=route,
            details=f"Driver {driver_user.get_full_name() or driver_user.username} started trip. Route status changed to IN_PROGRESS.",
        )

    logger.info(
        "Trip started successfully for Route %s by Driver %s",
        route_id,
        driver_user.username,
    )
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

    is_manager = (
        driver_user.is_superuser
        or getattr(driver_user, "is_erp_user", False)
        or driver_user.groups.filter(
            name__in=["Logistics_Managers", "ERP_Admins"]
        ).exists()
    )
    is_assigned = (route.driver == driver_user) or route.additional_drivers.filter(
        id=driver_user.id
    ).exists()
    if not is_assigned and not is_manager:
        logger.warning(
            "User %s attempted to stop trip on Route %s which is assigned to another driver.",
            driver_user,
            route_id,
        )
        raise PermissionError("This route is assigned to another driver.")

    with transaction.atomic():
        route.status = RouteStatus.COMPLETED
        route.completed_at = timezone.now()
        route.is_completed = True
        route.save(update_fields=["status", "completed_at", "is_completed"])

        try:
            update_route_metrics(route)
        except Exception as e:
            logger.error("Failed to update route metrics in stop_trip_for_route: %s", e)

        # Free the driver
        if route.driver:
            driver_profile = Driver.objects.filter(user=route.driver).first()
            if driver_profile:
                driver_profile.is_available = True
                driver_profile.on_trip = False
                driver_profile.save(update_fields=["is_available", "on_trip"])

        # Set any non-delivered, non-cancelled orders inside this route to UNDELIVERED
        stops = route.stops.select_related("order")
        undelivered_count = 0
        for stop in stops:
            if stop.order.status in [
                OrderStatus.PENDING,
                OrderStatus.CONFIRMED,
                OrderStatus.IN_TRANSIT,
            ]:
                stop.order.status = OrderStatus.UNDELIVERED
                stop.order.delivered_at = timezone.now()
                stop.order.save(update_fields=["status", "delivered_at"])
                undelivered_count += 1

                # Send undelivered attempt push notification
                order = stop.order
                if order.customer and order.customer.user:
                    title = "⚠️ Delivery Attempt Failed"
                    body = "We missed you today! We couldn't deliver your order, but we will try again on our next run. 🚚"
                    send_push_notification(
                        user=order.customer.user,
                        title=title,
                        body=body,
                        order=order,
                        notification_type='order_status'
                    )

                DeliveryLog.objects.create(
                    action="Order Force Undelivered",
                    route=route,
                    order=stop.order,
                    details="Order marked as undelivered due to manual trip completion/stop.",
                )

        DeliveryLog.objects.create(
            action="Trip Completed",
            route=route,
            details=f"Driver completed trip. Marked {undelivered_count} remaining orders as undelivered.",
        )

    logger.info(
        "Trip completed successfully for Route %s. Undelivered orders: %d",
        route_id,
        undelivered_count,
    )
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
        status__in=[RouteStatus.PENDING, RouteStatus.STARTED, RouteStatus.IN_PROGRESS],
    ).select_related("driver")

    stopped_count = 0
    orders_affected = 0

    for route in active_routes:
        with transaction.atomic():
            route.status = RouteStatus.STOPPED
            route.is_completed = True
            route.completed_at = timezone.now()
            route.save(update_fields=["status", "is_completed", "completed_at"])

            try:
                update_route_metrics(route)
            except Exception as e:
                logger.error("Failed to update route metrics in auto_stop_active_trips_at_noon: %s", e)

            # Free the driver profile
            if route.driver:
                driver_profile = Driver.objects.filter(user=route.driver).first()
                if driver_profile:
                    driver_profile.is_available = True
                    driver_profile.on_trip = False
                    driver_profile.save(update_fields=["is_available", "on_trip"])

            # Update remaining orders to undelivered
            stops = route.stops.select_related("order")
            for stop in stops:
                if stop.order.status in [
                    OrderStatus.PENDING,
                    OrderStatus.CONFIRMED,
                    OrderStatus.IN_TRANSIT,
                ]:
                    stop.order.status = OrderStatus.UNDELIVERED
                    stop.order.delivered_at = timezone.now()
                    stop.order.save(update_fields=["status", "delivered_at"])
                    orders_affected += 1

                    # Send undelivered attempt push notification
                    order = stop.order
                    if order.customer and order.customer.user:
                        title = "⚠️ Delivery Attempt Failed"
                        body = "We missed you today! We couldn't deliver your order, but we will try again on our next run. 🚚"
                        send_push_notification(
                            user=order.customer.user,
                            title=title,
                            body=body,
                            order=order,
                            notification_type='order_status'
                        )

                    DeliveryLog.objects.create(
                        action="Noon Cutoff Stop",
                        route=route,
                        order=stop.order,
                        details="Order marked undelivered automatically at 12:00 PM cutoff.",
                    )

            DeliveryLog.objects.create(
                action="Noon Cutoff Stop",
                route=route,
                details=f"Route automatically stopped at 12:00 PM cutoff. Affected orders: {orders_affected}",
            )
            stopped_count += 1

    return {
        "stopped_routes_count": stopped_count,
        "orders_affected_count": orders_affected,
    }


def process_pre_delivery_product_cutoff():
    """
    Runs at 6:00 AM cutoff time on delivery day.
    (Previously locked routes; now just logs that the cutoff has passed).
    """
    logger.info(
        "Cutoff 6:00 AM processing completed. No routes locked per new biker/rider model."
    )
    return {"locked_routes_count": 0}


def calculate_geo_distance(lon1, lat1, lon2, lat2):
    import math
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000  # Radius of earth in meters
    return c * r


def get_trail_coords(trail):
    loc = trail.cleaned_location or trail.location
    if not loc:
        return None
    if hasattr(loc, "x"):
        return loc.y, loc.x  # Point returns x (lng), y (lat) -> return (lat, lng)
    if isinstance(loc, dict):
        return float(loc.get("lat") or 0.0), float(loc.get("lng") or 0.0)
    return None


def update_route_metrics(orders_route):
    """
    Calculates actual distance (km), actual duration (minutes), and unproductive stoppage time (minutes)
    based on the driver's trails, counting from leaving the 100m warehouse buffer to returning to it.
    """
    from routing.models import Route as RoutingRoute
    from tracking.models import DriverTrail

    # 1. Fetch corresponding routing route and historical trails
    routing_route = RoutingRoute.objects.filter(
        driver__user=orders_route.driver,
        delivery_date=orders_route.delivery_date
    ).first()

    if routing_route:
        trails = list(DriverTrail.objects.filter(route=routing_route).order_by("timestamp"))
    else:
        trails = list(DriverTrail.objects.filter(
            user=orders_route.driver,
            timestamp__date=orders_route.delivery_date
        ).order_by("timestamp"))

    if not trails:
        return

    # 2. Get warehouse location
    from routing.models import Driver as RoutingDriver
    driver_profile = RoutingDriver.objects.filter(user=orders_route.driver).first()
    warehouse = driver_profile.warehouse if driver_profile else None
    w_lat, w_lng = None, None
    if warehouse and warehouse.latitude is not None and warehouse.longitude is not None:
        w_lat = float(warehouse.latitude)
        w_lng = float(warehouse.longitude)

    # Fallback to first trail coordinate if warehouse is not set
    if w_lat is None or w_lng is None:
        first_coord = get_trail_coords(trails[0])
        if first_coord:
            w_lat, w_lng = first_coord

    if w_lat is None or w_lng is None:
        return

    # 3. Determine when they left and returned to warehouse (100m buffer)
    leave_idx = 0
    for idx, t in enumerate(trails):
        coords = get_trail_coords(t)
        if coords:
            dist = calculate_geo_distance(w_lng, w_lat, coords[1], coords[0])
            if dist > 100.0:
                leave_idx = idx
                break

    # Find when they returned to the warehouse after leaving
    return_idx = len(trails) - 1
    for idx in range(len(trails) - 1, leave_idx, -1):
        coords = get_trail_coords(trails[idx])
        if coords:
            dist = calculate_geo_distance(w_lng, w_lat, coords[1], coords[0])
            if dist > 100.0:
                return_idx = min(idx + 1, len(trails) - 1)
                break

    sub_trail = trails[leave_idx : return_idx + 1]
    if not sub_trail:
        return

    # 4. Calculate actual duration (warehouse to warehouse)
    t_start = sub_trail[0].timestamp
    t_end = sub_trail[-1].timestamp
    actual_duration = max(0, int((t_end - t_start).total_seconds() / 60.0))

    # 5. Calculate actual distance (sum of segments outside warehouse buffer)
    actual_distance_meters = 0.0
    prev_coords = None
    for t in sub_trail:
        coords = get_trail_coords(t)
        if coords:
            if prev_coords:
                actual_distance_meters += calculate_geo_distance(prev_coords[1], prev_coords[0], coords[1], coords[0])
            prev_coords = coords
    actual_distance_km = round(actual_distance_meters / 1000.0, 2)

    # 6. Calculate stoppage duration (unproductive stop time)
    stoppage_minutes = 0

    # Fetch customer coordinates to check proximity and scale wait time allowance
    stops = list(orders_route.stops.select_related("order__customer"))
    customer_locations = []
    for s in stops:
        cust_loc = s.order.customer.location
        if cust_loc:
            if hasattr(cust_loc, "x"):
                customer_locations.append((cust_loc.y, cust_loc.x))
            elif isinstance(cust_loc, dict):
                customer_locations.append((float(cust_loc.get("lat") or 0.0), float(cust_loc.get("lng") or 0.0)))

    # Rolling stop detector
    stop_start_coords = None
    stop_start_time = None
    prev_t = None
    stoppage_history_list = []

    for t in sub_trail:
        coords = get_trail_coords(t)
        if not coords:
            continue

        if stop_start_coords is None:
            stop_start_coords = coords
            stop_start_time = t.timestamp
            prev_t = t
            continue

        dist = calculate_geo_distance(stop_start_coords[1], stop_start_coords[0], coords[1], coords[0])
        if dist <= 25.0:
            # Still at the same stop
            prev_t = t
            continue
        else:
            # Major move / changed location
            duration_mins = (prev_t.timestamp - stop_start_time).total_seconds() / 60.0
            if duration_mins > 2.0:
                # Calculate customer allowance at stop_start_coords
                near_customers = 0
                for c_lat, c_lng in customer_locations:
                    c_dist = calculate_geo_distance(stop_start_coords[1], stop_start_coords[0], c_lng, c_lat)
                    if c_dist <= 100.0:
                        near_customers += 1

                # Max allowance: if there are customers, 2 * near_customers. If not, 2 minutes as base traffic buffer.
                allowance = 2.0 * max(1, near_customers)
                unproductive_mins = max(0.0, duration_mins - allowance)
                stoppage_minutes += int(unproductive_mins)

                stoppage_history_list.append({
                    "lat": float(stop_start_coords[0]),
                    "lng": float(stop_start_coords[1]),
                    "start_time": stop_start_time.isoformat(),
                    "end_time": prev_t.timestamp.isoformat(),
                    "duration_minutes": round(duration_mins, 1),
                    "near_customers": near_customers,
                    "allowance_minutes": allowance,
                    "unproductive_minutes": round(unproductive_mins, 1)
                })

            # Reset start coordinates for next segment
            stop_start_coords = coords
            stop_start_time = t.timestamp
            prev_t = t

    # Check last open segment
    if stop_start_coords and stop_start_time and prev_t:
        duration_mins = (prev_t.timestamp - stop_start_time).total_seconds() / 60.0
        if duration_mins > 2.0:
            near_customers = 0
            for c_lat, c_lng in customer_locations:
                c_dist = calculate_geo_distance(stop_start_coords[1], stop_start_coords[0], c_lng, c_lat)
                if c_dist <= 100.0:
                    near_customers += 1
            allowance = 2.0 * max(1, near_customers)
            unproductive_mins = max(0.0, duration_mins - allowance)
            stoppage_minutes += int(unproductive_mins)

            stoppage_history_list.append({
                "lat": float(stop_start_coords[0]),
                "lng": float(stop_start_coords[1]),
                "start_time": stop_start_time.isoformat(),
                "end_time": prev_t.timestamp.isoformat(),
                "duration_minutes": round(duration_mins, 1),
                "near_customers": near_customers,
                "allowance_minutes": allowance,
                "unproductive_minutes": round(unproductive_mins, 1)
            })

    # Save the computed values to orders_route
    orders_route.actual_distance_km = actual_distance_km
    orders_route.actual_duration_minutes = actual_duration
    orders_route.stoppage_duration_minutes = stoppage_minutes
    orders_route.stoppage_history = stoppage_history_list
    orders_route.save(update_fields=[
        "actual_distance_km",
        "actual_duration_minutes",
        "stoppage_duration_minutes",
        "stoppage_history"
    ])
