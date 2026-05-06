import math
import requests
import logging
from django.contrib.gis.geos import Point, LineString
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from .models import Order, Route, RouteStop

logger = logging.getLogger(__name__)

def get_osrm_distance_matrix(locations):
    """Fetches road distance matrix using BICYCLE profile."""
    coords = ";".join([f"{loc.x},{loc.y}" for loc in locations])
    url = f"http://router.project-osrm.org/table/v1/bicycle/{coords}?annotations=distance"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json().get('distances')
    except Exception as e:
        logger.warning(f"OSRM Distance Matrix failed: {str(e)}")
    return None

def get_osrm_route_geometry(locations):
    """Fetches the road geometry using BICYCLE profile."""
    coords = ";".join([f"{loc.x},{loc.y}" for loc in locations])
    url = f"http://router.project-osrm.org/route/v1/bicycle/{coords}?geometries=geojson&overview=full&continue_straight=false"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'routes' in data and len(data['routes']) > 0:
                geom = data['routes'][0]['geometry']
                coords = [(c[0], c[1]) for c in geom['coordinates']]
                return LineString(coords)
    except Exception as e:
        logger.warning(f"OSRM Geometry failed: {str(e)}")
    return None

def optimize_route_ortools(order_ids, start_point=None):
    orders = list(Order.objects.filter(id__in=order_ids).select_related('customer'))
    valid_orders = [o for o in orders if o.customer.location]
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
                    sanitized_row.append(999999) # 999km penalty for unreachable points
                else:
                    sanitized_row.append(int(dist))
            distance_matrix.append(sanitized_row)
    else:
        # Fallback to Haversine
        distance_matrix = [[0]*size for _ in range(size)]
        for i in range(size):
            for j in range(size):
                p1, p2 = locations[i], locations[j]
                distance_matrix[i][j] = int(math.sqrt((p1.x-p2.x)**2 + (p1.y-p2.y)**2) * 111000)

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
        if node_index > 0: # Skip the starting point (depot)
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

def create_optimized_route(name, driver, date, order_ids, warehouse_location=None):
    optimized_orders, road_geometry = optimize_route_ortools(order_ids, start_point=warehouse_location)
    
    from django.db import transaction
    with transaction.atomic():
        RouteStop.objects.filter(order_id__in=order_ids).delete()
        route = Route.objects.create(
            name=name,
            driver=driver,
            delivery_date=date,
            geometry=road_geometry
        )
        stops = []
        for index, order in enumerate(optimized_orders):
            stops.append(RouteStop(
                route=route,
                order=order,
                sequence_number=index + 1
            ))
        RouteStop.objects.bulk_create(stops)
    return route
