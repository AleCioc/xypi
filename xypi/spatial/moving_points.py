"""Graph-based moving_points time flow — multiple movers on one spatial pattern."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    Point,
)
from shapely.geometry.base import BaseGeometry

MovementMode = Literal["sync", "async"]


@dataclass
class MoverConfig:
    """One moving point with its own path on the shared graph."""

    name: str = "mover_0"
    movement: MovementMode = "sync"
    speed: float = 1.0
    path: list[int] | None = None
    start_node: int = 0
    loop: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "movement": self.movement,
            "speed": self.speed,
            "path": self.path,
            "start_node": self.start_node,
            "loop": self.loop,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MoverConfig:
        path_raw = data.get("path")
        return cls(
            name=str(data.get("name", "mover_0")),
            movement=data.get("movement", "sync"),
            speed=float(data.get("speed", 1.0)),
            path=[int(x) for x in path_raw] if path_raw is not None else None,
            start_node=int(data.get("start_node", 0)),
            loop=bool(data.get("loop", True)),
        )


@dataclass
class MovingPointsConfig:
    """Shared node graph plus one or more independent movers."""

    edges: list[tuple[int, int]] = field(default_factory=list)
    movers: list[MoverConfig] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [list(e) for e in self.edges],
            "movers": [m.to_dict() for m in self.movers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MovingPointsConfig:
        edges_raw = data.get("edges", [])
        edges = [tuple(int(x) for x in e) for e in edges_raw]
        movers_raw = data.get("movers")
        if movers_raw:
            movers = [MoverConfig.from_dict(m) for m in movers_raw]
        else:
            # Legacy single-mover payload (formerly MovingPointConfig)
            movers = [
                MoverConfig(
                    name="mover_0",
                    movement=data.get("movement", "sync"),
                    speed=float(data.get("speed", 1.0)),
                    path=[int(x) for x in data["path"]] if data.get("path") else None,
                    start_node=int(data.get("start_node", 0)),
                    loop=bool(data.get("loop", True)),
                )
            ]
        return cls(edges=edges, movers=movers)


# Backward-compatible alias
MovingPointConfig = MovingPointsConfig


@dataclass
class MoverPosition:
    step: int
    mover: str
    node_index: int
    x: float
    y: float
    edge: tuple[int, int] | None
    edge_t: float
    arrival: bool


def extract_nodes(geometry: BaseGeometry) -> list[tuple[float, float]]:
    if isinstance(geometry, MultiPoint):
        return [(float(p.x), float(p.y)) for p in geometry.geoms]
    if isinstance(geometry, Point):
        return [(float(geometry.x), float(geometry.y))]
    if isinstance(geometry, GeometryCollection):
        nodes: list[tuple[float, float]] = []
        for g in geometry.geoms:
            if isinstance(g, (Point, MultiPoint)):
                nodes.extend(extract_nodes(g))
        return nodes
    raise TypeError(
        f"moving_points geometry must be MultiPoint or GeometryCollection with points, got {geometry.geom_type!r}"
    )


def _nearest_node_index(nodes: list[tuple[float, float]], x: float, y: float) -> int:
    best = 0
    best_d = math.inf
    for i, (nx, ny) in enumerate(nodes):
        d = math.hypot(nx - x, ny - y)
        if d < best_d:
            best_d = d
            best = i
    return best


def edges_from_linestrings(geometry: BaseGeometry, nodes: list[tuple[float, float]]) -> list[tuple[int, int]]:
    lines: list[LineString] = []
    if isinstance(geometry, LineString):
        lines = [geometry]
    elif isinstance(geometry, MultiLineString):
        lines = list(geometry.geoms)
    elif isinstance(geometry, GeometryCollection):
        for g in geometry.geoms:
            if isinstance(g, LineString):
                lines.append(g)
            elif isinstance(g, MultiLineString):
                lines.extend(g.geoms)

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for line in lines:
        coords = list(line.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            i = _nearest_node_index(nodes, float(a[0]), float(a[1]))
            j = _nearest_node_index(nodes, float(b[0]), float(b[1]))
            if i == j:
                continue
            key = (min(i, j), max(i, j))
            if key not in seen:
                seen.add(key)
                edges.append(key)
    return edges


def normalize_edges(edges: list[tuple[int, int]]) -> set[tuple[int, int]]:
    return {(min(a, b), max(a, b)) for a, b in edges}


def validate_edge(edge_set: set[tuple[int, int]], a: int, b: int) -> None:
    if a == b:
        return
    key = (min(a, b), max(a, b))
    if key not in edge_set:
        raise ValueError(f"No edge between nodes {a} and {b} — movement blocked")


def build_path(mover: MoverConfig, edge_set: set[tuple[int, int]], n_nodes: int) -> list[int]:
    if n_nodes < 1:
        raise ValueError("moving_points requires at least one node")
    if mover.path is not None:
        if not mover.path:
            raise ValueError(f"mover {mover.name!r} path cannot be empty")
        for a, b in zip(mover.path[:-1], mover.path[1:]):
            validate_edge(edge_set, a, b)
        return list(mover.path)

    if not edge_set:
        return [mover.start_node]

    visited_edges: set[tuple[int, int]] = set()
    adj: dict[int, list[int]] = {i: [] for i in range(n_nodes)}
    for a, b in edge_set:
        adj[a].append(b)
        adj[b].append(a)

    path = [mover.start_node]
    current = mover.start_node
    while True:
        neighbors = sorted(adj[current])
        nxt = None
        for cand in neighbors:
            key = (min(current, cand), max(current, cand))
            if key not in visited_edges:
                nxt = cand
                visited_edges.add(key)
                break
        if nxt is None:
            break
        path.append(nxt)
        current = nxt
    return path


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _interpolate(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def compute_sync_positions(
    nodes: list[tuple[float, float]],
    path: list[int],
    *,
    mover: str,
    n_steps: int,
    loop: bool,
) -> list[MoverPosition]:
    if not path:
        return []
    positions: list[MoverPosition] = []
    for step in range(n_steps):
        idx = step % len(path) if loop else min(step, len(path) - 1)
        node = path[idx]
        edge: tuple[int, int] | None = None
        edge_t = 0.0
        if step > 0:
            prev_idx = (step - 1) % len(path) if loop else step - 1
            prev_node = path[prev_idx]
            if prev_node != node:
                edge = (prev_node, node)
                edge_t = 1.0
        positions.append(
            MoverPosition(
                step=step,
                mover=mover,
                node_index=node,
                x=nodes[node][0],
                y=nodes[node][1],
                edge=edge,
                edge_t=edge_t,
                arrival=True,
            )
        )
    return positions


def compute_async_positions(
    nodes: list[tuple[float, float]],
    path: list[int],
    *,
    mover: str,
    n_steps: int,
    beats_per_step: float,
    speed: float,
    loop: bool,
) -> list[MoverPosition]:
    if not path or speed <= 0:
        return compute_sync_positions(nodes, path, mover=mover, n_steps=n_steps, loop=loop)

    hop_nodes = path if len(path) >= 2 else [path[0]]
    segment_nodes = list(hop_nodes)
    if loop and len(hop_nodes) > 1 and hop_nodes[0] != hop_nodes[-1]:
        segment_nodes = hop_nodes + [hop_nodes[0]]

    arrivals = [0.0]
    for a, b in zip(segment_nodes[:-1], segment_nodes[1:]):
        arrivals.append(arrivals[-1] + _dist(nodes[a], nodes[b]) / speed)

    cycle_beats = arrivals[-1] if arrivals else 0.0
    if cycle_beats <= 0:
        return compute_sync_positions(nodes, path, mover=mover, n_steps=n_steps, loop=loop)

    positions: list[MoverPosition] = []
    for step in range(n_steps):
        t = step * beats_per_step
        cycle_t = t % cycle_beats if loop and cycle_beats > 0 else min(t, cycle_beats)

        seg_i = 0
        for i in range(len(arrivals) - 1):
            if arrivals[i] <= cycle_t <= arrivals[i + 1] + 1e-12:
                seg_i = i
                break
        else:
            seg_i = max(0, len(arrivals) - 2)

        a_node = segment_nodes[seg_i]
        b_node = segment_nodes[seg_i + 1]
        seg_len = max(arrivals[seg_i + 1] - arrivals[seg_i], 1e-12)
        edge_t = (cycle_t - arrivals[seg_i]) / seg_len
        px, py = _interpolate(nodes[a_node], nodes[b_node], edge_t)
        at_node = edge_t < 1e-6 or abs(cycle_t - arrivals[seg_i + 1]) < 1e-6
        prev_cycle_t = max(0.0, (step - 1) * beats_per_step)
        prev_cycle = prev_cycle_t % cycle_beats if loop and cycle_beats > 0 else min(prev_cycle_t, cycle_beats)
        arrival = any(
            prev_cycle < arr <= cycle_t + 1e-9 or abs(cycle_t - arr) < 1e-6 for arr in arrivals
        )
        positions.append(
            MoverPosition(
                step=step,
                mover=mover,
                node_index=segment_nodes[seg_i + 1] if at_node and seg_i + 1 < len(segment_nodes) else a_node,
                x=px,
                y=py,
                edge=(a_node, b_node),
                edge_t=edge_t,
                arrival=arrival,
            )
        )
    return positions


def resolve_graph(
    geometry: BaseGeometry,
    config: MovingPointsConfig,
) -> tuple[list[tuple[float, float]], list[tuple[int, int]]]:
    nodes = extract_nodes(geometry)
    edges = list(config.edges)
    if not edges:
        edges = edges_from_linestrings(geometry, nodes)
    return nodes, list(normalize_edges(edges))


def compute_mover_positions(
    nodes: list[tuple[float, float]],
    edge_set: set[tuple[int, int]],
    mover: MoverConfig,
    *,
    n_steps: int,
    beats_per_step: float,
) -> tuple[list[int], list[MoverPosition]]:
    path = build_path(mover, edge_set, len(nodes))
    if mover.movement == "async":
        positions = compute_async_positions(
            nodes,
            path,
            mover=mover.name,
            n_steps=n_steps,
            beats_per_step=beats_per_step,
            speed=mover.speed,
            loop=mover.loop,
        )
    else:
        positions = compute_sync_positions(
            nodes, path, mover=mover.name, n_steps=n_steps, loop=mover.loop
        )
    return path, positions


def default_movers() -> list[MoverConfig]:
    return [MoverConfig(name="mover_0")]
