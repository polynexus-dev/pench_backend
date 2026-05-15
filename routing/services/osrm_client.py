import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

OSRM_BASE_URL = getattr(settings, 'OSRM_BASE_URL', 'http://router.project-osrm.org')


def build_distance_matrix(stops: list[dict]) -> list[list[float]]:
    """
    Fetch a driving duration matrix from OSRM for a list of stops.

    Uses: GET /table/v1/driving/{coordinates}
    Public OSRM endpoint: router.project-osrm.org

    Args:
        stops: List of dicts with 'lat' and 'lon' keys.
               stops[0] is treated as the depot (warehouse).

    Returns:
        NxN matrix of durations in seconds (float).
        Falls back to Euclidean distances if OSRM call fails.

    Raises:
        RuntimeError if the OSRM response is malformed.
    """
    if len(stops) < 2:
        raise ValueError('At least 2 stops (depot + 1 delivery) are required.')

    # OSRM expects coordinates as lon,lat (note: lon first)
    coords_str = ';'.join(f"{s['lon']},{s['lat']}" for s in stops)
    url = f'{OSRM_BASE_URL}/table/v1/driving/{coords_str}'

    try:
        resp = requests.get(url, params={'annotations': 'duration'}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get('code') != 'Ok':
            raise RuntimeError(f"OSRM error: {data.get('message', 'unknown')}")

        matrix = data['durations']
        logger.debug('OSRM matrix fetched: %dx%d', len(matrix), len(matrix[0]))
        return matrix

    except requests.RequestException as exc:
        logger.error('OSRM request failed: %s — falling back to Euclidean.', exc)
        return _euclidean_matrix(stops)


def _euclidean_matrix(stops: list[dict]) -> list[list[float]]:
    """Fallback: straight-line distance matrix in degrees × 10000."""
    import math
    n = len(stops)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dlat = stops[i]['lat'] - stops[j]['lat']
                dlon = stops[i]['lon'] - stops[j]['lon']
                matrix[i][j] = math.sqrt(dlat ** 2 + dlon ** 2) * 10000
    return matrix


def snap_to_road(lng: float, lat: float) -> list[float]:
    """
    Snap a single coordinate to the nearest road.
    Useful for the first point of a trip.
    """
    url = f'{OSRM_BASE_URL}/nearest/v1/driving/{lng},{lat}'
    try:
        resp = requests.get(url, params={'number': 1}, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') == 'Ok' and data.get('waypoints'):
            return data['waypoints'][0]['location']
    except Exception as e:
        print(f"[OSRM Nearest Error] {e}")
    return [lng, lat]


def match_trail(coordinates: list[list[float]], radiuses: list[float] = None) -> list[list[float]]:
    """
    Snap a list of coordinates to the nearest road using OSRM Matching API.
    
    Returns the FULL geometry (interpolated points) of the matched path.
    """
    if len(coordinates) < 2:
        return coordinates

    # OSRM expects coordinates as lon,lat (note: lon first)
    coords_str = ';'.join(f"{lng},{lat}" for lng, lat in coordinates)
    url = f'{OSRM_BASE_URL}/match/v1/driving/{coords_str}'

    params = {
        'overview': 'full',
        'geometries': 'geojson',
        'tidy': 'true'
    }
    
    if radiuses:
        params['radiuses'] = ';'.join(map(str, radiuses))

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data.get('code') != 'Ok':
            print(f"[OSRM ERROR] {data.get('code')}: {data.get('message')}")
            return coordinates

        # matchings[0].geometry contains the full road path (interpolated points)
        matchings = data.get('matchings', [])
        if matchings and 'geometry' in matchings[0]:
            # This returns all points along the road curves
            return matchings[0]['geometry']['coordinates']

        # Fallback to tracepoints if geometry is missing
        snapped = []
        for point in data.get('tracepoints', []):
            if point and 'location' in point:
                snapped.append(point['location'])
            else:
                snapped.append(coordinates[len(snapped)])
        return snapped

    except requests.RequestException as exc:
        print(f"[OSRM Request Error] {exc}")
        return coordinates
