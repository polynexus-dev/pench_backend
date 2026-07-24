import json
import logging

from shapely.geometry import MultiPoint, Point, mapping, shape
from shapely.ops import unary_union, voronoi_diagram
from shapely.strtree import STRtree
from shapely.validation import make_valid
from shapely import wkt as shapely_wkt

logger = logging.getLogger(__name__)

# Rough degrees->km padding used only when no city/service-area boundary is available
# to clip against; ~0.01 deg is ~1.1km at the equator, enough to keep the fallback
# envelope tight around the outermost customers without needing an exact projection.
FALLBACK_BUFFER_DEGREES = 0.01


def _to_shapely(geom):
    """Accepts a GEOSGeometry, a GeoJSON-shaped dict, or an existing shapely geometry."""
    if geom is None:
        return None
    if type(geom).__module__.startswith("shapely"):
        return geom
    if isinstance(geom, dict):
        return shape(geom)
    return shapely_wkt.loads(geom.wkt)


def _from_shapely(geom, has_gis):
    if has_gis:
        from django.contrib.gis.geos import GEOSGeometry

        return GEOSGeometry(geom.wkt, srid=4326)
    return json.loads(json.dumps(mapping(geom)))


def generate_voronoi_zones(driver_points, clip_boundary=None, has_gis=False):
    """
    Partitions customer points into one non-overlapping zone per driver.

    Computes a single Voronoi diagram over every customer point (across all drivers),
    then dissolves the cells belonging to the same driver into that driver's zone. This
    guarantees the resulting zones tile the service area with no gaps/overlaps, and that
    every one of a driver's own customers falls inside their own zone.

    Args:
        driver_points: dict[driver_key -> list of (lon, lat) tuples].
        clip_boundary: GEOSGeometry, GeoJSON dict, or shapely (Multi)Polygon representing
            the service area to clip the tessellation to. Falls back to a buffered convex
            hull of all customer points if not provided.
        has_gis: if True, returned geometries are GEOSGeometry; otherwise plain GeoJSON dicts.

    Returns:
        {"zones": dict[driver_key -> geometry], "warnings": [str, ...]}
    """
    warnings = []

    all_points = []
    point_drivers = []
    for driver_key, points in driver_points.items():
        for lon, lat in points:
            all_points.append((lon, lat))
            point_drivers.append(driver_key)

    if len(all_points) < 2 or len(driver_points) < 2:
        raise ValueError(
            "Need customer points for at least 2 different drivers to generate a Voronoi partition."
        )

    multipoint = MultiPoint(all_points)

    boundary_shape = _to_shapely(clip_boundary)
    if boundary_shape is None or boundary_shape.is_empty:
        boundary_shape = multipoint.convex_hull.buffer(FALLBACK_BUFFER_DEGREES)

    diagram = voronoi_diagram(multipoint, envelope=boundary_shape)
    cells = [g for g in diagram.geoms if g.geom_type == "Polygon"]
    tree = STRtree(cells)

    driver_cells = {key: [] for key in driver_points}
    unmatched = 0
    for (lon, lat), driver_key in zip(all_points, point_drivers):
        pt = Point(lon, lat)
        cell = next((cells[i] for i in tree.query(pt) if cells[i].intersects(pt)), None)
        if cell is None:
            unmatched += 1
            continue
        driver_cells[driver_key].append(cell.intersection(boundary_shape))

    if unmatched:
        warnings.append(
            f"{unmatched} customer point(s) could not be matched to a Voronoi cell and were excluded."
        )

    zones = {}
    for driver_key, cells_for_driver in driver_cells.items():
        if not cells_for_driver:
            continue
        merged = unary_union(cells_for_driver)
        if not merged.is_valid:
            merged = make_valid(merged)
        if merged.geom_type not in ("Polygon", "MultiPolygon"):
            merged = merged.convex_hull
        if merged.geom_type == "MultiPolygon":
            warnings.append(
                f"Driver '{driver_key}' has customers in disjoint clusters; used a convex hull "
                f"to merge them into a single zone. Review this zone's boundary manually."
            )
            merged = merged.convex_hull
        zones[driver_key] = _from_shapely(merged, has_gis)

    return {"zones": zones, "warnings": warnings}
