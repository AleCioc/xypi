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
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Callable

from shapely.geometry import LineString, Point, Polygon


ROOT = Path(__file__).resolve().parent


def write_json_atomic(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def turn_deg(a, b, c) -> float:
    ax, ay = a[1] - b[1], a[0] - b[0]
    cx, cy = c[1] - b[1], c[0] - b[0]
    na = max(math.hypot(ax, ay), 1e-12)
    nc = max(math.hypot(cx, cy), 1e-12)
    cosv = max(-1.0, min(1.0, (ax * cx + ay * cy) / (na * nc)))
    return abs(180.0 - math.degrees(math.acos(cosv)))


def random_colour() -> str:
    h = random.randint(0, 359)
    return f"hsl({h} 78% 58%)"


@dataclass(frozen=True)
class MapView:
    south: float
    west: float
    north: float
    east: float

    @classmethod
    def from_bbox(cls, bbox):
        return cls(*map(float, bbox))

    def normalize(self, lat: float, lon: float) -> tuple[float, float]:
        x = (lon - self.west) / max(self.east - self.west, 1e-12)
        y = (lat - self.south) / max(self.north - self.south, 1e-12)
        return clamp01(x), clamp01(y)

    def denormalize(self, x: float, y: float) -> tuple[float, float]:
        lon = self.west + clamp01(x) * (self.east - self.west)
        lat = self.south + clamp01(y) * (self.north - self.south)
        return lat, lon


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

    def add_edge(self, edge: Edge):
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
            raise RuntimeError("No street nodes are available for this layer")
        x, y = xy
        return min(nodes, key=lambda n: (self.xy(n)[0] - x) ** 2 + (self.xy(n)[1] - y) ** 2)

    def shortest_path(self, start: int, goal: int, allowed: set[int] | None = None) -> list[int]:
        if start == goal:
            return [start]
        allowed = allowed or set(self.nodes)
        dist = {start: 0.0}
        prev = {}
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
                    dist[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(queue, (nd, nxt))
        if goal not in dist:
            return []
        path = [goal]
        while path[-1] != start:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    def largest_component(self, nodes: set[int]) -> set[int]:
        remaining = set(nodes)
        best = set()
        while remaining:
            seed = remaining.pop()
            comp = {seed}
            stack = [seed]
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

    def public_state(self):
        return {
            "nodes": {str(n): self.xy(n) for n in self.nodes},
            "edges": [
                {
                    "a": e.a,
                    "b": e.b,
                    "length_m": e.length_m,
                    "geometry": [self.view.normalize(lat, lon) for lat, lon in e.geometry],
                }
                for e in self.edges.values()
            ],
        }


def download_overpass(map_cfg: dict) -> dict:
    view = MapView.from_bbox(map_cfg["bbox"])
    cache_dir = ROOT / map_cfg.get("cache_dir", "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha1(json.dumps([round(v, 8) for v in map_cfg["bbox"]]).encode("utf-8")).hexdigest()[:12]
    cache = cache_dir / f"streets_{cache_key}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    query = f'''[out:json][timeout:30];
    way["highway"]["highway"!~"motorway|motorway_link|trunk|trunk_link|raceway|construction|proposed"]({view.south},{view.west},{view.north},{view.east});
    (._;>;);
    out body;'''
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(map_cfg.get("overpass_url", "https://overpass-api.de/api/interpreter"), data=body, headers={"User-Agent": "XYPI-map-agent/0.4"})

    def read_json(context=None):
        with urllib.request.urlopen(req, timeout=45, context=context) as response:
            return json.loads(response.read().decode("utf-8"))

    def ssl_verify_failed(exc: Exception) -> bool:
        reason = getattr(exc, "reason", None)
        return (
            isinstance(exc, ssl.SSLCertVerificationError)
            or isinstance(reason, ssl.SSLCertVerificationError)
            or "CERTIFICATE_VERIFY_FAILED" in str(exc)
        )

    try:
        data = read_json()
    except Exception as exc:
        if not ssl_verify_failed(exc):
            raise

        # Some macOS/Python installations do not have a usable CA bundle.
        # First retry with certifi when available.
        certifi = None
        try:
            import certifi as certifi_module
            certifi = certifi_module
        except ImportError:
            pass

        if certifi is not None:
            print("[map] system CA verification failed; retrying with certifi")
            try:
                data = read_json(ssl.create_default_context(cafile=certifi.where()))
            except Exception as cert_exc:
                if not ssl_verify_failed(cert_exc):
                    raise
                exc = cert_exc
            else:
                cache.write_text(json.dumps(data))
                return data

        if not map_cfg.get("allow_insecure_ssl_fallback", True):
            raise RuntimeError(
                "HTTPS certificate verification failed. Install/update the Python CA certificates, "
                "install certifi, or enable MAP['allow_insecure_ssl_fallback'] for this local prototype."
            ) from exc

        print("[map] WARNING: certificate verification failed; using insecure SSL fallback for Overpass")
        data = read_json(ssl._create_unverified_context())

    cache.write_text(json.dumps(data))
    return data


def graph_from_overpass(data: dict, view: MapView, corner_angle_deg: float = 25.0) -> StreetGraph:
    raw_nodes = {int(e["id"]): (float(e["lat"]), float(e["lon"])) for e in data.get("elements", []) if e.get("type") == "node"}
    ways = [e for e in data.get("elements", []) if e.get("type") == "way" and len(e.get("nodes", [])) >= 2]
    occurrences = {}
    for way in ways:
        for n in set(map(int, way["nodes"])):
            occurrences[n] = occurrences.get(n, 0) + 1

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
                continue
            a, b, c = raw_nodes[ids[i - 1]], raw_nodes[node], raw_nodes[ids[i + 1]]
            if turn_deg(a, b, c) >= corner_angle_deg:
                important.add(i)

        idxs = sorted(important)
        for i0, i1 in zip(idxs, idxs[1:]):
            segment = ids[i0:i1 + 1]
            length = 0.0
            geom = [raw_nodes[n] for n in segment]
            for p0, p1 in zip(geom, geom[1:]):
                length += haversine_m(p0[0], p0[1], p1[0], p1[1])
            if length > 0:
                graph.add_edge(Edge(segment[0], segment[-1], length, geom))

    used = set(graph.adj)
    graph.nodes = {n: graph.nodes[n] for n in used}
    return graph


@dataclass
class Layer:
    name: str
    shape: str
    coords: list[tuple[float, float]]
    colour: str = field(default_factory=random_colour)
    allowed_nodes: set[int] = field(default_factory=set)
    street_paths: list[list[tuple[float, float]]] = field(default_factory=list)

    def shape_geometry(self):
        if self.shape == "points":
            return [Point(x, y) for x, y in self.coords]
        if self.shape == "line":
            return LineString(self.coords)
        if self.shape == "area":
            return Polygon(self.coords)
        raise ValueError(f"Unknown layer shape {self.shape!r}; use points, line, or area")

    def public_state(self):
        return {
            "name": self.name,
            "shape": self.shape,
            "coords": self.coords,
            "colour": self.colour,
            "street_paths": self.street_paths,
        }


def route_path_nodes(graph: StreetGraph, points: list[tuple[float, float]], *, close: bool = False) -> list[int]:
    anchors = [graph.nearest_node(p) for p in points]
    if len(anchors) == 1:
        return [anchors[0]]
    pairs = list(zip(anchors, anchors[1:]))
    if close and len(anchors) > 2:
        pairs.append((anchors[-1], anchors[0]))
    ordered: list[int] = []
    for start, goal in pairs:
        part = graph.shortest_path(start, goal)
        if not part:
            continue
        if ordered and ordered[-1] == part[0]:
            ordered.extend(part[1:])
        else:
            ordered.extend(part)
    return ordered or [anchors[0]]


def route_geometry(graph: StreetGraph, path: list[int]) -> list[tuple[float, float]]:
    if len(path) < 2:
        return [graph.xy(path[0])] if path else []
    out: list[tuple[float, float]] = []
    for start, target in zip(path, path[1:]):
        edge = graph.adj[start][target]
        geom = edge.geometry if edge.a == start and edge.b == target else list(reversed(edge.geometry))
        xy = [graph.view.normalize(lat, lon) for lat, lon in geom]
        if out and xy and out[-1] == xy[0]:
            out.extend(xy[1:])
        else:
            out.extend(xy)
    return out


def area_nodes(graph: StreetGraph, coords: list[tuple[float, float]]) -> set[int]:
    poly = Polygon(coords)
    selected = {n for n in graph.nodes if poly.buffer(1e-9).contains(Point(*graph.xy(n)))}
    selected = graph.largest_component(selected)
    if selected:
        return selected
    c = poly.centroid
    return {graph.nearest_node((c.x, c.y))}


def configure_layer_graph(graph: StreetGraph, layer: Layer):
    layer.street_paths = []
    if layer.shape == "points":
        # Point layers are a constellation / force field, not a route. The agent
        # may use the connected street network and point-aware behaviours decide
        # how the visible dots attract, repel, or bend its motion.
        layer.allowed_nodes = graph.largest_component(set(graph.nodes))
    elif layer.shape == "line":
        path = route_path_nodes(graph, layer.coords, close=False)
        layer.allowed_nodes = set(path)
        geom = route_geometry(graph, path)
        if geom:
            layer.street_paths = [geom]
    elif layer.shape == "area":
        layer.allowed_nodes = area_nodes(graph, layer.coords)
    else:
        raise ValueError(f"Unknown layer shape: {layer.shape}")

    connected = {n for n in layer.allowed_nodes if any(m in layer.allowed_nodes for m in graph.adj.get(n, {}))}
    if not connected and layer.allowed_nodes:
        expanded = set(layer.allowed_nodes)
        for n in list(layer.allowed_nodes):
            expanded.update(graph.adj.get(n, {}))
        connected = expanded
    layer.allowed_nodes = connected

def edge_position(graph: StreetGraph, edge: Edge, start: int, target: int, t: float) -> tuple[float, float]:
    """Interpolate along the full OSM street polyline, not a straight node-to-node chord."""
    geom = edge.geometry if edge.a == start and edge.b == target else list(reversed(edge.geometry))
    if len(geom) < 2:
        return graph.xy(target)
    lengths = [0.0]
    for p0, p1 in zip(geom, geom[1:]):
        lengths.append(lengths[-1] + haversine_m(p0[0], p0[1], p1[0], p1[1]))
    total = max(lengths[-1], 1e-9)
    wanted = clamp01(t) * total
    for i in range(1, len(lengths)):
        if wanted <= lengths[i]:
            span = max(lengths[i] - lengths[i - 1], 1e-9)
            u = (wanted - lengths[i - 1]) / span
            lat = geom[i - 1][0] + (geom[i][0] - geom[i - 1][0]) * u
            lon = geom[i - 1][1] + (geom[i][1] - geom[i - 1][1]) * u
            return graph.view.normalize(lat, lon)
    return graph.xy(target)


@dataclass
class Context:
    current_node: int
    previous_node: int | None
    neighbours: tuple[int, ...]
    graph: StreetGraph
    layer_shape: str
    layer_coords: tuple[tuple[float, float], ...]

    def node_xy(self, node: int) -> tuple[float, float]:
        return self.graph.xy(node)

    @property
    def current_xy(self) -> tuple[float, float]:
        return self.graph.xy(self.current_node)

    @property
    def points(self) -> tuple[tuple[float, float], ...]:
        return self.layer_coords if self.layer_shape == "points" else ()

    def edge_length(self, node: int) -> float:
        return self.graph.adj[self.current_node][node].length_m


def choices(ctx: Context) -> list[int]:
    """Available streets, avoiding immediate backtracking when possible."""
    return [n for n in ctx.neighbours if n != ctx.previous_node] or list(ctx.neighbours)


def _direction_score(ctx: Context, node: int, vx: float, vy: float) -> float:
    cx, cy = ctx.current_xy
    nx, ny = ctx.node_xy(node)
    dx, dy = nx - cx, ny - cy
    a = max(math.hypot(dx, dy), 1e-9)
    b = max(math.hypot(vx, vy), 1e-9)
    return (dx * vx + dy * vy) / (a * b)


def random_walk(ctx: Context) -> int:
    return random.choice(choices(ctx))


def straightish(ctx: Context) -> int:
    opts = choices(ctx)
    if ctx.previous_node is None or len(opts) == 1:
        return random.choice(opts)
    px, py = ctx.node_xy(ctx.previous_node)
    cx, cy = ctx.current_xy
    return max(opts, key=lambda node: _direction_score(ctx, node, cx - px, cy - py))


def backtrack(ctx: Context) -> int:
    if ctx.previous_node in ctx.neighbours:
        return ctx.previous_node
    return random.choice(list(ctx.neighbours))


def clockwiseish(ctx: Context) -> int:
    opts = choices(ctx)
    if ctx.previous_node is None:
        return random.choice(opts)
    px, py = ctx.node_xy(ctx.previous_node)
    cx, cy = ctx.current_xy
    ix, iy = cx - px, cy - py
    def cross(node):
        nx, ny = ctx.node_xy(node)
        return ix * (ny - cy) - iy * (nx - cx)
    return min(opts, key=cross)


def anticlockwiseish(ctx: Context) -> int:
    opts = choices(ctx)
    if ctx.previous_node is None:
        return random.choice(opts)
    px, py = ctx.node_xy(ctx.previous_node)
    cx, cy = ctx.current_xy
    ix, iy = cx - px, cy - py
    def cross(node):
        nx, ny = ctx.node_xy(node)
        return ix * (ny - cy) - iy * (nx - cx)
    return max(opts, key=cross)


def shortest_street(ctx: Context) -> int:
    return min(choices(ctx), key=ctx.edge_length)


def longest_street(ctx: Context) -> int:
    return max(choices(ctx), key=ctx.edge_length)


def point_attract(ctx: Context) -> int:
    """For point layers: the constellation acts as one attraction field over the street graph."""
    opts = choices(ctx)
    if not ctx.points:
        return random.choice(opts)
    cx, cy = ctx.current_xy
    vx = vy = 0.0
    for px, py in ctx.points:
        dx, dy = px - cx, py - cy
        d2 = max(dx * dx + dy * dy, 0.0025)
        weight = 1.0 / d2
        vx += dx * weight
        vy += dy * weight
    if abs(vx) + abs(vy) < 1e-9:
        return random.choice(opts)
    return max(opts, key=lambda node: _direction_score(ctx, node, vx, vy) + random.uniform(-0.06, 0.06))


@dataclass(frozen=True)
class AgentSpec:
    shape: str
    coords: tuple[tuple[float, float], ...]
    speed_mps: float
    behaviour: object
    sound: str


_DEFAULT_BEHAVIOUR = object()


def agent(shape, coords, *, speed: float = 1.4, behaviour=_DEFAULT_BEHAVIOUR, sound: str = "sine") -> AgentSpec:
    """Declare one spatial layer and its automatically bound moving agent."""
    shape = str(shape).strip().lower()
    if shape not in {"points", "line", "area"}:
        raise ValueError("agent shape must be 'points', 'line', or 'area'")
    pts = tuple(tuple(map(float, p)) for p in coords)
    minimum = {"points": 1, "line": 2, "area": 3}[shape]
    if len(pts) < minimum:
        raise ValueError(f"{shape} needs at least {minimum} coordinate(s)")
    if any(len(p) != 2 or p[0] < 0 or p[0] > 1 or p[1] < 0 or p[1] > 1 for p in pts):
        raise ValueError("all coordinates must be normalized (x, y) pairs between 0 and 1")
    speed = float(speed)
    if speed <= 0:
        raise ValueError("speed must be > 0")
    sound = str(sound).strip()
    if not sound:
        raise ValueError("sound must be a non-empty string")
    if behaviour is _DEFAULT_BEHAVIOUR:
        behaviour = {"points": point_attract, "line": straightish, "area": random_walk}[shape]
    if behaviour is not None and not callable(behaviour) and not isinstance(behaviour, str):
        raise TypeError("behaviour must be a function, function name, or None")
    return AgentSpec(shape=shape, coords=pts, speed_mps=speed, behaviour=behaviour, sound=sound)


LIVE_API = {
    "agent": agent,
    "choices": choices,
    "random_walk": random_walk,
    "straightish": straightish,
    "backtrack": backtrack,
    "clockwiseish": clockwiseish,
    "anticlockwiseish": anticlockwiseish,
    "shortest_street": shortest_street,
    "longest_street": longest_street,
    "point_attract": point_attract,
}


def load_live_module(path: Path, module_name: str, source: str | None = None) -> ModuleType:
    source = path.read_text(encoding="utf-8") if source is None else source
    module = ModuleType(module_name)
    module.__file__ = str(path)
    module.__dict__.update(LIVE_API)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


class LiveProgram:
    """Atomically hot-reload the single performance script, live.py."""

    def __init__(self, path: Path):
        self.path = path
        self.stamp = None
        self.failed_stamp = None
        self.module: ModuleType | None = None
        self.generation = 0
        self.reload(force=True)

    @staticmethod
    def _unit_defs(module: ModuleType) -> list[tuple[str, AgentSpec]]:
        units = []
        for name, value in module.__dict__.items():
            if name.startswith("l") and name[1:].isdigit() and isinstance(value, AgentSpec):
                units.append((name, value))
        units.sort(key=lambda item: int(item[0][1:]))
        return units

    def reload(self, force=False) -> bool:
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
            if not force and (stamp == self.stamp or stamp == self.failed_stamp):
                return False
            module = load_live_module(self.path, "xypi_live_program")
            self._unit_defs(module)
            self.module = module
            self.stamp = stamp
            self.failed_stamp = None
            self.generation += 1
            print("[live] live.py reloaded")
            return True
        except Exception as exc:
            try:
                self.failed_stamp = (self.path.stat().st_mtime_ns, self.path.stat().st_size)
            except OSError:
                pass
            print(f"[live] live.py reload failed: {exc}")
            return False

    @classmethod
    def validate_source(cls, source: str, filename: str = "live.py") -> ModuleType:
        fake_path = Path(filename)
        module = load_live_module(fake_path, "xypi_live_candidate", source=source)
        cls._unit_defs(module)
        return module

    def source(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def unit_defs(self) -> list[tuple[str, AgentSpec]]:
        return self._unit_defs(self.module) if self.module else []

    def resolve_behaviour(self, spec) -> tuple[str | None, Callable | None]:
        if spec is None:
            return None, None
        if callable(spec):
            return getattr(spec, "__name__", "<behaviour>"), spec
        if isinstance(spec, str):
            fn = getattr(self.module, spec, None) if self.module else None
            if not callable(fn):
                fn = LIVE_API.get(spec)
            if not callable(fn):
                raise RuntimeError(f"Behaviour {spec!r} is not callable in live.py")
            return spec, fn
        raise TypeError("behaviour must be a function, a function name, or None")


class OscSender:
    def __init__(self, host: str, port: int, path: str):
        self.addr = (host, int(port))
        self.path = path
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    @staticmethod
    def _osc_string(value: str) -> bytes:
        raw = value.encode("utf-8") + b"\0"
        return raw + b"\0" * ((4 - len(raw) % 4) % 4)

    def send_corner(self, layer: str, sound: str, y_pitch: float, x_timbre: float, duration: float):
        packet = self._osc_string(self.path)
        packet += self._osc_string(",ssfff")
        packet += self._osc_string(layer)
        packet += self._osc_string(sound)
        packet += struct.pack(">fff", float(y_pitch), float(x_timbre), float(duration))
        self.sock.sendto(packet, self.addr)


@dataclass
class Agent:
    name: str
    layer: Layer
    node: int
    speed_mps: float = 1.4
    previous_node: int | None = None
    target_node: int | None = None
    edge: Edge | None = None
    street_started: float = 0.0
    edge_last_update: float = 0.0
    edge_progress_m: float = 0.0
    edge_duration: float = 0.0
    x: float = 0.0
    y: float = 0.0
    last_event: dict | None = None
    behaviour: str | None = None
    behaviour_fn: Callable | None = field(default=None, repr=False)
    sound: str = "sine"
    status: str = "waiting for agent configuration"

    def public_state(self):
        return {
            "name": self.name,
            "layer": self.layer.name,
            "x": self.x,
            "y": self.y,
            "node": self.node,
            "target_node": self.target_node,
            "speed_mps": self.speed_mps,
            "behaviour": self.behaviour,
            "sound": self.sound,
            "status": self.status,
            "edge_duration": self.edge_duration,
            "last_event": self.last_event,
        }


def _layer_from_spec(name: str, spec: AgentSpec, colour: str) -> Layer:
    return Layer(name=name, shape=spec.shape, coords=list(spec.coords), colour=colour)


def _layer_signature(layer: Layer):
    return layer.shape, tuple(layer.coords)


class AgentMapEngine:
    def __init__(self, config_module, live_path: Path):
        self.config = config_module
        self.view = MapView.from_bbox(config_module.MAP["bbox"])
        osc = config_module.OSC
        self.osc = OscSender(osc["host"], osc["port"], osc.get("path", "/xypi/corner"))
        self.live = LiveProgram(live_path)
        self.graph: StreetGraph | None = None
        self.layers: list[Layer] = []
        self.agents: list[Agent] = []
        self.colours: dict[str, str] = {}
        self.status = "loading streets"
        self.error = None
        self.live_status = "ready"
        self.live_error = None
        self.lock = threading.RLock()
        self.running = True
        self.runtime_dir = ROOT / "runtime"
        self.map_json_path = self.runtime_dir / "map.json"
        self.state_json_path = self.runtime_dir / "state.json"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._publish_map()
        self._publish_state()

    def start(self):
        threading.Thread(target=self._load_map, daemon=True).start()
        threading.Thread(target=self._simulation_loop, daemon=True).start()

    def _load_map(self):
        try:
            raw = download_overpass(self.config.MAP)
            graph = graph_from_overpass(raw, self.view, float(self.config.MAP.get("corner_angle_deg", 25.0)))
            if not graph.edges:
                raise RuntimeError("Overpass returned no usable street edges for this bounding box")
            with self.lock:
                self.graph = graph
                self.status = "map ready"
                self.error = None
            print(f"[map] loaded {len(graph.nodes)} corner nodes, {len(graph.edges)} street segments")
            self._publish_map()
            self._sync_live_program(force=True)
            self._publish_state()
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.status = "error"
            print(f"[map] {exc}")
            self._publish_map()
            self._publish_state()

    def _sync_live_program(self, force=False):
        changed = self.live.reload() if not force else True
        if not changed and not force:
            return
        with self.lock:
            graph = self.graph
            if graph is None:
                return
            old_layers = {layer.name: layer for layer in self.layers}
            old_agents = {agent.layer.name: agent for agent in self.agents}

        try:
            defs = self.live.unit_defs()
            names = [name for name, _ in defs]
            new_layers = []
            new_agents = []
            for name, spec in defs:
                colour = self.colours.setdefault(name, random_colour())
                candidate = _layer_from_spec(name, spec, colour)
                old = old_layers.get(name)
                if old is not None and _layer_signature(old) == _layer_signature(candidate):
                    layer = old
                    agent_obj = old_agents[name]
                else:
                    layer = candidate
                    configure_layer_graph(graph, layer)
                    if not layer.allowed_nodes:
                        raise RuntimeError(f"{name!r} does not intersect a usable street route")
                    geom = layer.shape_geometry()
                    anchor = (geom.centroid.x, geom.centroid.y) if layer.shape == "area" else layer.coords[0]
                    start = graph.nearest_node(anchor, layer.allowed_nodes)
                    x, y = graph.xy(start)
                    agent_obj = Agent(name=name, layer=layer, node=start, x=x, y=y)
                    action = "added" if old is None else "updated"
                    allowed_edges = sum(1 for n in layer.allowed_nodes for m in graph.adj.get(n, {}) if m in layer.allowed_nodes) // 2
                    print(f"[live] {action} {name}; shape={layer.shape}, {len(layer.allowed_nodes)} street nodes, {allowed_edges} usable segments")

                speed = spec.speed_mps
                behaviour_name, behaviour_fn = self.live.resolve_behaviour(spec.behaviour)
                sound = spec.sound
                old_speed = agent_obj.speed_mps
                old_behaviour = agent_obj.behaviour
                old_sound = agent_obj.sound
                agent_obj.speed_mps = speed
                agent_obj.behaviour = behaviour_name
                agent_obj.behaviour_fn = behaviour_fn
                agent_obj.sound = sound
                if force or old is None or abs(speed - old_speed) > 1e-12 or behaviour_name != old_behaviour or sound != old_sound:
                    print(f"[agent] {name}: speed={speed:.2f} m/s, behaviour={behaviour_name or 'none'}, sound={sound}")

                new_layers.append(layer)
                new_agents.append(agent_obj)

            removed = set(old_layers) - set(names)
            for name in sorted(removed):
                print(f"[live] removed {name}")

            with self.lock:
                self.layers = new_layers
                self.agents = new_agents
                self.error = None
                self.live_status = "applied"
                self.live_error = None
        except Exception as exc:
            with self.lock:
                self.live_status = "rejected"
                self.live_error = str(exc)
            print(f"[live] program update rejected: {exc}")

    def _set_agent_status(self, agent: Agent, status: str):
        if agent.status != status:
            agent.status = status
            print(f"[agent] {agent.name}: {status}")

    def _choose_edge(self, agent: Agent, now: float):
        assert self.graph is not None
        neighbours = tuple(n for n in self.graph.adj.get(agent.node, {}) if n in agent.layer.allowed_nodes)
        if not neighbours:
            self._set_agent_status(agent, "blocked: no connected street segment inside shape")
            return
        if agent.behaviour is None:
            self._set_agent_status(agent, "waiting for behaviour")
            return
        ctx = Context(agent.node, agent.previous_node, neighbours, self.graph, agent.layer.shape, tuple(agent.layer.coords))
        try:
            behaviour = agent.behaviour_fn
            if behaviour is None:
                self._set_agent_status(agent, "waiting for behaviour")
                return
            target = behaviour(ctx)
            if target not in neighbours:
                raise ValueError(f"behaviour returned unavailable node {target}")
        except Exception as exc:
            self._set_agent_status(agent, f"behaviour error: {exc}")
            return

        edge = self.graph.adj[agent.node][target]
        agent.target_node = target
        agent.edge = edge
        agent.street_started = now
        agent.edge_last_update = now
        agent.edge_progress_m = 0.0
        agent.edge_duration = edge.length_m / max(agent.speed_mps, 0.05)
        self._set_agent_status(agent, f"moving with {agent.behaviour}: {edge.length_m:.1f} m at {agent.speed_mps:.2f} m/s ({agent.edge_duration:.2f} s)")

    def _arrive(self, agent: Agent, now: float):
        assert self.graph is not None and agent.target_node is not None
        old = agent.node
        agent.previous_node = old
        agent.node = agent.target_node
        agent.target_node = None
        agent.edge = None
        actual_duration = max(now - agent.street_started, 0.0)
        agent.edge_progress_m = 0.0
        agent.edge_last_update = now
        x, y = self.graph.xy(agent.node)
        agent.x, agent.y = x, y
        event = {"time": time.time(), "sound": agent.sound, "x_timbre": x, "y_pitch": y, "duration": actual_duration}
        agent.last_event = event
        agent.status = f"arrived at corner; previous street {actual_duration:.2f} s"
        self.osc.send_corner(agent.name, agent.sound, y, x, actual_duration)
        print(f"[corner] {agent.name:12s} sound={agent.sound:8s} pitch(y)={y:.3f} timbre(x)={x:.3f} duration={actual_duration:.3f}s")

    def _simulation_loop(self):
        last_publish = 0.0
        while self.running:
            self._sync_live_program()
            now = time.monotonic()
            with self.lock:
                graph = self.graph
                agents = list(self.agents)
            if graph is not None:
                for agent in agents:
                    if agent.target_node is None:
                        self._choose_edge(agent, now)
                    if agent.target_node is None or agent.edge is None:
                        continue
                    dt = max(0.0, now - agent.edge_last_update)
                    agent.edge_last_update = now
                    agent.edge_progress_m += agent.speed_mps * dt
                    t = agent.edge_progress_m / max(agent.edge.length_m, 1e-9)
                    if t >= 1.0:
                        self._arrive(agent, now)
                    else:
                        agent.edge_duration = (agent.edge.length_m - agent.edge_progress_m) / max(agent.speed_mps, 0.05)
                        agent.x, agent.y = edge_position(graph, agent.edge, agent.node, agent.target_node, t)
            if now - last_publish >= 0.1:
                self._publish_state()
                last_publish = now
            time.sleep(1 / 30)

    def update_live_source(self, source: str) -> tuple[bool, str]:
        if len(source.encode("utf-8")) > 256_000:
            return False, "live.py is too large for the browser editor"
        try:
            self.live.validate_source(source, str(self.live.path))
            tmp = self.live.path.with_suffix(".py.browser.tmp")
            tmp.write_text(source, encoding="utf-8")
            os.replace(tmp, self.live.path)
            with self.lock:
                self.live_status = "saved"
                self.live_error = None
            return True, "saved; engine will hot-reload it"
        except Exception as exc:
            with self.lock:
                self.live_status = "editor error"
                self.live_error = str(exc)
            return False, str(exc)

    def _publish_map(self):
        try:
            write_json_atomic(self.map_json_path, self.map_state())
        except Exception as exc:
            print(f"[viewer] failed to write map snapshot: {exc}")

    def _publish_state(self):
        try:
            write_json_atomic(self.state_json_path, self.state())
        except Exception as exc:
            print(f"[viewer] failed to write state snapshot: {exc}")

    def state(self):
        with self.lock:
            graph = self.graph
            return {
                "status": self.status,
                "error": self.error,
                "map": {
                    "name": self.config.MAP.get("name", "map"),
                    "bbox": self.config.MAP["bbox"],
                    "center": self.config.MAP.get("center"),
                    "zoom": self.config.MAP.get("zoom"),
                    "street_segments": len(graph.edges) if graph else 0,
                    "corner_nodes": len(graph.nodes) if graph else 0,
                },
                "layers": [layer.public_state() for layer in self.layers],
                "agents": [agent.public_state() for agent in self.agents],
                "live": {"status": self.live_status, "error": self.live_error},
                "osc": self.config.OSC,
            }

    def map_state(self):
        with self.lock:
            if self.graph is None:
                return {"ready": False, "streets": {"nodes": {}, "edges": []}}
            return {"ready": True, "streets": self.graph.public_state()}


class ViewerHandler(SimpleHTTPRequestHandler):
    engine: AgentMapEngine | None = None

    def _send_json(self, status: int, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/live":
            if self.engine is None:
                self.send_error(503, "engine unavailable")
                return
            raw = self.engine.live.source().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/live":
            self.send_error(404)
            return
        if self.engine is None:
            self._send_json(503, {"ok": False, "error": "engine unavailable"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"ok": False, "error": "invalid Content-Length"})
            return
        if length <= 0 or length > 256_000:
            self._send_json(413, {"ok": False, "error": "live source must be between 1 byte and 256 KB"})
            return
        source = self.rfile.read(length).decode("utf-8")
        ok, message = self.engine.update_live_source(source)
        self._send_json(200 if ok else 400, {"ok": ok, "message": message, "error": None if ok else message})

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        request = str(args[0] if args else "")
        if "runtime/state.json" not in request and "runtime/map.json" not in request:
            super().log_message(fmt, *args)


def serve(engine: AgentMapEngine, port: int = 8001, index_name: str = "index_v13.html"):
    os.chdir(ROOT)
    ViewerHandler.engine = engine
    server = ThreadingHTTPServer(("127.0.0.1", port), ViewerHandler)
    url = f"http://127.0.0.1:{port}/{index_name}"
    print(f"[viewer] {url}")
    print(f"[viewer] map snapshot: http://127.0.0.1:{port}/runtime/map.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        engine.running = False
        server.server_close()
