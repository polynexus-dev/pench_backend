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


def match_trail(coordinates: list[list[float]]) -> list[list[float]]:
    """
    Snap a list of coordinates to the nearest road using OSRM Matching API.
    
    Args:
        coordinates: List of [lng, lat] pairs.
        
    Returns:
        List of snapped [lng, lat] pairs. 
        Falls back to original coordinates if OSRM fails.
    """
    if len(coordinates) < 2:
        return coordinates

    # OSRM expects coordinates as lon,lat (note: lon first)
    coords_str = ';'.join(f"{lng},{lat}" for lng, lat in coordinates)
    url = f'{OSRM_BASE_URL}/match/v1/driving/{coords_str}'

    try:
        # annotations=duration,distance can be added if needed
        # overview=simplified (default) or full
        resp = requests.get(url, params={'overview': 'full', 'geometries': 'geojson'}, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data.get('code') != 'Ok':
            logger.warning(f"OSRM Match failed: {data.get('message', 'unknown')}. Falling back to raw.")
            return coordinates

        # The 'tracepoints' array contains information about each input coordinate
        # and where it snapped.
        snapped = []
        for point in data.get('tracepoints', []):
            if point and 'location' in point:
                snapped.append(point['location']) # [lng, lat]
            else:
                # If a point couldn't be matched, keep original or skip? 
                # Keeping original for now to maintain list length
                snapped.append(coordinates[len(snapped)])

        return snapped

    except requests.RequestException as exc:
        logger.error(f'OSRM Match request failed: {exc}')
        return coordinates
