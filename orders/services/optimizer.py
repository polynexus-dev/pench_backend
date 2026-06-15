import math
import requests
import logging
from django.contrib.gis.geos import Point, LineString
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from orders.models import Order, Route, RouteStop

logger = logging.getLogger(__name__)


def get_coords(loc):
    """Helper to extract (x, y) from GIS Point or JSON dict."""
    if not loc:
        return None, None
    if hasattr(loc, "x") and hasattr(loc, "y"):
        return loc.x, loc.y
    if isinstance(loc, dict):
        return loc.get("lng") or loc.get("longitude"), loc.get("lat") or loc.get(
            "latitude"
        )
    return None, None


def get_osrm_distance_matrix(locations):
    """Fetches road distance matrix using BICYCLE profile."""
    coord_list = []
    for loc in locations:
        x, y = get_coords(loc)
        if x is not None:
            coord_list.append(f"{x},{y}")

    if not coord_list:
        return None

    coords = ";".join(coord_list)
    from django.conf import settings

    url = f"{settings.OSRM_BASE_URL}/table/v1/driving/{coords}?annotations=distance"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get("distances")
    except Exception as e:
        logger.warning(f"OSRM Distance Matrix failed: {str(e)}")
    return None


def get_osrm_route_geometry(locations):
    """Fetches the road geometry using BICYCLE profile."""
    coord_list = []
    for loc in locations:
        x, y = get_coords(loc)
        if x is not None:
            coord_list.append(f"{x},{y}")

    if not coord_list:
        return None

    coords = ";".join(coord_list)
    from django.conf import settings

    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords}?geometries=geojson&overview=full&continue_straight=false"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "routes" in data and len(data["routes"]) > 0:
                geom = data["routes"][0]["geometry"]
                coords = [(c[0], c[1]) for c in geom["coordinates"]]
                return LineString(coords)
    except Exception as e:
        logger.warning(f"OSRM Geometry failed: {str(e)}")
    return None


