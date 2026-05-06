import logging
from django.conf import settings

logger = logging.getLogger(__name__)

TIME_LIMIT = getattr(settings, 'ROUTE_OPTIMIZATION_TIME_LIMIT_SECONDS', 5)


def solve_tsp(distance_matrix: list[list[float]]) -> list[int] | None:
    """
    Solves the Travelling Salesman Problem using Google OR-Tools.

    Strategy:
        1. PATH_CHEAPEST_ARC  — fast greedy first solution
        2. GUIDED_LOCAL_SEARCH — metaheuristic improvement within time limit

    Args:
        distance_matrix: NxN matrix of travel costs (durations from OSRM).
                         Index 0 is always the depot (warehouse).

    Returns:
        Ordered list of stop indices representing the optimal route,
        starting and ending at index 0 (depot).
        Returns None if no solution is found.
    """
    try:
        from ortools.constraint_solver import routing_enums_pb2
        from ortools.constraint_solver import pywrapcp
    except ImportError:
        logger.error('OR-Tools not installed. Run: pip install ortools')
        return None

    n = len(distance_matrix)
    if n < 2:
        logger.warning('TSP solver: need at least 2 nodes.')
        return None

    # Scale floats to integers (OR-Tools requires int costs)
    scale = 100
    int_matrix = [
        [int(distance_matrix[i][j] * scale) for j in range(n)]
        for i in range(n)
    ]

    # Create routing index manager (1 vehicle, depot at index 0)
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Search parameters
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.seconds = TIME_LIMIT
    search_params.log_search = False

    solution = routing.SolveWithParameters(search_params)

    if not solution:
        logger.warning('OR-Tools: no solution found within time limit.')
        return None

    # Decode route
    route = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    route.append(0)  # Return to depot

    total_cost = solution.ObjectiveValue() / scale
    logger.info('OR-Tools solution: %s (cost=%.1fs)', route, total_cost)
    return route
