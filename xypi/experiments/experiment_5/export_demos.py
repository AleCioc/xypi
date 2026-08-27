#!/usr/bin/env python3
"""Export static GeoJSON demos for experiment_5 (optional)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.channels.config import ChannelConfig, SoundParams, TimeConfig
from xypi.channels.interpreter import count_hits, interpret_channel
from xypi.spatial.geojson import export_channel_geojson
from xypi.spatial.moving_points import MoverConfig, MovingPointsConfig
from xypi.spatial.patterns import point_graph
from xypi.spatial.space_config import SpaceConfig

OUTPUT_DIR = Path(__file__).parent / "output"
BPM = 150
N_STEPS = 8

TRIANGLE_NODES = [(2, 2), (8, 2), (5, 7)]
TRIANGLE_EDGES = [(0, 1), (1, 2), (2, 0)]
ISLAND_NODES = [(1, 1), (3, 3), (10, 1), (12, 4)]
ISLAND_EDGES = [(0, 1), (2, 3)]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    triangle = point_graph(TRIANGLE_NODES, TRIANGLE_EDGES, name="triangle").geometry
    islands = point_graph(ISLAND_NODES, ISLAND_EDGES, name="islands").geometry

    configs = [
        (
            ChannelConfig(
                name="tri_sync",
                spatial_pattern_id="triangle",
                x_axis=AxisRole.PITCH,
                y_axis=AxisRole.RELEASE,
                sound=SoundParams(mode="synth", root_midi=48, pitch_range=12),
                time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.MOVING_POINTS),
                space=SpaceConfig(
                    moving_points=MovingPointsConfig(
                        edges=TRIANGLE_EDGES,
                        movers=[MoverConfig(name="walker", path=[0, 1, 2, 0])],
                    ),
                ),
            ),
            triangle,
        ),
        (
            ChannelConfig(
                name="tri_async",
                spatial_pattern_id="triangle",
                x_axis=AxisRole.PITCH,
                y_axis=AxisRole.RELEASE,
                sound=SoundParams(mode="synth", root_midi=60, pitch_range=12),
                time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.MOVING_POINTS, beats_per_step=0.5),
                space=SpaceConfig(
                    moving_points=MovingPointsConfig(
                        edges=TRIANGLE_EDGES,
                        movers=[
                            MoverConfig(name="glide", movement="async", speed=2.0, path=[0, 1, 2, 0])
                        ],
                    ),
                ),
            ),
            triangle,
        ),
        (
            ChannelConfig(
                name="dual_islands",
                spatial_pattern_id="islands",
                x_axis=AxisRole.PITCH,
                y_axis=AxisRole.RELEASE,
                sound=SoundParams(mode="sample", root_midi=0, pitch_range=4),
                time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.MOVING_POINTS),
                space=SpaceConfig(
                    moving_points=MovingPointsConfig(
                        edges=ISLAND_EDGES,
                        movers=[
                            MoverConfig(name="alpha", path=[0, 1, 0, 1, 0, 1, 0, 1]),
                            MoverConfig(name="beta", path=[2, 3, 2, 3, 2, 3, 2, 3]),
                        ],
                    ),
                ),
            ),
            islands,
        ),
    ]

    for config, geometry in configs:
        channel = interpret_channel(config, geometry)
        export_channel_geojson(OUTPUT_DIR / f"{config.name}.geojson", channel, bpm=BPM)
        n_movers = len(config.space.moving_points.movers) if config.space.moving_points else 0
        print(f"{config.name}: {count_hits(channel)}/{N_STEPS} hits · {n_movers} mover(s)")


if __name__ == "__main__":
    main()