def optimize_route_ortools(order_ids, start_point=None):
    orders = list(Order.objects.filter(id__in=order_ids).select_related("customer"))
    valid_orders = [o for o in orders if o.customer.location]

    print(
        f"[DEBUG] Found {len(orders)} orders. {len(valid_orders)} have customer locations."
    )

    if not valid_orders:
        return orders, None

    locations = []
    if start_point:
        locations.append(start_point)
    else:
        locations.append(valid_orders[0].customer.location)
    locations.extend([o.customer.location for o in valid_orders])

    # 1. Fetch and Sanitize Distance Matrix
    raw_matrix = get_osrm_distance_matrix(locations)
    size = len(locations)

    if raw_matrix:
        # Replace None/Null with a very large distance (penalty)
        distance_matrix = []
        for row in raw_matrix:
            sanitized_row = []
            for dist in row:
                if dist is None:
                    sanitized_row.append(999999)  # 999km penalty for unreachable points
                else:
                    sanitized_row.append(int(dist))
            distance_matrix.append(sanitized_row)
    else:
        # Fallback to Haversine
        distance_matrix = [[0] * size for _ in range(size)]
        for i in range(size):
            for j in range(size):
                p1, p2 = locations[i], locations[j]
                x1, y1 = get_coords(p1)
                x2, y2 = get_coords(p2)
                distance_matrix[i][j] = int(
                    math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2) * 111000
                )

    # 2. OR-Tools Setup
    manager = pywrapcp.RoutingIndexManager(size, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # 3. Search Strategy
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 2

    # 4. Solve
    assignment = routing.SolveWithParameters(search_parameters)
    if not assignment:
        logger.warning("OR-Tools failed to find a solution.")
        return valid_orders, None

    index = routing.Start(0)
    sequence_indices = []
    while not routing.IsEnd(index):
        node_index = manager.IndexToNode(index)
        if node_index > 0:  # Skip the starting point (depot)
            sequence_indices.append(node_index - 1)
        index = assignment.Value(routing.NextVar(index))

    optimized_orders = [valid_orders[i] for i in sequence_indices]

    # 5. Final Geometry
    final_locations = []
    if start_point:
        final_locations.append(start_point)
    final_locations.extend([o.customer.location for o in optimized_orders])

    road_geometry = get_osrm_route_geometry(final_locations)

    return optimized_orders, road_geometry


def create_optimized_route(
    name, driver, date, order_ids, warehouse=None, warehouse_location=None
):
    import datetime
    if isinstance(date, str):
        try:
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            try:
                date = datetime.date.fromisoformat(date)
            except ValueError:
                pass

    from django.contrib.auth import get_user_model
    from routing.models import Driver

    User = get_user_model()

    # Resolve BOTH driver_user (User instance for Route.driver) and driver_profile (Driver profile instance for Warehouse)
    driver_user = None
    driver_profile = None

    if driver:
        if isinstance(driver, User):
            driver_user = driver
            driver_profile = getattr(driver, "driver_profile", None)
            if not driver_profile:
                driver_profile = Driver.objects.filter(user=driver).first()
        elif isinstance(driver, Driver):
            driver_profile = driver
            driver_user = driver.user
        else:
            # Duck typing support or ID lookups
            if hasattr(driver, "driver_profile"):
                driver_user = driver
                driver_profile = driver.driver_profile
            elif hasattr(driver, "user"):
                driver_profile = driver
                driver_user = driver.user
            else:
                driver_user = User.objects.filter(id=driver).first()
                if driver_user:
                    driver_profile = getattr(driver_user, "driver_profile", None)
                    if not driver_profile:
                        driver_profile = Driver.objects.filter(user=driver_user).first()

    # Automatically resolve warehouse and warehouse_location if not explicitly passed
    if not warehouse and driver_profile and getattr(driver_profile, "warehouse", None):
        warehouse = driver_profile.warehouse

    if warehouse and not warehouse_location:
        if warehouse.latitude is not None and warehouse.longitude is not None:
            warehouse_location = {
                "longitude": float(warehouse.longitude),
                "latitude": float(warehouse.latitude),
            }

    optimized_orders, road_geometry = optimize_route_ortools(
        order_ids, start_point=warehouse_location
    )

    from django.db import transaction
    from orders.models import RouteStatus, OrderStatus, DeliveryLog
    from django.utils import timezone
    from django.db.models import Q

    with transaction.atomic():
        # Check if an existing incomplete, unstarted route already exists for this driver and date.
        # If so, UPDATE it in-place instead of creating a new route.
        existing_route = None
        if driver_user and date:
            existing_route = Route.objects.filter(
                driver=driver_user,
                delivery_date=date,
                is_completed=False,
                started_at__isnull=True,
            ).first()

        if existing_route:
            # UPDATE the existing route: clear old stops, set new optimized stops and geometry
            existing_route.stops.all().delete()
            RouteStop.objects.filter(order_id__in=order_ids).delete()

            existing_route.geometry = road_geometry
            if name:
                existing_route.name = name
            existing_route.status = RouteStatus.PENDING
            existing_route.save(update_fields=["geometry", "name", "status"])

            stops = []
            for index, order in enumerate(optimized_orders):
                stops.append(RouteStop(route=existing_route, order=order, sequence_number=index + 1))
            RouteStop.objects.bulk_create(stops)

            DeliveryLog.objects.create(
                action="Route Updated",
                route=existing_route,
                details=f"Route updated in-place with {len(optimized_orders)} stops (new/additional orders detected).",
            )

            return existing_route

        # No existing route found — create a new one.
        # Auto-close/complete any previous active routes for this driver (from OTHER dates)
        if driver_user:
            previous_active_routes = Route.objects.filter(
                Q(driver=driver_user) | Q(additional_drivers=driver_user),
                is_completed=False,
            ).distinct()
            for prev_route in previous_active_routes:
                prev_route.status = RouteStatus.COMPLETED
                prev_route.completed_at = timezone.now()
                prev_route.is_completed = True
                prev_route.save(
                    update_fields=["status", "completed_at", "is_completed"]
                )

                # Free the driver profile
                if driver_profile:
                    driver_profile.is_available = True
                    driver_profile.on_trip = False
                    driver_profile.save(update_fields=["is_available", "on_trip"])

                # Set all incomplete orders on that route to UNDELIVERED
                prev_stops = prev_route.stops.select_related("order")
                undelivered_count = 0
                for stop in prev_stops:
                    if stop.order.status in [
                        OrderStatus.PENDING,
                        OrderStatus.CONFIRMED,
                        OrderStatus.DISPATCHED,
                        OrderStatus.IN_TRANSIT,
                    ]:
                        stop.order.status = OrderStatus.UNDELIVERED
                        stop.order.delivered_at = timezone.now()
                        stop.order.save(update_fields=["status", "delivered_at"])
                        undelivered_count += 1

                        DeliveryLog.objects.create(
                            action="Order Force Undelivered",
                            route=prev_route,
                            order=stop.order,
                            details="Order marked as undelivered automatically during route generation because it was left incomplete.",
                        )

                DeliveryLog.objects.create(
                    action="Trip Completed",
                    route=prev_route,
                    details=f"Route automatically closed/completed on new route creation. {undelivered_count} stops marked undelivered.",
                )

        RouteStop.objects.filter(order_id__in=order_ids).delete()
        route = Route.objects.create(
            name=name,
            driver=driver_user,  # Save the resolved User instance
            delivery_date=date,
            geometry=road_geometry,
        )
        stops = []
        for index, order in enumerate(optimized_orders):
            stops.append(RouteStop(route=route, order=order, sequence_number=index + 1))
        RouteStop.objects.bulk_create(stops)
    return route
