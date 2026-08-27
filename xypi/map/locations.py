"""Map location presets and bbox helpers."""

from __future__ import annotations

import math
from typing import Any

MAP_PRESETS: dict[str, dict[str, Any]] = {
    "trento": {"name": "Trento, Italy", "center": (46.06737, 11.12144), "zoom": 16.0},
    "taranto": {"name": "Taranto, Italy", "center": (40.4712, 17.2432), "zoom": 16.0},
    "antwerp": {"name": "Antwerp, Belgium", "center": (51.22127, 4.39711), "zoom": 16.0},
}

DEFAULT_LOCATION = "trento"

BASE_MAP_CONFIG: dict[str, Any] = {
    "overpass_url": "https://overpass-api.de/api/interpreter",
    "corner_angle_deg": 25.0,
    "allow_insecure_ssl_fallback": True,
}


def bbox_from_center(
    lat: float,
    lon: float,
    zoom: float,
    width_px: int = 1100,
    height_px: int = 760,
) -> list[float]:
    """Return [south, west, north, east] using Web-Mercator zoom semantics."""
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    lon = float(lon)
    zoom = float(zoom)
    world = 256.0 * (2.0**zoom)
    x = (lon + 180.0) / 360.0 * world
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)) * world

    def unproject(px: float, py: float) -> tuple[float, float]:
        out_lon = px / world * 360.0 - 180.0
        n = math.pi - 2.0 * math.pi * py / world
        out_lat = math.degrees(math.atan(math.sinh(n)))
        return out_lat, out_lon

    north, west = unproject(x - width_px / 2.0, y - height_px / 2.0)
    south, east = unproject(x + width_px / 2.0, y + height_px / 2.0)
    return [south, west, north, east]


def make_map(name: str, lat: float, lon: float, zoom: float) -> dict[str, Any]:
    cfg = dict(BASE_MAP_CONFIG)
    cfg.update(
        {
            "id": name.lower().replace(" ", "_"),
            "name": name,
            "center": [float(lat), float(lon)],
            "zoom": float(zoom),
            "bbox": bbox_from_center(lat, lon, zoom),
        }
    )
    return cfg


def preset_map(location_id: str, zoom: float | None = None) -> dict[str, Any]:
    key = location_id.lower()
    if key not in MAP_PRESETS:
        raise KeyError(f"Unknown location {location_id!r}; choose from {', '.join(sorted(MAP_PRESETS))}")
    preset = MAP_PRESETS[key]
    z = preset["zoom"] if zoom is None else zoom
    lat, lon = preset["center"]
    cfg = make_map(preset["name"], lat, lon, z)
    cfg["preset_id"] = key
    return cfg


def list_locations() -> list[dict[str, Any]]:
    return [
        {"id": key, "name": val["name"], "center": list(val["center"]), "zoom": val["zoom"]}
        for key, val in sorted(MAP_PRESETS.items())
    ]
