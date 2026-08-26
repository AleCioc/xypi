from __future__ import annotations

from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry


def extract_points(geometry: BaseGeometry) -> list[tuple[float, float]]:
    """Extract discrete source points from any supported spatial pattern."""
    if isinstance(geometry, Point):
        return [(float(geometry.x), float(geometry.y))]
    if isinstance(geometry, MultiPoint):
        return [(float(p.x), float(p.y)) for p in geometry.geoms]
    if isinstance(geometry, LineString):
        return [(float(x), float(y)) for x, y in geometry.coords]
    if isinstance(geometry, MultiLineString):
        pts: list[tuple[float, float]] = []
        for line in geometry.geoms:
            pts.extend((float(x), float(y)) for x, y in line.coords)
        return pts
    if isinstance(geometry, Polygon):
        return _ring_points(geometry.exterior.coords)
    if isinstance(geometry, MultiPolygon):
        pts = []
        for poly in geometry.geoms:
            pts.extend(_ring_points(poly.exterior.coords))
        return pts
    if isinstance(geometry, GeometryCollection):
        pts = []
        for g in geometry.geoms:
            pts.extend(extract_points(g))
        return pts
    raise TypeError(f"Unsupported geometry type: {geometry.geom_type!r}")


def _ring_points(coords) -> list[tuple[float, float]]:
    ring = list(coords)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    return [(float(x), float(y)) for x, y in ring]
