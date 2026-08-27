"""Spatial layer binding to street graph."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon

from xypi.agents.spec import StreetAgentSpec
from xypi.map.graph import StreetGraph, area_nodes, route_geometry, route_path_nodes


def random_colour() -> str:
    h = random.randint(0, 359)
    return f"hsl({h} 78% 58%)"


@dataclass
class Layer:
    name: str
    shape: str
    coords: list[tuple[float, float]]
    colour: str = field(default_factory=random_colour)
    allowed_nodes: set[int] = field(default_factory=set)
    street_paths: list[list[tuple[float, float]]] = field(default_factory=list)
    sound: str = "sine"
    output: str = "osc"

    def shape_geometry(self):
        if self.shape == "points":
            return [Point(x, y) for x, y in self.coords]
        if self.shape == "line":
            return LineString(self.coords)
        if self.shape == "area":
            return Polygon(self.coords)
        raise ValueError(f"Unknown layer shape {self.shape!r}")

    def public_state(self) -> dict:
        return {
            "name": self.name,
            "shape": self.shape,
            "coords": self.coords,
            "colour": self.colour,
            "street_paths": self.street_paths,
            "sound": self.sound,
            "output": self.output,
        }


def configure_layer_graph(graph: StreetGraph, layer: Layer) -> None:
    layer.street_paths = []
    if layer.shape == "points":
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


def layer_from_spec(name: str, spec: StreetAgentSpec, colour: str) -> Layer:
    return Layer(
        name=name,
        shape=spec.shape,
        coords=list(spec.coords),
        colour=colour,
        sound=spec.sound,
        output=spec.output,
    )


def layer_signature(layer: Layer) -> tuple:
    return layer.shape, tuple(layer.coords), layer.sound, layer.output
