from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon, mapping
from shapely.geometry import GeometryCollection
from shapely.geometry.base import BaseGeometry


@dataclass
class SpatialPattern:
    name: str
    geometry: BaseGeometry
    _gdf: gpd.GeoDataFrame | None = field(default=None, repr=False)

    def to_geodataframe(self) -> gpd.GeoDataFrame:
        if self._gdf is None:
            self._gdf = to_geodataframe(self.geometry, name=self.name)
        return self._gdf

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.geometry.bounds


def to_geodataframe(geometry: BaseGeometry, *, name: str = "pattern") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"name": [name], "geometry": [geometry]}, crs="EPSG:4326")


def polygon(coords: list[tuple[float, float]], *, name: str = "polygon") -> SpatialPattern:
    return SpatialPattern(name=name, geometry=Polygon(coords))


def multipoint(coords: list[tuple[float, float]], *, name: str = "multipoint") -> SpatialPattern:
    return SpatialPattern(name=name, geometry=MultiPoint([Point(x, y) for x, y in coords]))


def line_string(coords: list[tuple[float, float]], *, name: str = "line") -> SpatialPattern:
    return SpatialPattern(name=name, geometry=LineString(coords))


def multi_line_string(
    lines: list[list[tuple[float, float]]],
    *,
    name: str = "multiline",
) -> SpatialPattern:
    return SpatialPattern(name=name, geometry=MultiLineString([LineString(c) for c in lines]))


def multi_polygon(
    polygons: list[list[tuple[float, float]]],
    *,
    name: str = "multipolygon",
) -> SpatialPattern:
    return SpatialPattern(name=name, geometry=MultiPolygon([Polygon(c) for c in polygons]))


def point_graph(
    nodes: list[tuple[float, float]],
    edges: list[tuple[int, int]],
    *,
    name: str = "point_graph",
) -> SpatialPattern:
    """MultiPoint nodes plus LineString edges (for moving_points time flow)."""
    mp = MultiPoint([Point(x, y) for x, y in nodes])
    if edges:
        lines = MultiLineString(
            [LineString([(nodes[a][0], nodes[a][1]), (nodes[b][0], nodes[b][1])]) for a, b in edges]
        )
        geometry: BaseGeometry = GeometryCollection([mp, lines])
    else:
        geometry = mp
    return SpatialPattern(name=name, geometry=geometry)


def geometry_to_feature_dict(spatial_id: str, geometry: BaseGeometry) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": spatial_id,
        "properties": {"xypi_id": spatial_id},
        "geometry": mapping(geometry),
    }
