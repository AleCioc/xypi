from __future__ import annotations

import hashlib
import heapq
import json
import math
import os
import random
import socket
import ssl
import struct
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal


# -----------------------------------------------------------------------------
# Small utilities
# -----------------------------------------------------------------------------


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(a))


def turn_deg(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    ax, ay = a[1] - b[1], a[0] - b[0]
    cx, cy = c[1] - b[1], c[0] - b[0]
    na = max(math.hypot(ax, ay), 1e-12)
    nc = max(math.hypot(cx, cy), 1e-12)
    cosv = max(-1.0, min(1.0, (ax * cx + ay * cy) / (na * nc)))
    return abs(180.0 - math.degrees(math.acos(cosv)))


def random_colour() -> str:
    return f"hsl({random.randint(0, 359)} 78% 58%)"


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


# -----------------------------------------------------------------------------
# Locations and normalized map coordinates
# -----------------------------------------------------------------------------


MAP_PRESETS: dict[str, dict[str, Any]] = {
    "trento": {"name": "Trento, Italy", "center": (46.06737, 11.12144), "zoom": 16.0},
    "taranto": {"name": "Taranto, Italy", "center": (40.4712, 17.2432), "zoom": 16.0},
    "antwerp": {"name": "Antwerp, Belgium", "center": (51.22127, 4.39711), "zoom": 16.0},
}
DEFAULT_LOCATION = "trento"


def bbox_from_center(lat: float, lon: float, zoom: float, width_px: int = 1100, height_px: int = 760) -> list[float]:
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    lon, zoom = float(lon), float(zoom)
    world = 256.0 * (2.0**zoom)
    x = (lon + 180.0) / 360.0 * world
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1.0 + sin_lat) / (1.0 - sin_lat)) / (4.0 * math.pi)) * world

    def unproject(px: float, py: float) -> tuple[float, float]:
        out_lon = px / world * 360.0 - 180.0
        n = math.pi - 2.0 * math.pi * py / world
        return math.degrees(math.atan(math.sinh(n))), out_lon

    north, west = unproject(x - width_px / 2.0, y - height_px / 2.0)
    south, east = unproject(x + width_px / 2.0, y + height_px / 2.0)
    return [south, west, north, east]


def preset_map(location_id: str, zoom: float | None = None) -> dict[str, Any]:
    key = location_id.lower()
    if key not in MAP_PRESETS:
        raise KeyError(f"Unknown location {location_id!r}; choose from {', '.join(sorted(MAP_PRESETS))}")
    preset = MAP_PRESETS[key]
    z = float(preset["zoom"] if zoom is None else zoom)
    lat, lon = preset["center"]
    return {
        "id": key,
        "name": preset["name"],
        "center": [lat, lon],
        "zoom": z,
        "bbox": bbox_from_center(lat, lon, z),
        "overpass_url": "https://overpass-api.de/api/interpreter",
        "corner_angle_deg": 25.0,
        "allow_insecure_ssl_fallback": True,
    }


def list_locations() -> list[dict[str, Any]]:
    return [
        {"id": key, "name": val["name"], "center": list(val["center"]), "zoom": val["zoom"]}
        for key, val in sorted(MAP_PRESETS.items())
    ]


@dataclass(frozen=True)
class MapView:
    south: float
    west: float
    north: float
    east: float

    @classmethod
    def from_bbox(cls, bbox: list[float]) -> "MapView":
        return cls(*map(float, bbox))

    def normalize(self, lat: float, lon: float) -> tuple[float, float]:
        x = (lon - self.west) / max(self.east - self.west, 1e-12)
        y = (lat - self.south) / max(self.north - self.south, 1e-12)
        return clamp01(x), clamp01(y)

    def denormalize(self, x: float, y: float) -> tuple[float, float]:
        lon = self.west + clamp01(x) * (self.east - self.west)
        lat = self.south + clamp01(y) * (self.north - self.south)
        return lat, lon


# -----------------------------------------------------------------------------
# Overpass: streets + POIs
# -----------------------------------------------------------------------------


OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

POI_FILTERS: dict[str, tuple[str, str]] = {
    "schools": ("amenity", "school"),
    "hospitals": ("amenity", "hospital"),
    "restaurants": ("amenity", "restaurant"),
    "bars": ("amenity", "bar"),
    "bus_stops": ("highway", "bus_stop"),
    "monuments": ("historic", "monument"),
}
POI_EXTRA_FILTERS: dict[str, tuple[tuple[str, str], ...]] = {
    "schools": (("amenity", "kindergarten"), ("amenity", "college"), ("building", "school")),
    "hospitals": (("amenity", "clinic"), ("healthcare", "hospital")),
    "restaurants": (),
    "bars": (("amenity", "pub"),),
    "bus_stops": (),
    "monuments": (),
}
POI_ALIASES = {
    "school": "schools", "kindergarten": "schools", "college": "schools",
    "hospital": "hospitals", "clinic": "hospitals",
    "restaurant": "restaurants", "bar": "bars", "pub": "bars",
    "bus_stop": "bus_stops", "busstop": "bus_stops", "monument": "monuments",
}


def normalize_poi_category(category: str) -> str:
    key = str(category).strip().lower().replace(" ", "_").replace("-", "_")
    key = POI_ALIASES.get(key, key)
    if key not in POI_FILTERS:
        raise KeyError(f"Unknown POI category {category!r}; choose from {', '.join(POI_FILTERS)}")
    return key


def _cache_path(cache_dir: Path, prefix: str, bbox: list[float]) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps([round(v, 8) for v in bbox]).encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{prefix}_{key}.json"


def _read_overpass(url: str, body: bytes, timeout: int, context=None) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers={"User-Agent": "XYPI/1.0"})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _overpass_query(map_cfg: dict[str, Any], query: str, timeout: int = 120) -> dict[str, Any]:
    body = urllib.parse.urlencode({"data": query}).encode()
    urls = [map_cfg.get("overpass_url", OVERPASS_MIRRORS[0])]
    urls.extend(url for url in OVERPASS_MIRRORS if url not in urls)
    last_exc: Exception | None = None
    for url in urls:
        for attempt in range(2):
            try:
                return _read_overpass(url, body, timeout)
            except Exception as exc:
                last_exc = exc
                reason = getattr(exc, "reason", None)
                ssl_error = isinstance(exc, ssl.SSLCertVerificationError) or isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc)
                if ssl_error:
                    try:
                        import certifi  # type: ignore
                        return _read_overpass(url, body, timeout, ssl.create_default_context(cafile=certifi.where()))
                    except Exception as cert_exc:
                        last_exc = cert_exc
                        if map_cfg.get("allow_insecure_ssl_fallback", True):
                            try:
                                return _read_overpass(url, body, timeout, ssl._create_unverified_context())
                            except Exception as insecure_exc:
                                last_exc = insecure_exc
                retryable = isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 502, 503, 504)
                retryable = retryable or isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()
                if retryable and attempt == 0:
                    time.sleep(2.0)
                    continue
                break
    raise RuntimeError(f"All Overpass mirrors failed: {last_exc}") from last_exc


