#!/usr/bin/env python3
"""Experiment 3 — mixed geometry types + radial time.

Patterns: MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, radial cloud.
Radial channel: x=note, y=octave, time expands center→perimeter each loop.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.channels.config import ChannelConfig, Composition, SoundParams, TimeConfig
from xypi.channels.interpreter import interpret_channel
from xypi.experiments.shared.setup import BPM, N_STEPS, channel_summary
from xypi.spatial.geojson import export_channel_geojson
from xypi.spatial.patterns import (
    line_string,
    multi_line_string,
    multi_polygon,
    multipoint,
    polygon,
)
from xypi.spatial.space_config import SpaceConfig

OUTPUT_DIR = Path(__file__).parent / "output"


def _radial_cloud_points(cx: float, cy: float, *, rings: int = 4, pts_per_ring: int = 6):
    coords = [(cx, cy)]
    for r in range(1, rings + 1):
        radius = r * 1.8
        for i in range(pts_per_ring):
            angle = 2 * math.pi * i / pts_per_ring
            coords.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return coords


def build_composition() -> Composition:
    composition = Composition(bpm=BPM)
    for p in [
        multipoint([(2, 2), (4, 3), (6, 2), (5, 5), (3, 6)], name="pts_scatter"),
        line_string([(1, 1), (3, 4), (5, 3), (7, 6), (9, 5)], name="line_melody"),
        multi_line_string(
            [[(10, 1), (12, 3), (14, 2)], [(11, 5), (13, 7), (15, 6)]],
            name="lines_dual",
        ),
        polygon([(1, 10), (4, 11), (5, 14), (2, 15)], name="poly_tri"),
        multi_polygon(
            [[(10, 10), (13, 10), (13, 13), (10, 13)], [(14, 11), (17, 11), (16, 14)]],
            name="polys_pair",
        ),
        multipoint(_radial_cloud_points(8.0, 8.0), name="radial_cloud"),
    ]:
        composition.add_pattern(p.name, p.geometry)

    channels = [
        ChannelConfig(
            name="pts_x_time",
            spatial_pattern_id="pts_scatter",
            x_axis=AxisRole.TIME,
            y_axis=AxisRole.PITCH,
            sound=SoundParams(mode="synth", root_midi=48, pitch_range=12),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.X),
            space=SpaceConfig(pitch_cells=6),
        ),
        ChannelConfig(
            name="line_y_time",
            spatial_pattern_id="line_melody",
            x_axis=AxisRole.PITCH,
            y_axis=AxisRole.TIME,
            sound=SoundParams(mode="synth", root_midi=60, pitch_range=12),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.Y),
            space=SpaceConfig(pitch_cells=7),
        ),
        ChannelConfig(
            name="mlines_x_time",
            spatial_pattern_id="lines_dual",
            x_axis=AxisRole.TIME,
            y_axis=AxisRole.PITCH,
            sound=SoundParams(mode="sample", root_midi=0, pitch_range=4),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.X),
            space=SpaceConfig(pitch_cells=5),
        ),
        ChannelConfig(
            name="mpoly_y_time",
            spatial_pattern_id="polys_pair",
            x_axis=AxisRole.PITCH,
            y_axis=AxisRole.TIME,
            sound=SoundParams(mode="sample", root_midi=0, pitch_range=4),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.Y),
            space=SpaceConfig(pitch_cells=8),
        ),
        ChannelConfig(
            name="radial_note_octave",
            spatial_pattern_id="radial_cloud",
            x_axis=AxisRole.PITCH,
            y_axis=AxisRole.OCTAVE,
            sound=SoundParams(mode="synth", root_midi=36, note_semitones=12),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.RADIAL),
            space=SpaceConfig(pitch_cells=12, octave_cells=4, center_x=8.0, center_y=8.0),
        ),
    ]
    for ch in channels:
        composition.add_channel(ch)
    return composition


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    composition = build_composition()
    for config in composition.channels.values():
        geometry = composition.patterns[config.spatial_pattern_id]
        channel = interpret_channel(config, geometry)
        export_channel_geojson(OUTPUT_DIR / f"{config.name}.geojson", channel, bpm=BPM)
        hits = sum(1 for e in channel.events if e.hit)
        print(
            channel_summary(
                config,
                hits=hits,
                source_points=len(channel.source_points),
                grid=(channel.grid_time, channel.grid_pitch),
            )
        )
    print(f"\nOpen viewer: cd {Path(__file__).parent} && python -m http.server 8001")
    print("Then visit http://localhost:8001/index.html")


if __name__ == "__main__":
    main()
