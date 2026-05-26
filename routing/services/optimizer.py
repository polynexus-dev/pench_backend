import logging
from django.contrib.gis.geos import LineString, Point

from .geocoder import geocode_orders
from .osrm_client import build_distance_matrix
from .tsp_solver import solve_tsp

logger = logging.getLogger(__name__)


def optimize_route(route) -> bool:
    """
    Full optimization pipeline for a Route instance:

        1. Geocode delivery addresses for all orders
        2. Build OSRM driving duration matrix
        3. Solve TSP with OR-Tools (PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH)
        4. Decode solution to ordered waypoints
        5. Save GeoJSON LineString to route.geometry

    Args:
        route: routing.models.Route instance with orders pre-assigned.

    Returns:
        True if optimization succeeded, False otherwise.
    """
    from routing.models import RouteStatus

    route.status = RouteStatus.OPTIMIZING
    route.save(update_fields=["status"])

    try:
        orders = list(route.orders.all())
        if not orders:
            raise ValueError("Route has no orders assigned.")

        # Step 1: Geocode — depot (index 0) + delivery stops
        depot_stop = _get_depot_stop(route)
        delivery_stops = geocode_orders(orders)

        if not delivery_stops:
            raise ValueError("No orders could be geocoded.")

        all_stops = [depot_stop] + delivery_stops
        logger.info("Optimizing route %s with %d stops.", route.id, len(all_stops))

        # Step 2: OSRM distance matrix
        matrix = build_distance_matrix(all_stops)

        # Step 3: OR-Tools TSP
        stop_order = solve_tsp(matrix)
        if stop_order is None:
            raise RuntimeError("OR-Tools returned no solution.")

        # Step 4: Build ordered waypoints from solution indices
        ordered_stops = [all_stops[i] for i in stop_order]
        waypoints = [[s["lon"], s["lat"]] for s in ordered_stops]

        # Step 5: Save geometry and metadata
        line = LineString(waypoints, srid=4326)
        route.geometry = line
        route.waypoints = waypoints
        route.status = RouteStatus.OPTIMIZED

        # Estimate total duration from matrix (sum of consecutive pairs)
        total_seconds = sum(
            matrix[stop_order[i]][stop_order[i + 1]] for i in range(len(stop_order) - 1)
        )
        route.estimated_duration_minutes = int(total_seconds / 60)
        route.optimization_error = ""
        route.save()

        logger.info("Route %s optimized successfully.", route.id)
        return True

    except Exception as exc:
        logger.exception("Route %s optimization failed: %s", route.id, exc)
        route.status = RouteStatus.FAILED
        route.optimization_error = str(exc)
        route.save(update_fields=["status", "optimization_error"])
        return False


def _get_depot_stop(route=None) -> dict:
    """
    Returns the warehouse/depot location.
    If route has an associated warehouse with coordinates, it uses those.
    Otherwise it falls back to settings.
    """
    from django.conf import settings

    # Try route's associated warehouse
    if (
        route
        and route.warehouse
        and route.warehouse.latitude is not None
        and route.warehouse.longitude is not None
    ):
        return {
            "order_id": None,
            "address": route.warehouse.name or "Warehouse",
            "lat": float(route.warehouse.latitude),
            "lon": float(route.warehouse.longitude),
        }

    depot = getattr(settings, "DEPOT_LOCATION", {"lat": 19.0760, "lon": 72.8777})
    return {
        "order_id": None,
        "address": "Depot",
        "lat": depot["lat"],
        "lon": depot["lon"],
    }
