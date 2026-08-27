"""Street-walking behaviour functions for map agents."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable

from xypi.map.graph import Edge, StreetGraph


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


BEHAVIOUR_REGISTRY: dict[str, Callable[[Context], int]] = {
    "random_walk": random_walk,
    "straightish": straightish,
    "backtrack": backtrack,
    "clockwiseish": clockwiseish,
    "anticlockwiseish": anticlockwiseish,
    "shortest_street": shortest_street,
    "longest_street": longest_street,
    "point_attract": point_attract,
}
