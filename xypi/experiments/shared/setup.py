from __future__ import annotations

from dataclasses import dataclass

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.channels.config import ChannelConfig, Composition, SoundParams, TimeConfig
from xypi.spatial.patterns import polygon
from xypi.spatial.space_config import SpaceConfig

BPM = 150
N_STEPS = 8

# Complementary pitch grids (coprime-ish) for shifting melodies / phasing patterns.
GRID_X_TIME = (5, 9)   # poly_a synth, poly_c sample — horizontal time maps
GRID_Y_TIME = (7, 11)  # poly_b synth, poly_d sample — vertical time maps

POLYGONS: dict[str, list[tuple[float, float]]] = {
    "poly_a": [(1, 1), (7, 1), (8, 5), (4, 7), (1, 5)],
    "poly_b": [(10, 1), (16, 2), (15, 7), (11, 8), (9, 4)],
    "poly_c": [(1, 9), (6, 10), (7, 14), (3, 16), (0, 13)],
    "poly_d": [(10, 10), (16, 9), (17, 14), (13, 16), (9, 13)],
}


def build_composition() -> Composition:
    composition = Composition(bpm=BPM)
    for name, coords in POLYGONS.items():
        p = polygon(coords, name=name)
        composition.add_pattern(p.name, p.geometry)

    channels = [
        ChannelConfig(
            name="poly_a_synth",
            spatial_pattern_id="poly_a",
            x_axis=AxisRole.TIME,
            y_axis=AxisRole.PITCH,
            sound=SoundParams(mode="synth", root_midi=36, pitch_range=12),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM),
            space=SpaceConfig(mode="points-0", pitch_cells=GRID_X_TIME[0]),
        ),
        ChannelConfig(
            name="poly_b_synth",
            spatial_pattern_id="poly_b",
            x_axis=AxisRole.PITCH,
            y_axis=AxisRole.TIME,
            sound=SoundParams(mode="synth", root_midi=60, pitch_range=12),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.Y),
            space=SpaceConfig(mode="points-0", pitch_cells=GRID_Y_TIME[0]),
        ),
        ChannelConfig(
            name="poly_c_sample",
            spatial_pattern_id="poly_c",
            x_axis=AxisRole.TIME,
            y_axis=AxisRole.PITCH,
            sound=SoundParams(mode="sample", root_midi=0, pitch_range=4),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM),
            space=SpaceConfig(mode="points-0", pitch_cells=GRID_X_TIME[1]),
        ),
        ChannelConfig(
            name="poly_d_sample",
            spatial_pattern_id="poly_d",
            x_axis=AxisRole.PITCH,
            y_axis=AxisRole.TIME,
            sound=SoundParams(mode="sample", root_midi=0, pitch_range=4),
            time=TimeConfig(n_steps=N_STEPS, bpm=BPM, flow=TimeFlow.Y),
            space=SpaceConfig(mode="points-0", pitch_cells=GRID_Y_TIME[1]),
        ),
    ]
    for ch in channels:
        composition.add_channel(ch)
    return composition


def channel_summary(config: ChannelConfig, *, hits: int, source_points: int, grid: tuple[int, int]) -> str:
    return (
        f"{config.name}: {hits}/{N_STEPS} hits · {source_points} pts · "
        f"grid {grid[0]}×{grid[1]} · time={config.time_flow.value} · "
        f"x={config.x_axis.value} y={config.y_axis.value}"
    )
