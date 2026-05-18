import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# --- OSRM URL RESOLUTION WITH AUTO-SWITCHING FALLBACK ---
OSRM_BASE_URL = getattr(settings, 'OSRM_BASE_URL', 'https://osrm.polynexus.in')
FALLBACK_OSRM_URL = 'https://osrm.polynexus.in'
_use_fallback = False

def get_osrm_base_url() -> str:
    global _use_fallback
    if _use_fallback:
        return FALLBACK_OSRM_URL
    return OSRM_BASE_URL

def trigger_osrm_fallback():
    global _use_fallback
    if not _use_fallback and OSRM_BASE_URL != FALLBACK_OSRM_URL:
        print(f"\n[OSRM Client] Connection failed to {OSRM_BASE_URL}. Switching globally to public fallback {FALLBACK_OSRM_URL}...")
        _use_fallback = True


def build_distance_matrix(stops: list[dict]) -> list[list[float]]:
    """
    Fetch a driving duration matrix from OSRM for a list of stops.
    Uses: GET /table/v1/driving/{coordinates}
    """
    if len(stops) < 2:
        raise ValueError('At least 2 stops (depot + 1 delivery) are required.')

    # OSRM expects coordinates as lon,lat (note: lon first)
    coords_str = ';'.join(f"{s['lon']},{s['lat']}" for s in stops)
    base_url = get_osrm_base_url()
    url = f'{base_url}/table/v1/driving/{coords_str}'

    try:
        resp = requests.get(url, params={'annotations': 'duration'}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get('code') != 'Ok':
            raise RuntimeError(f"OSRM error: {data.get('message', 'unknown')}")

        matrix = data['durations']
        logger.debug('OSRM matrix fetched: %dx%d', len(matrix), len(matrix[0]))
        return matrix

    except Exception as exc:
        logger.error('OSRM matrix failed: %s — falling back.', exc)
        if base_url != FALLBACK_OSRM_URL:
            trigger_osrm_fallback()
            return build_distance_matrix(stops) # Retry once with public fallback
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
    base_url = get_osrm_base_url()
    url = f'{base_url}/nearest/v1/driving/{lng},{lat}'
    try:
        resp = requests.get(url, params={'number': 1}, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') == 'Ok' and data.get('waypoints'):
            return data['waypoints'][0]['location']
        else:
            raise RuntimeError(f"OSRM code not Ok: {data.get('code')}")
    except Exception as e:
        print(f"[OSRM Nearest Error] {e}")
        if base_url != FALLBACK_OSRM_URL:
            trigger_osrm_fallback()
            return snap_to_road(lng, lat) # Retry once with public fallback
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
    base_url = get_osrm_base_url()
    url = f'{base_url}/match/v1/driving/{coords_str}'

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
            raise RuntimeError(f"OSRM code not Ok: {data.get('code')}: {data.get('message')}")

        matchings = data.get('matchings', [])
        if matchings and 'geometry' in matchings[0]:
            return matchings[0]['geometry']['coordinates']

        snapped = []
        for point in data.get('tracepoints', []):
            if point and 'location' in point:
                snapped.append(point['location'])
            else:
                snapped.append(coordinates[len(snapped)])
        return snapped

    except Exception as exc:
        print(f"[OSRM Match Error] {exc}")
        if base_url != FALLBACK_OSRM_URL:
            trigger_osrm_fallback()
            return match_trail(coordinates, radiuses) # Retry once with public fallback
        return coordinates


def get_road_route(coordinates: list[list[float]]) -> list[list[float]]:
    """
    Given a list of coordinates, routes them sequentially along the street network
    using the OSRM Route API to return a continuous street-based path.
    """
    if len(coordinates) < 2:
        return coordinates

    # OSRM has coordinate limits (usually 100) and URL length limits. Chunk if necessary.
    max_chunk_size = 50
    if len(coordinates) > max_chunk_size:
        full_route = []
        for i in range(0, len(coordinates) - 1, max_chunk_size - 1):
            chunk = coordinates[i:i + max_chunk_size]
            if len(chunk) < 2:
                break
            
            chunk_route = get_road_route(chunk)
            
            # Append the chunk route. Avoid duplicating the overlapping point.
            if not full_route:
                full_route.extend(chunk_route)
            else:
                full_route.extend(chunk_route[1:])
                
        return full_route

    # OSRM expects coordinates as lon,lat (note: lon first)
    coords_str = ';'.join(f"{lng},{lat}" for lng, lat in coordinates)
    base_url = get_osrm_base_url()
    url = f"{base_url}/route/v1/driving/{coords_str}"
    
    params = {
        'overview': 'full',
        'geometries': 'geojson',
        'continue_straight': 'false'
    }
    
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('code') == 'Ok' and 'routes' in data and len(data['routes']) > 0:
            return data['routes'][0]['geometry']['coordinates']
        else:
            raise RuntimeError(f"OSRM code not Ok: {data.get('code')}")
    except Exception as e:
        logger.error(f"[OSRM Route Error] {e}")
        if base_url != FALLBACK_OSRM_URL:
            trigger_osrm_fallback()
            return get_road_route(coordinates) # Retry once with public fallback
    return coordinates
