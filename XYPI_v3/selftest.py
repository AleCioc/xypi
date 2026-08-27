from __future__ import annotations

import random
import tempfile
import time
from pathlib import Path

from core import AgentContext, Edge, GridChannel, GridOscPlayback, GridSpec, MapView, POI_FILTERS, PointPattern, StreetGraph, XYPIEngine, grid, interpret_grid, point_in_polygon, random_walk


def make_graph() -> StreetGraph:
    view = MapView(0.0, 0.0, 1.0, 1.0)
    graph_obj = StreetGraph(view)
    graph_obj.nodes = {1: (0.2, 0.2), 2: (0.2, 0.8), 3: (0.8, 0.8), 4: (0.8, 0.2)}
    for a, b in [(1, 2), (2, 3), (3, 4), (4, 1)]:
        p0, p1 = graph_obj.nodes[a], graph_obj.nodes[b]
        graph_obj.add_edge(Edge(a, b, 100.0, [p0, p1]))
    return graph_obj


def test_grid_quantization() -> None:
    pattern = PointPattern("test", ((0.05, 0.05), (0.49, 0.75), (0.99, 0.99)))
    channel = interpret_grid(GridChannel("g", pattern, time_flow="x", pitch_cells=4, n_steps=4))
    assert channel.cells == [(0, 0), (1, 3), (3, 3)]
    assert [event.step for event in channel.events] == [0, 1, 3]
    vertical = interpret_grid(GridChannel("v", pattern, time_flow="y", pitch_cells=4, n_steps=4))
    assert vertical.cells[0] == (0, 0)


def test_no_tree_category() -> None:
    assert "trees" not in POI_FILTERS
    assert "natural" not in {key for key, _ in POI_FILTERS.values()}


def test_grid_declaration() -> None:
    spec = grid("hospital", steps=12, bpm=133, direction="vertical", movement="backforth", max_points=40, output="browser")
    assert isinstance(spec, GridSpec)
    assert spec.places == "hospitals"
    assert spec.steps == 12
    assert spec.direction == "vertical" and spec.movement == "backforth"
    assert spec.output == "osc"



def test_rows_removed() -> None:
    try:
        grid("schools", steps=8, rows=4)
    except TypeError as exc:
        assert "steps defines both grid axes" in str(exc)
    else:
        raise AssertionError("grid(rows=...) should be rejected")

def test_movement() -> None:
    pattern = PointPattern("test", ((0.1, 0.1),))
    channel = GridChannel("g", pattern, n_steps=4, movement="backforth")
    state = {"step": 0, "direction": 1}
    sequence = [state["step"]]
    for _ in range(7):
        GridOscPlayback._advance(channel, state)
        sequence.append(state["step"])
    assert sequence == [0, 1, 2, 3, 2, 1, 0, 1]
    random.seed(3)
    channel.movement = "random"
    for _ in range(20):
        GridOscPlayback._advance(channel, state)
        assert 0 <= state["step"] < channel.n_steps



def test_unified_osc_message() -> None:
    class CaptureSender:
        def __init__(self):
            self.messages = []
        def send(self, path, *args):
            self.messages.append((path, args))

    sender = CaptureSender()
    pattern = PointPattern("test", ((0.1, 0.2),))
    channel = interpret_grid(GridChannel("l1", pattern, n_steps=1, pitch_cells=4, bpm=6000, sound="hh"))
    playback = GridOscPlayback(sender)
    playback.sync([channel])
    time.sleep(0.025)
    playback.stop()
    assert sender.messages
    path, args = sender.messages[0]
    assert path == "/xypi/corner"
    assert args[0] == "l1" and args[1] == "hh"
    assert len(args) == 5

def test_geometry() -> None:
    square = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    assert point_in_polygon((0.5, 0.5), square)
    assert not point_in_polygon((0.95, 0.5), square)
    graph_obj = make_graph()
    ctx = AgentContext(1, None, tuple(graph_obj.adj[1]), graph_obj, "area", tuple(square))
    assert random_walk(ctx) in graph_obj.adj[1]


def test_live_build() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        live = root / "live.py"
        live.write_text("# empty", encoding="utf-8")
        engine = XYPIEngine(root, live)
        engine.graph = make_graph()
        engine.status = "map ready"
        engine.poi_data["schools"] = [{"x": 0.1, "y": 0.2, "id": "n/1", "name": "A", "category": "schools"}, {"x": 0.7, "y": 0.8, "id": "n/2", "name": "B", "category": "schools"}]
        engine.poi_data["hospitals"] = [{"x": 0.4, "y": 0.5, "id": "n/3", "name": "H", "category": "hospitals"}]
        source = '''
l1 = grid("schools", steps=8, bpm=120, direction="horizontal", movement="linear", output="browser")
l2 = grid("hospitals", steps=6, bpm=90, direction="vertical", movement="backforth", output="both")
l3 = agent("area", [(0.1,0.1),(0.9,0.1),(0.9,0.9),(0.1,0.9)], speed=10, behaviour=random_walk, sound="bass")
'''
        result = engine.update_live_source(source)
        assert result["ok"], result.get("error")
        assert [c.name for c in engine.channels] == ["l1", "l2"]
        assert engine.channels[0].pattern.category == "schools"
        assert engine.channels[0].movement == "linear" and engine.channels[0].time_flow == "x"
        assert engine.channels[0].pitch_cells == engine.channels[0].n_steps == 8
        assert engine.channels[1].movement == "backforth" and engine.channels[1].time_flow == "y"
        assert engine.channels[1].pitch_cells == engine.channels[1].n_steps == 6
        assert all(c.output == "osc" for c in engine.channels)
        assert len(engine.agents) == 1 and engine.agents[0].name == "l3"
        assert engine.agents[0].layer.spec.sound == "bass"
        engine.stop()


if __name__ == "__main__":
    test_grid_quantization()
    test_no_tree_category()
    test_grid_declaration()
    test_rows_removed()
    test_movement()
    test_unified_osc_message()
    test_geometry()
    test_live_build()
    print("XYPI self-test: OK")
