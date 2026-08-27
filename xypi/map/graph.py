"""Street graph built from OSM highway data."""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon

from xypi.map.geo import haversine_m, turn_deg
from xypi.map.view import MapView


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
            raise RuntimeError("No street nodes are available for this layer")
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
        best: set[int] = set()
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

    def public_state(self) -> dict:
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


def graph_from_overpass(data: dict, view: MapView, corner_angle_deg: float = 25.0) -> StreetGraph:
    raw_nodes = {
        int(e["id"]): (float(e["lat"]), float(e["lon"]))
        for e in data.get("elements", [])
        if e.get("type") == "node"
    }
    ways = [e for e in data.get("elements", []) if e.get("type") == "way" and len(e.get("nodes", [])) >= 2]
    occurrences: dict[int, int] = {}
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
            segment = ids[i0 : i1 + 1]
            length = 0.0
            geom = [raw_nodes[n] for n in segment]
            for p0, p1 in zip(geom, geom[1:]):
                length += haversine_m(p0[0], p0[1], p1[0], p1[1])
            if length > 0:
                graph.add_edge(Edge(segment[0], segment[-1], length, geom))

    used = set(graph.adj)
    graph.nodes = {n: graph.nodes[n] for n in used}
    return graph


def route_path_nodes(
    graph: StreetGraph,
    points: list[tuple[float, float]],
    *,
    close: bool = False,
) -> list[int]:
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


def edge_position(graph: StreetGraph, edge: Edge, start: int, target: int, t: float) -> tuple[float, float]:
    from xypi.map.geo import clamp01

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
