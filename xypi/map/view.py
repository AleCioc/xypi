"""Lat/lon ↔ normalized map coordinates."""

from __future__ import annotations

from dataclasses import dataclass

from xypi.map.geo import clamp01


@dataclass(frozen=True)
class MapView:
    south: float
    west: float
    north: float
    east: float

    @classmethod
    def from_bbox(cls, bbox: list[float]) -> MapView:
        return cls(*map(float, bbox))

    def normalize(self, lat: float, lon: float) -> tuple[float, float]:
        x = (lon - self.west) / max(self.east - self.west, 1e-12)
        y = (lat - self.south) / max(self.north - self.south, 1e-12)
        return clamp01(x), clamp01(y)

    def denormalize(self, x: float, y: float) -> tuple[float, float]:
        lon = self.west + clamp01(x) * (self.east - self.west)
        lat = self.south + clamp01(y) * (self.north - self.south)
        return lat, lon