def load_street_raw(map_cfg: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    cache = _cache_path(cache_dir, "streets", map_cfg["bbox"])
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    south, west, north, east = map_cfg["bbox"]
    query = f'''[out:json][timeout:90];
way["highway"]["highway"!~"motorway|motorway_link|trunk|trunk_link|raceway|construction|proposed"]({south},{west},{north},{east});
(._;>;); out body;'''
    data = _overpass_query(map_cfg, query)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def _poi_category(tags: dict[str, Any]) -> str | None:
    for name, primary in POI_FILTERS.items():
        for key, value in (primary, *POI_EXTRA_FILTERS.get(name, ())):
            if tags.get(key) == value:
                return name
    return None


def load_pois(map_cfg: dict[str, Any], cache_dir: Path) -> dict[str, list[dict[str, Any]]]:
    cache = _cache_path(cache_dir, "pois_v2", map_cfg["bbox"])
    if cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        return {name: list(cached.get(name, [])) for name in POI_FILTERS}
    south, west, north, east = map_cfg["bbox"]
    lines = ["[out:json][timeout:90];", "("]
    seen_filters: set[tuple[str, str]] = set()
    for name, primary in POI_FILTERS.items():
        for key, value in (primary, *POI_EXTRA_FILTERS.get(name, ())):
            if (key, value) in seen_filters:
                continue
            seen_filters.add((key, value))
            lines.append(f'nwr["{key}"="{value}"]({south},{west},{north},{east});')
    lines.extend([");", "out center tags;"])
    raw = _overpass_query(map_cfg, "\n".join(lines))
    view = MapView.from_bbox(map_cfg["bbox"])
    result = {name: [] for name in POI_FILTERS}
    seen_ids: dict[str, set[str]] = {name: set() for name in POI_FILTERS}
    for element in raw.get("elements", []):
        tags = element.get("tags") or {}
        category = _poi_category(tags)
        if category is None:
            continue
        osm_id = f"{element.get('type', 'osm')}/{element.get('id', '')}"
        if osm_id in seen_ids[category]:
            continue
        seen_ids[category].add(osm_id)
        if element.get("type") == "node" and "lat" in element and "lon" in element:
            lat, lon = float(element["lat"]), float(element["lon"])
        else:
            center = element.get("center") or {}
            if "lat" not in center or "lon" not in center:
                continue
            lat, lon = float(center["lat"]), float(center["lon"])
        x, y = view.normalize(lat, lon)
        result[category].append({
            "id": osm_id,
            "name": tags.get("name") or tags.get("operator") or category.rstrip("s"),
            "category": category,
            "lat": lat, "lon": lon, "x": x, "y": y,
            "tags": tags,
        })
    for items in result.values():
        items.sort(key=lambda item: (item.get("name", ""), item["id"]))
    cache.write_text(json.dumps(result), encoding="utf-8")
    return result


# -----------------------------------------------------------------------------
# Street graph
# -----------------------------------------------------------------------------


@dataclass
class Edge:
    a: int
    b: int
    length_m: float
    geometry: list[tuple[float, float]]


class StreetGraph:
    def __init__(self, view: MapView):
        self.view = view
        self.nodes: dict[int, tuple[float, float]] = {}
        self.edges: dict[tuple[int, int], Edge] = {}
        self.adj: dict[int, dict[int, Edge]] = {}

    def add_edge(self, edge: Edge) -> None:
        key = tuple(sorted((edge.a, edge.b)))
        old = self.edges.get(key)
        if old is not None and old.length_m <= edge.length_m:
            return
        self.edges[key] = edge
        self.adj.setdefault(edge.a, {})[edge.b] = edge
        self.adj.setdefault(edge.b, {})[edge.a] = edge

    def xy(self, node: int) -> tuple[float, float]:
        lat, lon = self.nodes[node]
        return self.view.normalize(lat, lon)

    def nearest_node(self, xy: tuple[float, float], allowed: set[int] | None = None) -> int:
        nodes = allowed or set(self.nodes)
        if not nodes:
            raise RuntimeError("No street nodes are available")
        x, y = xy
        return min(nodes, key=lambda n: (self.xy(n)[0] - x) ** 2 + (self.xy(n)[1] - y) ** 2)

    def shortest_path(self, start: int, goal: int, allowed: set[int] | None = None) -> list[int]:
        if start == goal:
            return [start]
        allowed = allowed or set(self.nodes)
        dist = {start: 0.0}
        prev: dict[int, int] = {}
        queue = [(0.0, start)]
        while queue:
            d, node = heapq.heappop(queue)
            if d != dist.get(node):
                continue
            if node == goal:
                break
            for nxt, edge in self.adj.get(node, {}).items():
                if nxt not in allowed:
                    continue
                nd = d + edge.length_m
                if nd < dist.get(nxt, float("inf")):
                    dist[nxt], prev[nxt] = nd, node
                    heapq.heappush(queue, (nd, nxt))
        if goal not in dist:
            return []
        path = [goal]
        while path[-1] != start:
            path.append(prev[path[-1]])
        return list(reversed(path))

    def largest_component(self, nodes: set[int]) -> set[int]:
        remaining, best = set(nodes), set()
        while remaining:
            seed = remaining.pop()
            comp, stack = {seed}, [seed]
            while stack:
                node = stack.pop()
                for nxt in self.adj.get(node, {}):
                    if nxt in remaining and nxt in nodes:
                        remaining.remove(nxt)
                        comp.add(nxt)
                        stack.append(nxt)
            if len(comp) > len(best):
                best = comp
        return best

    def public_state(self) -> dict[str, Any]:
        return {
            "nodes": {str(n): self.xy(n) for n in self.nodes},
            "edges": [{
                "a": e.a, "b": e.b, "length_m": e.length_m,
                "geometry": [self.view.normalize(lat, lon) for lat, lon in e.geometry],
            } for e in self.edges.values()],
        }


def graph_from_overpass(data: dict[str, Any], view: MapView, corner_angle_deg: float = 25.0) -> StreetGraph:
    raw_nodes = {int(e["id"]): (float(e["lat"]), float(e["lon"])) for e in data.get("elements", []) if e.get("type") == "node"}
    ways = [e for e in data.get("elements", []) if e.get("type") == "way" and len(e.get("nodes", [])) >= 2]
    occurrences: dict[int, int] = {}
    for way in ways:
        for node in set(map(int, way["nodes"])):
            occurrences[node] = occurrences.get(node, 0) + 1
    graph = StreetGraph(view)
    graph.nodes = raw_nodes
    for way in ways:
        ids = [int(n) for n in way["nodes"] if int(n) in raw_nodes]
        if len(ids) < 2:
            continue
        important = {0, len(ids) - 1}
        for i in range(1, len(ids) - 1):
            node = ids[i]
            if occurrences.get(node, 0) > 1:
                important.add(i)
            elif turn_deg(raw_nodes[ids[i - 1]], raw_nodes[node], raw_nodes[ids[i + 1]]) >= corner_angle_deg:
                important.add(i)
        idxs = sorted(important)
        for i0, i1 in zip(idxs, idxs[1:]):
            segment = ids[i0:i1 + 1]
            geom = [raw_nodes[n] for n in segment]
            length = sum(haversine_m(p0[0], p0[1], p1[0], p1[1]) for p0, p1 in zip(geom, geom[1:]))
            if length > 0:
                graph.add_edge(Edge(segment[0], segment[-1], length, geom))
    used = set(graph.adj)
    graph.nodes = {n: graph.nodes[n] for n in used}
    return graph


def route_path_nodes(graph: StreetGraph, points: list[tuple[float, float]], close: bool = False) -> list[int]:
    anchors = [graph.nearest_node(p) for p in points]
    if len(anchors) == 1:
        return anchors
    pairs = list(zip(anchors, anchors[1:]))
    if close and len(anchors) > 2:
        pairs.append((anchors[-1], anchors[0]))
    ordered: list[int] = []
    for start, goal in pairs:
        part = graph.shortest_path(start, goal)
        if part:
            ordered.extend(part[1:] if ordered and ordered[-1] == part[0] else part)
    return ordered or [anchors[0]]


def route_geometry(graph: StreetGraph, path: list[int]) -> list[tuple[float, float]]:
    if len(path) < 2:
        return [graph.xy(path[0])] if path else []
    out: list[tuple[float, float]] = []
    for start, target in zip(path, path[1:]):
        edge = graph.adj[start][target]
        geom = edge.geometry if edge.a == start and edge.b == target else list(reversed(edge.geometry))
        xy = [graph.view.normalize(lat, lon) for lat, lon in geom]
        out.extend(xy[1:] if out and xy and out[-1] == xy[0] else xy)
    return out


def polygon_centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    if not coords:
        return 0.5, 0.5
    area2 = cx = cy = 0.0
    pts = coords + [coords[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area2) < 1e-12:
        return sum(x for x, _ in coords) / len(coords), sum(y for _, y in coords) / len(coords)
    return cx / (3.0 * area2), cy / (3.0 * area2)


def point_in_polygon(point: tuple[float, float], coords: list[tuple[float, float]]) -> bool:
    if len(coords) < 3:
        return False
    x, y, inside = point[0], point[1], False
    pts = coords + [coords[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if (y0 > y) != (y1 > y):
            x_at_y = (x1 - x0) * (y - y0) / (y1 - y0) + x0
            if x < x_at_y:
                inside = not inside
    return inside


def area_nodes(graph: StreetGraph, coords: list[tuple[float, float]]) -> set[int]:
    selected = graph.largest_component({n for n in graph.nodes if point_in_polygon(graph.xy(n), coords)})
    return selected or {graph.nearest_node(polygon_centroid(coords))}


def edge_position(graph: StreetGraph, edge: Edge, start: int, target: int, t: float) -> tuple[float, float]:
    geom = edge.geometry if edge.a == start and edge.b == target else list(reversed(edge.geometry))
    if len(geom) < 2:
        return graph.xy(target)
    lengths = [0.0]
    for p0, p1 in zip(geom, geom[1:]):
        lengths.append(lengths[-1] + haversine_m(p0[0], p0[1], p1[0], p1[1]))
    wanted = clamp01(t) * max(lengths[-1], 1e-9)
    for i in range(1, len(lengths)):
        if wanted <= lengths[i]:
            u = (wanted - lengths[i - 1]) / max(lengths[i] - lengths[i - 1], 1e-9)
            lat = geom[i - 1][0] + (geom[i][0] - geom[i - 1][0]) * u
            lon = geom[i - 1][1] + (geom[i][1] - geom[i - 1][1]) * u
            return graph.view.normalize(lat, lon)
    return graph.xy(target)


# -----------------------------------------------------------------------------
# Grid sequencer
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PointPattern:
    name: str
    points: tuple[tuple[float, float], ...]
    category: str | None = None

    def to_geodataframe(self):
        """Compatibility shim: this project no longer needs GeoPandas."""
        return self


@dataclass
class GridEvent:
    step: int
    row: int
    x: float
    y: float
    value: float
    midi: int
    hit: bool = True

    def public_state(self) -> dict[str, Any]:
        return {"step": self.step, "row": self.row, "x": self.x, "y": self.y, "value": self.value, "midi": self.midi, "hit": self.hit}


@dataclass(frozen=True)
class GridSpec:
    places: str
    steps: int = 8
    bpm: float = 120.0
    direction: Literal["horizontal", "vertical"] = "horizontal"
    movement: Literal["linear", "backforth", "random"] = "linear"
    root_midi: int = 48
    pitch_range: int = 12
    beats_per_step: float = 1.0
    time_pattern: list[int] | int = 1
    output: Literal["osc"] = "osc"
    amp: float = 0.45
    max_points: int = 120
    sound: str | None = None


def grid(places: str, *, steps: int = 8, bpm: float = 120.0, direction: str = "horizontal", movement: str = "linear", root_midi: int = 48, pitch_range: int = 12, beats_per_step: float = 1.0, time_pattern: list[int] | int = 1, output: str = "osc", amp: float = 0.45, max_points: int = 120, sound: str | None = None, **kwargs: Any) -> GridSpec:
    if "rows" in kwargs:
        raise TypeError("grid() no longer accepts rows; steps defines both grid axes")
    if "mode" in kwargs:
        raise TypeError("grid() no longer accepts mode; choose the SuperCollider synth with sound=...")
    if kwargs:
        raise TypeError(f"Unknown grid option(s): {', '.join(sorted(kwargs))}")
    category = normalize_poi_category(places)
    direction_key = str(direction).strip().lower().replace("-", "_")
    direction_aliases = {"x": "horizontal", "horizontal": "horizontal", "h": "horizontal", "y": "vertical", "vertical": "vertical", "v": "vertical"}
    if direction_key not in direction_aliases:
        raise ValueError("direction must be 'horizontal' or 'vertical'")
    direction_value = direction_aliases[direction_key]
    movement_key = str(movement).strip().lower().replace("-", "").replace("_", "")
    movement_aliases = {"linear": "linear", "forward": "linear", "backforth": "backforth", "backandforth": "backforth", "pingpong": "backforth", "random": "random"}
    if movement_key not in movement_aliases:
        raise ValueError("movement must be 'linear', 'backforth', or 'random'")
    movement_value = movement_aliases[movement_key]
    if int(steps) < 1:
        raise ValueError("steps must be >= 1")
    if float(bpm) <= 0:
        raise ValueError("bpm must be > 0")
    if float(beats_per_step) <= 0:
        raise ValueError("beats_per_step must be > 0")
    if int(max_points) < 0:
        raise ValueError("max_points must be >= 0")
    if output not in ("browser", "osc", "both"):
        raise ValueError("output must be 'osc' (legacy 'browser'/'both' are accepted and normalized to OSC)")
    return GridSpec(places=category, steps=int(steps), bpm=float(bpm), direction=direction_value, movement=movement_value, root_midi=int(root_midi), pitch_range=int(pitch_range), beats_per_step=float(beats_per_step), time_pattern=time_pattern, output="osc", amp=float(amp), max_points=int(max_points), sound=None if sound is None else str(sound))


@dataclass
class GridChannel:
    name: str
    pattern: PointPattern
    time_flow: Literal["x", "y"] = "x"
    movement: Literal["linear", "backforth", "random"] = "linear"
    root_midi: int = 48
    pitch_range: int = 12
    pitch_cells: int = 8
    n_steps: int = 8
    bpm: float = 150.0
    beats_per_step: float = 1.0
    time_pattern: list[int] | int = 1
    output: Literal["osc"] = "osc"
    amp: float = 0.45
    sound: str | None = None
    current_step: int = -1
    events: list[GridEvent] = field(default_factory=list)
    cells: list[tuple[int, int]] = field(default_factory=list)

    @property
    def step_sec(self) -> float:
        return 60.0 / self.bpm * self.beats_per_step

    def public_state(self) -> dict[str, Any]:
        return {
            "name": self.name, "source": self.pattern.name, "category": self.pattern.category,
            "time_flow": self.time_flow, "direction": "horizontal" if self.time_flow == "x" else "vertical",
            "movement": self.movement, "sound": self.sound, "root_midi": self.root_midi,
            "pitch_range": self.pitch_range, "pitch_cells": self.pitch_cells, "n_steps": self.n_steps,
            "bpm": self.bpm, "beats_per_step": self.beats_per_step, "output": "osc", "amp": self.amp, "current_step": self.current_step,
            "points": [{"x": x, "y": y} for x, y in self.pattern.points],
            "cells": [{"step": step, "row": row} for step, row in self.cells],
            "events": [event.public_state() for event in self.events],
        }


def pois_to_points(items: Iterable[dict[str, Any]], max_points: int | None = None) -> list[tuple[float, float]]:
    out = [(clamp01(item["x"]), clamp01(item["y"])) for item in items if "x" in item and "y" in item]
    return out if max_points is None else out[:max(0, int(max_points))]


def point_graph(nodes: Iterable[tuple[float, float]], edges: Iterable[tuple[int, int]] | None = None, name: str = "point_graph") -> PointPattern:
    # Edges are accepted for compatibility with older live scripts; the fixed POI grid only needs the nodes.
    return PointPattern(name=name, points=tuple((clamp01(x), clamp01(y)) for x, y in nodes))


def _pattern_mask(pattern: list[int] | int, n_steps: int) -> list[int]:
    if pattern == 1:
        return [1] * n_steps
    if pattern == 0:
        return [0] * n_steps
    seq = [int(bool(v)) for v in pattern]
    if not seq:
        return [0] * n_steps
    return (seq * (n_steps // len(seq) + 1))[:n_steps]


def _cell(value: float, n: int) -> int:
    return max(0, min(n - 1, int(clamp01(value) * n)))


def interpret_grid(channel: GridChannel) -> GridChannel:
    if channel.n_steps < 1 or channel.pitch_cells < 1:
        raise ValueError("n_steps and pitch_cells must be >= 1")
    mask = _pattern_mask(channel.time_pattern, channel.n_steps)
    cells: dict[tuple[int, int], tuple[float, float]] = {}
    for x, y in channel.pattern.points:
        if channel.time_flow == "x":
            step, row = _cell(x, channel.n_steps), _cell(y, channel.pitch_cells)
        else:
            step, row = _cell(y, channel.n_steps), _cell(x, channel.pitch_cells)
        cells.setdefault((step, row), (x, y))
    channel.cells = sorted(cells)
    events: list[GridEvent] = []
    for (step, row), (x, y) in sorted(cells.items()):
        if not mask[step]:
            continue
        if channel.pitch_cells == 1:
            semitone = 0
        else:
            semitone = round(row / (channel.pitch_cells - 1) * channel.pitch_range)
        midi = int(channel.root_midi + semitone)
        value = float(midi)
        events.append(GridEvent(step=step, row=row, x=x, y=y, value=value, midi=midi))
    channel.events = events
    return channel


# -----------------------------------------------------------------------------
# OSC (raw UDP; no python-osc dependency)
# -----------------------------------------------------------------------------


def _osc_string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\0"
    return raw + b"\0" * ((4 - len(raw) % 4) % 4)


def osc_packet(path: str, args: list[Any]) -> bytes:
    tags, payload = ",", b""
    for arg in args:
        if isinstance(arg, bool) or isinstance(arg, int):
            tags += "i"
            payload += struct.pack(">i", int(arg))
        elif isinstance(arg, float):
            tags += "f"
            payload += struct.pack(">f", float(arg))
        else:
            tags += "s"
            payload += _osc_string(str(arg))
    return _osc_string(path) + _osc_string(tags) + payload


class OscSender:
    def __init__(self, host: str = "127.0.0.1", port: int = 57120):
        self.addr = (host, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, path: str, *args: Any) -> None:
        self.sock.sendto(osc_packet(path, list(args)), self.addr)


class GridOscPlayback:
    """OSC-only grid clock. Grid hits use the exact same /xypi/corner message as street agents."""

    def __init__(self, sender: OscSender):
        self.sender = sender
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._generation = 0
        self._channels: list[GridChannel] = []

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def sync(self, channels: list[GridChannel], autostart: bool = True) -> None:
        self.stop(clear_channels=False)
        self._channels = list(channels)
        if autostart and self._channels:
            self.start()

    def start(self) -> None:
        if self.is_running or not self._channels:
            return
        self._generation += 1
        generation = self._generation
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(generation, list(self._channels)), daemon=True, name="xypi-grid-osc")
        self._thread.start()

    @staticmethod
    def _advance(channel: GridChannel, state: dict[str, Any]) -> None:
        if channel.n_steps <= 1:
            state["step"] = 0
            return
        if channel.movement == "random":
            state["step"] = random.randrange(channel.n_steps)
            return
        if channel.movement == "backforth":
            direction = int(state.get("direction", 1))
            nxt = int(state["step"]) + direction
            if nxt >= channel.n_steps:
                direction, nxt = -1, channel.n_steps - 2
            elif nxt < 0:
                direction, nxt = 1, 1
            state["direction"], state["step"] = direction, nxt
            return
        state["step"] = (int(state["step"]) + 1) % channel.n_steps

    @staticmethod
    def _event_sound(channel: GridChannel, event: GridEvent) -> str:
        return channel.sound or "sine"

    def _run(self, generation: int, channels: list[GridChannel]) -> None:
        states = []
        for channel in channels:
            first = random.randrange(channel.n_steps) if channel.movement == "random" and channel.n_steps > 1 else 0
            channel.current_step = first
            states.append({"channel": channel, "step": first, "direction": 1, "next": time.perf_counter()})
        while not self._stop.is_set() and generation == self._generation:
            now = time.perf_counter()
            next_due = now + 0.05
            for state in states:
                channel: GridChannel = state["channel"]
                if now + 1e-6 >= state["next"]:
                    step = int(state["step"])
                    channel.current_step = step
                    for event in channel.events:
                        if event.step != step or not event.hit:
                            continue
                        self.sender.send("/xypi/corner", channel.name, self._event_sound(channel, event), float(event.y), float(event.x), float(channel.step_sec))
                    self._advance(channel, state)
                    state["next"] += channel.step_sec
                    if state["next"] < now - channel.step_sec:
                        state["next"] = now + channel.step_sec
                next_due = min(next_due, state["next"])
            self._stop.wait(max(0.002, min(0.05, next_due - time.perf_counter())))
        for channel in channels:
            channel.current_step = -1

    def stop(self, clear_channels: bool = False) -> None:
        self._stop.set()
        self._generation += 1
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        for channel in self._channels:
            channel.current_step = -1
        if clear_channels:
            self._channels = []


# -----------------------------------------------------------------------------
# Street agents and behaviours
# -----------------------------------------------------------------------------


@dataclass
class AgentContext:
    current_node: int
    previous_node: int | None
    neighbours: tuple[int, ...]
    graph: StreetGraph
    layer_shape: str
    layer_coords: tuple[tuple[float, float], ...]

    @property
    def current_xy(self) -> tuple[float, float]:
        return self.graph.xy(self.current_node)

    @property
    def points(self) -> tuple[tuple[float, float], ...]:
        return self.layer_coords if self.layer_shape == "points" else ()

    def node_xy(self, node: int) -> tuple[float, float]:
        return self.graph.xy(node)

    def edge_length(self, node: int) -> float:
        return self.graph.adj[self.current_node][node].length_m


def choices(ctx: AgentContext) -> list[int]:
    return [n for n in ctx.neighbours if n != ctx.previous_node] or list(ctx.neighbours)


def _direction_score(ctx: AgentContext, node: int, vx: float, vy: float) -> float:
    cx, cy = ctx.current_xy
    nx, ny = ctx.node_xy(node)
    dx, dy = nx - cx, ny - cy
    return (dx * vx + dy * vy) / (max(math.hypot(dx, dy), 1e-9) * max(math.hypot(vx, vy), 1e-9))


def random_walk(ctx: AgentContext) -> int:
    return random.choice(choices(ctx))


def straightish(ctx: AgentContext) -> int:
    opts = choices(ctx)
    if ctx.previous_node is None or len(opts) == 1:
        return random.choice(opts)
    px, py = ctx.node_xy(ctx.previous_node)
    cx, cy = ctx.current_xy
    return max(opts, key=lambda node: _direction_score(ctx, node, cx - px, cy - py))


def backtrack(ctx: AgentContext) -> int:
    return ctx.previous_node if ctx.previous_node in ctx.neighbours else random.choice(list(ctx.neighbours))


def clockwiseish(ctx: AgentContext) -> int:
    opts = choices(ctx)
    if ctx.previous_node is None:
        return random.choice(opts)
    px, py = ctx.node_xy(ctx.previous_node)
    cx, cy = ctx.current_xy
    ix, iy = cx - px, cy - py
    return min(opts, key=lambda node: ix * (ctx.node_xy(node)[1] - cy) - iy * (ctx.node_xy(node)[0] - cx))


def anticlockwiseish(ctx: AgentContext) -> int:
    opts = choices(ctx)
    if ctx.previous_node is None:
        return random.choice(opts)
    px, py = ctx.node_xy(ctx.previous_node)
    cx, cy = ctx.current_xy
    ix, iy = cx - px, cy - py
    return max(opts, key=lambda node: ix * (ctx.node_xy(node)[1] - cy) - iy * (ctx.node_xy(node)[0] - cx))


def shortest_street(ctx: AgentContext) -> int:
    return min(choices(ctx), key=ctx.edge_length)


def longest_street(ctx: AgentContext) -> int:
    return max(choices(ctx), key=ctx.edge_length)


def point_attract(ctx: AgentContext) -> int:
    opts = choices(ctx)
    if not ctx.points:
        return random.choice(opts)
    cx, cy = ctx.current_xy
    vx = vy = 0.0
    for px, py in ctx.points:
        dx, dy = px - cx, py - cy
        weight = 1.0 / max(dx * dx + dy * dy, 0.0025)
        vx += dx * weight
        vy += dy * weight
    return max(opts, key=lambda node: _direction_score(ctx, node, vx, vy) + random.uniform(-0.06, 0.06))


BEHAVIOURS: dict[str, Callable[[AgentContext], int]] = {
    "random_walk": random_walk, "straightish": straightish, "backtrack": backtrack,
    "clockwiseish": clockwiseish, "anticlockwiseish": anticlockwiseish,
    "shortest_street": shortest_street, "longest_street": longest_street, "point_attract": point_attract,
}
_DEFAULT_BEHAVIOUR = object()


@dataclass(frozen=True)
class StreetAgentSpec:
    shape: str
    coords: tuple[tuple[float, float], ...]
    speed_mps: float
    behaviour: object
    sound: str
    output: str = "osc"


def moving_agent(shape: str, coords: list | tuple | None = None, *, speed: float = 1.4, behaviour=_DEFAULT_BEHAVIOUR, sound: str = "sine", output: str = "osc", **kwargs: Any) -> StreetAgentSpec:
    if kwargs:
        raise TypeError(f"Unknown moving_agent option(s): {', '.join(sorted(kwargs))}")
    shape = str(shape).strip().lower()
    if shape not in {"points", "line", "area"}:
        raise ValueError("shape must be one of: points, line, area")
    if coords is None:
        raise ValueError(f"{shape} requires coordinates")
    pts = tuple(tuple(map(float, p)) for p in coords)
    minimum = {"points": 1, "line": 2, "area": 3}[shape]
    if len(pts) < minimum or any(len(p) != 2 or not 0 <= p[0] <= 1 or not 0 <= p[1] <= 1 for p in pts):
        raise ValueError(f"{shape} needs at least {minimum} normalized (x, y) coordinates in [0, 1]")
    if speed <= 0:
        raise ValueError("speed must be > 0")
    if behaviour is _DEFAULT_BEHAVIOUR:
        behaviour = {"points": point_attract, "line": straightish, "area": random_walk}[shape]
    if behaviour is not None and not callable(behaviour) and not isinstance(behaviour, str):
        raise TypeError("behaviour must be a function, function name, or None")
    if output not in ("osc", "none"):
        raise ValueError("street-agent output must be 'osc' or 'none'")
    return StreetAgentSpec(shape, pts, float(speed), behaviour, str(sound), output)


agent = moving_agent


@dataclass
class AgentLayer:
    name: str
    spec: StreetAgentSpec
    colour: str
    allowed_nodes: set[int] = field(default_factory=set)
    street_paths: list[list[tuple[float, float]]] = field(default_factory=list)

    def public_state(self) -> dict[str, Any]:
        return {"name": self.name, "shape": self.spec.shape, "coords": list(self.spec.coords), "colour": self.colour, "street_paths": self.street_paths, "sound": self.spec.sound, "speed_mps": self.spec.speed_mps, "output": self.spec.output}


@dataclass
class StreetAgent:
    name: str
    layer: AgentLayer
    node: int
    behaviour_name: str | None
    behaviour_fn: Callable[[AgentContext], int] | None
    previous_node: int | None = None
    target_node: int | None = None
    edge: Edge | None = None
    edge_started: float = 0.0
    edge_duration: float = 0.0
    x: float = 0.0
    y: float = 0.0
    last_event: dict[str, Any] | None = None

    def public_state(self) -> dict[str, Any]:
        return {"name": self.name, "layer": self.layer.name, "x": self.x, "y": self.y, "node": self.node, "target_node": self.target_node, "behaviour": self.behaviour_name, "sound": self.layer.spec.sound, "speed_mps": self.layer.spec.speed_mps, "edge_duration": self.edge_duration, "last_event": self.last_event}


def configure_layer(graph: StreetGraph, layer: AgentLayer) -> None:
    coords = list(layer.spec.coords)
    if layer.spec.shape == "points":
        layer.allowed_nodes = graph.largest_component(set(graph.nodes))
    elif layer.spec.shape == "line":
        path = route_path_nodes(graph, coords)
        layer.allowed_nodes = set(path)
        geom = route_geometry(graph, path)
        if geom:
            layer.street_paths = [geom]
    else:
        layer.allowed_nodes = area_nodes(graph, coords)
    connected = {n for n in layer.allowed_nodes if any(m in layer.allowed_nodes for m in graph.adj.get(n, {}))}
    if not connected and layer.allowed_nodes:
        connected = set(layer.allowed_nodes)
        for n in list(layer.allowed_nodes):
            connected.update(graph.adj.get(n, {}))
    layer.allowed_nodes = connected


# -----------------------------------------------------------------------------
# Unified live build context and engine
# -----------------------------------------------------------------------------


class LiveBuildContext:
    def __init__(self, engine: "XYPIEngine"):
        self.engine = engine
        self.channels: list[GridChannel] = []

    def pois(self, category: str | None = None):
        if category is None:
            return {name: list(items) for name, items in self.engine.poi_data.items()}
        return list(self.engine.poi_data[normalize_poi_category(category)])

    def schools(self):
        return self.pois("schools")

    def hospitals(self):
        return self.pois("hospitals")

    def poi_pattern(self, category: str, max_points: int = 120) -> PointPattern:
        category = normalize_poi_category(category)
        return PointPattern(category, tuple(pois_to_points(self.pois(category), max_points)), category)

    def schools_pattern(self, name: str = "schools", max_points: int = 120) -> PointPattern:
        pattern = self.poi_pattern("schools", max_points)
        return PointPattern(name, pattern.points, "schools")

    def hospitals_pattern(self, name: str = "hospitals", max_points: int = 120) -> PointPattern:
        pattern = self.poi_pattern("hospitals", max_points)
        return PointPattern(name, pattern.points, "hospitals")

    def add_grid(self, name: str, spec: GridSpec) -> GridChannel:
        pattern = self.poi_pattern(spec.places, spec.max_points)
        time_flow = "x" if spec.direction == "horizontal" else "y"
        channel = GridChannel(name=name, pattern=pattern, time_flow=time_flow, movement=spec.movement, root_midi=spec.root_midi, pitch_range=spec.pitch_range, pitch_cells=spec.steps, n_steps=spec.steps, bpm=spec.bpm, beats_per_step=spec.beats_per_step, time_pattern=spec.time_pattern, output=spec.output, amp=spec.amp, sound=spec.sound)
        interpret_grid(channel)
        self.channels.append(channel)
        return channel

    def play(self, pattern: Any, *, name: str = "channel", time_flow: str = "x", x_axis: str | None = None, y_axis: str | None = None, root_midi: int = 48, pitch_range: int = 12, pitch_cells: int = 8, release_cells: int = 6, n_steps: int = 8, bpm: float = 150.0, beats_per_step: float = 1.0, time_pattern: list[int] | int = 1, output: str = "osc", amp: float = 0.45, movement: str = "linear", sound: str | None = None, **kwargs: Any) -> GridChannel:
        if "mode" in kwargs:
            raise TypeError("play() no longer accepts mode; choose the SuperCollider synth with sound=...")
        if kwargs:
            unknown = ", ".join(sorted(kwargs))
            raise TypeError(f"Unknown play() option(s): {unknown}")
        if time_flow == "moving_points":
            raise ValueError("time_flow='moving_points' was an experiment-only channel mode. Use moving_agent(...) for the final street-topology agent layer.")
        if time_flow not in ("x", "y"):
            raise ValueError("time_flow must be 'x' or 'y'")
        if output not in ("browser", "osc", "both"):
            raise ValueError("output must be 'osc' (legacy 'browser'/'both' are accepted and normalized to OSC)")
        if x_axis is not None or y_axis is not None:
            expected = ("time", "pitch") if time_flow == "x" else ("pitch", "time")
            if x_axis is not None and x_axis != expected[0]:
                raise ValueError(f"time_flow={time_flow!r} expects x_axis={expected[0]!r}")
            if y_axis is not None and y_axis != expected[1]:
                raise ValueError(f"time_flow={time_flow!r} expects y_axis={expected[1]!r}")
        if isinstance(pattern, PointPattern):
            point_pattern = pattern
        elif isinstance(pattern, list) and (not pattern or isinstance(pattern[0], tuple)):
            point_pattern = PointPattern(name, tuple((clamp01(x), clamp01(y)) for x, y in pattern))
        elif isinstance(pattern, list) and pattern and isinstance(pattern[0], dict):
            point_pattern = PointPattern(name, tuple(pois_to_points(pattern)))
        else:
            raise TypeError("play() expects a PointPattern, a list of (x, y) points, or POI dictionaries")
        movement_key = str(movement).strip().lower().replace("-", "").replace("_", "")
        movement_aliases = {"linear": "linear", "forward": "linear", "backforth": "backforth", "backandforth": "backforth", "pingpong": "backforth", "random": "random"}
        if movement_key not in movement_aliases:
            raise ValueError("movement must be 'linear', 'backforth', or 'random'")
        channel = GridChannel(name=name, pattern=point_pattern, time_flow=time_flow, movement=movement_aliases[movement_key], root_midi=int(root_midi), pitch_range=int(pitch_range), pitch_cells=int(pitch_cells), n_steps=int(n_steps), bpm=float(bpm), beats_per_step=float(beats_per_step), time_pattern=time_pattern, output="osc", amp=float(amp), sound=None if sound is None else str(sound))
        interpret_grid(channel)
        self.channels.append(channel)
        return channel

    def namespace(self) -> dict[str, Any]:
        ns = {
            "grid": grid, "play": self.play, "pois": self.pois, "poi": self.pois, "poi_pattern": self.poi_pattern,
            "schools": self.schools, "hospitals": self.hospitals,
            "schools_pattern": self.schools_pattern, "hospitals_pattern": self.hospitals_pattern,
            "pois_to_points": pois_to_points, "point_graph": point_graph,
            "moving_agent": moving_agent, "agent": agent,
        }
        ns.update(BEHAVIOURS)
        return ns


class XYPIEngine:
    def __init__(self, data_dir: Path, live_path: Path, location_id: str = DEFAULT_LOCATION, zoom: float | None = None, osc_host: str = "127.0.0.1", osc_port: int = 57120):
        self.data_dir, self.live_path = Path(data_dir), Path(live_path)
        self.cache_dir, self.runtime_dir = self.data_dir / "cache", self.data_dir / "runtime"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.map_json_path, self.state_json_path = self.runtime_dir / "map.json", self.runtime_dir / "state.json"
        self.location_id, self.zoom = location_id, zoom
        self.map_cfg = preset_map(location_id, zoom)
        self.view = MapView.from_bbox(self.map_cfg["bbox"])
        self.graph: StreetGraph | None = None
        self.poi_data: dict[str, list[dict[str, Any]]] = {name: [] for name in POI_FILTERS}
        self.channels: list[GridChannel] = []
        self.layers: list[AgentLayer] = []
        self.agents: list[StreetAgent] = []
        self.colours: dict[str, str] = {}
        self.sender = OscSender(osc_host, osc_port)
        self.grid_playback = GridOscPlayback(self.sender)
        self.status, self.error = "loading map", None
        self.live_status, self.live_error = "waiting", None
        self.lock = threading.RLock()
        self.running = True
        self._load_generation = 0
        self._live_stamp: tuple[int, int] | None = None
        self._last_failed_stamp: tuple[int, int] | None = None
        self._publish_all()

    def start(self) -> None:
        self._start_map_load()
        threading.Thread(target=self._simulation_loop, daemon=True, name="xypi-agents").start()

    def stop(self) -> None:
        self.running = False
        self.grid_playback.stop(clear_channels=True)

    def _start_map_load(self) -> None:
        self._load_generation += 1
        generation = self._load_generation
        threading.Thread(target=self._load_map, args=(generation,), daemon=True, name="xypi-map-load").start()

    def request_location(self, location_id: str, zoom: float | None = None) -> None:
        cfg = preset_map(location_id, zoom)
        with self.lock:
            self.location_id, self.zoom, self.map_cfg = location_id, zoom, cfg
            self.view = MapView.from_bbox(cfg["bbox"])
            self.graph = None
            self.poi_data = {name: [] for name in POI_FILTERS}
            self.channels, self.layers, self.agents = [], [], []
            self.status, self.error = "loading map", None
            self.live_status, self.live_error = "waiting", None
        self.grid_playback.stop(clear_channels=True)
        self._publish_all()
        self._start_map_load()

    def _load_map(self, generation: int) -> None:
        try:
            cfg = dict(self.map_cfg)
            view = MapView.from_bbox(cfg["bbox"])
            raw = load_street_raw(cfg, self.cache_dir)
            graph = graph_from_overpass(raw, view, float(cfg.get("corner_angle_deg", 25.0)))
            if not graph.edges:
                raise RuntimeError("Overpass returned no usable street edges")
            pois = load_pois(cfg, self.cache_dir)
            with self.lock:
                if generation != self._load_generation:
                    return
                self.graph, self.poi_data = graph, pois
                self.status, self.error = "map ready", None
            print(f"[map] {cfg['name']}: {len(graph.edges)} street segments; " + ", ".join(f"{k}={len(v)}" for k, v in pois.items()))
            self.reload_live(force=True)
        except Exception as exc:
            with self.lock:
                if generation != self._load_generation:
                    return
                self.status, self.error = "error", str(exc)
            print(f"[map] {exc}")
        self._publish_all()

    def _resolve_behaviour(self, value: object, namespace: dict[str, Any]) -> tuple[str | None, Callable[[AgentContext], int] | None]:
        if value is None:
            return None, None
        if callable(value):
            return getattr(value, "__name__", "<behaviour>"), value  # type: ignore[return-value]
        if isinstance(value, str):
            fn = namespace.get(value) or BEHAVIOURS.get(value)
            if callable(fn):
                return value, fn
        raise TypeError(f"Behaviour {value!r} is not callable")

    def _build_agents(self, defs: list[tuple[str, StreetAgentSpec]], namespace: dict[str, Any]) -> tuple[list[AgentLayer], list[StreetAgent]]:
        if self.graph is None:
            return [], []
        layers, agents = [], []
        for name, spec in defs:
            colour = self.colours.setdefault(name, random_colour())
            layer = AgentLayer(name, spec, colour)
            configure_layer(self.graph, layer)
            if not layer.allowed_nodes:
                raise RuntimeError(f"Agent {name!r} does not intersect a usable street route")
            anchor = polygon_centroid(list(spec.coords)) if spec.shape == "area" else spec.coords[0]
            start = self.graph.nearest_node(anchor, layer.allowed_nodes)
            x, y = self.graph.xy(start)
            behaviour_name, behaviour_fn = self._resolve_behaviour(spec.behaviour, namespace)
            layers.append(layer)
            agents.append(StreetAgent(name, layer, start, behaviour_name, behaviour_fn, x=x, y=y))
        return layers, agents

    def reload_live(self, force: bool = False, source: str | None = None) -> dict[str, Any]:
        if self.graph is None:
            return {"ok": False, "error": "Map and POIs are still loading"}
        if source is None:
            try:
                stat = self.live_path.stat()
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
            stamp = (stat.st_mtime_ns, stat.st_size)
            if not force and stamp in (self._live_stamp, self._last_failed_stamp):
                return {"ok": True, "unchanged": True}
            source = self.live_path.read_text(encoding="utf-8")
        else:
            stamp = None
        build = LiveBuildContext(self)
        namespace = build.namespace()
        try:
            exec(compile(source, str(self.live_path), "exec"), namespace)
            declarations = [(name, value) for name, value in namespace.items() if name.startswith("l") and name[1:].isdigit() and isinstance(value, (StreetAgentSpec, GridSpec))]
            declarations.sort(key=lambda item: int(item[0][1:]))
            agent_defs: list[tuple[str, StreetAgentSpec]] = []
            for name, value in declarations:
                if isinstance(value, GridSpec):
                    build.add_grid(name, value)
                else:
                    agent_defs.append((name, value))
            names = [c.name for c in build.channels]
            if len(names) != len(set(names)):
                raise ValueError("Grid channel names must be unique")
            layers, agents = self._build_agents(agent_defs, namespace)
            with self.lock:
                self.channels, self.layers, self.agents = build.channels, layers, agents
                self.live_status, self.live_error = "applied", None
            if stamp is not None:
                self._live_stamp, self._last_failed_stamp = stamp, None
            self.grid_playback.sync(self.channels)
            self._publish_all()
            return {"ok": True, "channels": self.channel_payloads(), "agents": [a.public_state() for a in agents]}
        except Exception:
            error = traceback.format_exc()
            with self.lock:
                self.live_status, self.live_error = "rejected", error
            if stamp is not None:
                self._last_failed_stamp = stamp
            self._publish_all()
            return {"ok": False, "error": error}

    def update_live_source(self, source: str) -> dict[str, Any]:
        if not source.strip():
            return {"ok": False, "error": "live.py is empty"}
        result = self.reload_live(force=True, source=source)
        if not result.get("ok"):
            return result
        tmp = self.live_path.with_suffix(".py.tmp")
        tmp.write_text(source, encoding="utf-8")
        os.replace(tmp, self.live_path)
        stat = self.live_path.stat()
        self._live_stamp = (stat.st_mtime_ns, stat.st_size)
        return result

    def _choose_edge(self, agent_obj: StreetAgent, now: float) -> None:
        assert self.graph is not None
        neighbours = tuple(n for n in self.graph.adj.get(agent_obj.node, {}) if n in agent_obj.layer.allowed_nodes)
        if not neighbours or agent_obj.behaviour_fn is None:
            return
        ctx = AgentContext(agent_obj.node, agent_obj.previous_node, neighbours, self.graph, agent_obj.layer.spec.shape, agent_obj.layer.spec.coords)
        result = agent_obj.behaviour_fn(ctx)
        speed_mult = 1.0
        if isinstance(result, tuple):
            target, speed_mult = result
        else:
            target = result
        if target not in neighbours:
            raise ValueError(f"{agent_obj.name} behaviour returned unavailable node {target}")
        edge = self.graph.adj[agent_obj.node][target]
        agent_obj.target_node, agent_obj.edge, agent_obj.edge_started = target, edge, now
        agent_obj.edge_duration = edge.length_m / max(0.05, agent_obj.layer.spec.speed_mps * max(0.05, float(speed_mult)))

    def _arrive(self, agent_obj: StreetAgent, now: float) -> None:
        assert self.graph is not None and agent_obj.target_node is not None
        agent_obj.previous_node, agent_obj.node = agent_obj.node, agent_obj.target_node
        agent_obj.target_node, agent_obj.edge = None, None
        duration = max(now - agent_obj.edge_started, 0.0)
        agent_obj.x, agent_obj.y = self.graph.xy(agent_obj.node)
        event = {"time": time.time(), "x": agent_obj.x, "y": agent_obj.y, "duration": duration}
        agent_obj.last_event = event
        if agent_obj.layer.spec.output == "osc":
            self.sender.send("/xypi/corner", agent_obj.name, agent_obj.layer.spec.sound, float(agent_obj.y), float(agent_obj.x), float(duration))

    def _simulation_loop(self) -> None:
        last_publish = 0.0
        while self.running:
            try:
                if self.graph is not None:
                    self.reload_live(force=False)
                    now = time.monotonic()
                    with self.lock:
                        agents, graph = list(self.agents), self.graph
                    if graph is not None:
                        for agent_obj in agents:
                            try:
                                if agent_obj.target_node is None:
                                    self._choose_edge(agent_obj, now)
                                if agent_obj.target_node is None or agent_obj.edge is None:
                                    continue
                                t = (now - agent_obj.edge_started) / max(agent_obj.edge_duration, 1e-9)
                                if t >= 1.0:
                                    self._arrive(agent_obj, now)
                                else:
                                    agent_obj.x, agent_obj.y = edge_position(graph, agent_obj.edge, agent_obj.node, agent_obj.target_node, t)
                            except Exception as exc:
                                print(f"[agent] {agent_obj.name}: {exc}")
                    if now - last_publish >= 0.5:
                        self._publish_state()
                        last_publish = now
            except Exception as exc:
                print(f"[engine] {exc}")
            time.sleep(1.0 / 30.0)

    def play_grids(self) -> dict[str, Any]:
        self.grid_playback.start()
        return {"ok": True, "playing": self.grid_playback.is_running}

    def stop_grids(self) -> dict[str, Any]:
        self.grid_playback.stop(clear_channels=False)
        return {"ok": True, "playing": False}

    def transport_state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "playing": self.grid_playback.is_running,
                "steps": {channel.name: channel.current_step for channel in self.channels},
                "agents": [agent_obj.public_state() for agent_obj in self.agents],
            }

    def pois_payload(self) -> dict[str, Any]:
        with self.lock:
            return {name: list(items) for name, items in self.poi_data.items()}

    def channel_payloads(self) -> list[dict[str, Any]]:
        with self.lock:
            return [channel.public_state() for channel in self.channels]

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": self.status, "error": self.error,
                "location": {"id": self.location_id, "name": self.map_cfg["name"], "zoom": self.map_cfg["zoom"], "bbox": self.map_cfg["bbox"], "street_segments": len(self.graph.edges) if self.graph else 0, "corner_nodes": len(self.graph.nodes) if self.graph else 0},
                "poi_counts": {name: len(items) for name, items in self.poi_data.items()},
                "channels": self.channel_payloads(),
                "layers": [layer.public_state() for layer in self.layers],
                "agents": [agent_obj.public_state() for agent_obj in self.agents],
                "live": {"status": self.live_status, "error": self.live_error},
                "transport": {"playing": self.grid_playback.is_running, "output": "osc"},
            }

    def map_state(self) -> dict[str, Any]:
        with self.lock:
            return {"ready": self.graph is not None, "location": {"id": self.location_id, "name": self.map_cfg["name"]}, "streets": self.graph.public_state() if self.graph else {"nodes": {}, "edges": []}, "pois": self.pois_payload()}

    def _publish_map(self) -> None:
        try:
            atomic_json(self.map_json_path, self.map_state())
        except Exception as exc:
            print(f"[runtime] map snapshot: {exc}")

    def _publish_state(self) -> None:
        try:
            atomic_json(self.state_json_path, self.state())
        except Exception as exc:
            print(f"[runtime] state snapshot: {exc}")

    def _publish_all(self) -> None:
        self._publish_map()
        self._publish_state()
