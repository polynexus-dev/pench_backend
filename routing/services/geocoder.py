import requests
import logging

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "DeliveryERP/1.0 (contact@yourcompany.com)"}


def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Geocode a text address using OSM Nominatim.

    Returns:
        (latitude, longitude) tuple, or None if not found.
    """
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
    }
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
        logger.warning('Nominatim: no result for address "%s"', address)
        return None
    except requests.RequestException as exc:
        logger.error('Nominatim geocoding failed for "%s": %s', address, exc)
        return None


def geocode_orders(orders) -> list[dict]:
    """
    Geocode delivery addresses for a list of orders.

    Returns:
        List of dicts: [{order_id, address, lat, lon}]
        Orders that fail geocoding are skipped with a warning.
    """
    results = []
    for order in orders:
        coords = geocode_address(order.delivery_address)
        if coords:
            lat, lon = coords
            results.append(
                {
                    "order_id": str(order.id),
                    "address": order.delivery_address,
                    "lat": lat,
                    "lon": lon,
                }
            )
        else:
            logger.warning("Skipping order %s — could not geocode address.", order.id)
    return results
