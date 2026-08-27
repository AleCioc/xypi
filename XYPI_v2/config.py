"""Static startup configuration.

During a performance edit only live.py. Map choice happens before launch, either
with the presets below or with run_v11.py command-line arguments.
"""

import math

MAP_PRESETS = {
    "trento": {"name": "Trento, Italy", "center": (46.06737, 11.12144), "zoom": 16.0},
    "taranto": {"name": "Taranto, Italy", "center": (40.4712, 17.2432), "zoom": 16.0},
    "antwerp": {"name": "Antwerp, Belgium", "center": (51.22127, 4.39711), "zoom": 16.0},
}

DEFAULT_MAP = "trento"

BASE_MAP = {
    "overpass_url": "https://overpass-api.de/api/interpreter",
    "cache_dir": "cache",
    "corner_angle_deg": 25.0,
    "allow_insecure_ssl_fallback": True,
}

OSC = {
    "host": "127.0.0.1",
    "port": 57120,
    "path": "/xypi/corner",
}


def bbox_from_center(lat: float, lon: float, zoom: float, width_px: int = 1100, height_px: int = 760):
    """Return [south, west, north, east] using standard Web-Mercator zoom semantics."""
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    lon = float(lon)
    zoom = float(zoom)
    world = 256.0 * (2.0 ** zoom)
    x = (lon + 180.0) / 360.0 * world
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)) * world

    def unproject(px, py):
        out_lon = px / world * 360.0 - 180.0
        n = math.pi - 2.0 * math.pi * py / world
        out_lat = math.degrees(math.atan(math.sinh(n)))
        return out_lat, out_lon

    north, west = unproject(x - width_px / 2.0, y - height_px / 2.0)
    south, east = unproject(x + width_px / 2.0, y + height_px / 2.0)
    return [south, west, north, east]


def make_map(name: str, lat: float, lon: float, zoom: float):
    cfg = dict(BASE_MAP)
    cfg.update({"name": name, "center": [float(lat), float(lon)], "zoom": float(zoom), "bbox": bbox_from_center(lat, lon, zoom)})
    return cfg


def preset_map(name: str, zoom: float | None = None):
    key = name.lower()
    if key not in MAP_PRESETS:
        raise KeyError(f"Unknown map preset {name!r}; choose from {', '.join(sorted(MAP_PRESETS))}")
    p = MAP_PRESETS[key]
    z = p["zoom"] if zoom is None else zoom
    return make_map(p["name"], p["center"][0], p["center"][1], z)


MAP = preset_map(DEFAULT_MAP)
