from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.channels.config import ChannelConfig
from xypi.spatial.moving_points import compute_mover_positions, resolve_graph
from xypi.spatial.points import extract_points
from xypi.spatial.space_config import grid_bounds, grid_layout_dict, grid_shape


@dataclass
class CellHit:
    x: float
    y: float
    grid_col: int
    grid_row: int
    midi: int
    value: float
    hit: bool
    release: float = 0.5
    mover: str = ""


@dataclass
class StepEvent:
    step: int
    time_beats: float
    time_sec: float
    x: float
    y: float
    midi: int
    value: float
    hit: bool
    inside: bool
    grid_col: int = -1
    grid_row: int = -1
    activations: list[CellHit] = field(default_factory=list)


@dataclass
class Channel:
    config: ChannelConfig
    geometry: BaseGeometry
    events: list[StepEvent] = field(default_factory=list)
    source_points: list[tuple[float, float]] = field(default_factory=list)
    grid_time: int = 0
    grid_pitch: int = 0
    grid_layout: dict[str, Any] = field(default_factory=dict)
    radial_center: tuple[float, float] | None = None
    max_radius: float = 0.0
    moving_points: dict[str, Any] | None = None


def _cell_index(coord: float, min_val: float, max_val: float, n_cells: int) -> int:
    span = max(max_val - min_val, 1e-9)
    t = (coord - min_val) / span
    idx = int(t * n_cells)
    return max(0, min(n_cells - 1, idx))


def _radial_center(
    bounds: tuple[float, float, float, float],
    config: ChannelConfig,
) -> tuple[float, float]:
    minx, miny, maxx, maxy = bounds
    cx = config.space.center_x
    cy = config.space.center_y
    if cx is None or cy is None:
        return (minx + maxx) / 2, (miny + maxy) / 2
    return float(cx), float(cy)


def _max_radius(bounds: tuple[float, float, float, float], cx: float, cy: float) -> float:
    minx, miny, maxx, maxy = bounds
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    return max(math.hypot(x - cx, y - cy) for x, y in corners)


def _point_cell_axis(
    px: float,
    py: float,
    bounds: tuple[float, float, float, float],
    config: ChannelConfig,
    *,
    time_cells: int,
    pitch_cells: int,
) -> tuple[int, int, float, int, int]:
    minx, miny, maxx, maxy = bounds
    flow = config.time_flow

    if flow == TimeFlow.X:
        time_idx = _cell_index(px, minx, maxx, time_cells)
        pitch_idx = _cell_index(py, miny, maxy, pitch_cells)
        pitch_coord = py
        col, row = time_idx, pitch_idx
    else:
        time_idx = _cell_index(py, miny, maxy, time_cells)
        pitch_idx = _cell_index(px, minx, maxx, pitch_cells)
        pitch_coord = px
        col, row = pitch_idx, time_idx

    return time_idx, pitch_idx, pitch_coord, col, row


def _point_cell_radial(
    px: float,
    py: float,
    bounds: tuple[float, float, float, float],
    config: ChannelConfig,
    *,
    cx: float,
    cy: float,
    max_r: float,
    time_cells: int,
) -> tuple[int, int, float, int, int]:
    minx, miny, maxx, maxy = bounds
    dist = math.hypot(px - cx, py - cy)
    if max_r <= 0:
        time_idx = 0
    else:
        time_idx = min(time_cells - 1, int(dist / max_r * time_cells))

    note_idx = _cell_index(px, minx, maxx, config.space.pitch_cells)
    octave_idx = _cell_index(py, miny, maxy, config.space.octave_cells)
    return time_idx, 0, 0.0, note_idx, octave_idx


def _event_value(
    px: float,
    py: float,
    pitch_coord: float,
    config: ChannelConfig,
    bounds: tuple[float, float, float, float],
) -> float:
    minx, miny, maxx, maxy = bounds
    sound = config.sound
    flow = config.time_flow

    if flow == TimeFlow.RADIAL:
        return sound.midi_from_note_octave(
            px,
            py,
            minx=minx,
            maxx=maxx,
            miny=miny,
            maxy=maxy,
            note_cells=config.space.pitch_cells,
            octave_cells=config.space.octave_cells,
        )

    if config.x_axis in (AxisRole.PITCH, AxisRole.OCTAVE):
        return sound.value_from_coord(pitch_coord, min_coord=minx, max_coord=maxx)
    return sound.value_from_coord(pitch_coord, min_coord=miny, max_coord=maxy)


def _interpret_points_0(config: ChannelConfig, geometry: BaseGeometry) -> Channel:
    bounds = geometry.bounds
    pattern = config.time.pattern()
    n_steps = config.time.n_steps
    pitch_cells = config.space.pitch_cells
    flow = config.time_flow
    time_cells, _ = grid_shape(
        time_flow=flow,
        n_steps=n_steps,
        pitch_cells=pitch_cells,
        octave_cells=config.space.octave_cells,
    )

    source_points = extract_points(geometry)
    activations: defaultdict[int, list[tuple[float, float, float, int, int]]] = defaultdict(list)

    cx, cy = _radial_center(bounds, config)
    max_r = _max_radius(bounds, cx, cy)

    for px, py in source_points:
        if flow == TimeFlow.RADIAL:
            time_idx, _, _, col, row = _point_cell_radial(
                px, py, bounds, config, cx=cx, cy=cy, max_r=max_r, time_cells=time_cells
            )
            pitch_coord = 0.0
        else:
            time_idx, _, pitch_coord, col, row = _point_cell_axis(
                px, py, bounds, config, time_cells=time_cells, pitch_cells=pitch_cells
            )
        activations[time_idx].append((px, py, pitch_coord, col, row))

    events: list[StepEvent] = []
    for step in range(n_steps):
        candidates = activations.get(step, [])
        time_beats = step * config.time.beats_per_step
        time_sec = time_beats * config.time.beat_sec()
        step_on = bool(pattern[step])

        cell_hits: list[CellHit] = []
        for px, py, pitch_coord, col, row in candidates:
            value = _event_value(px, py, pitch_coord, config, bounds) if step_on else 0.0
            midi = int(value) if config.sound.mode == "synth" else 0
            cell_hits.append(
                CellHit(
                    x=px,
                    y=py,
                    grid_col=col,
                    grid_row=row,
                    midi=midi,
                    value=value,
                    hit=step_on and value > 0,
                )
            )

        inside = bool(candidates)
        hit = any(c.hit for c in cell_hits)
        if cell_hits:
            primary = cell_hits[0]
            px, py = primary.x, primary.y
            col, row = primary.grid_col, primary.grid_row
            value, midi = primary.value, primary.midi
        else:
            px, py, col, row = 0.0, 0.0, -1, -1
            value, midi = 0.0, 0

        events.append(
            StepEvent(
                step=step,
                time_beats=time_beats,
                time_sec=time_sec,
                x=px,
                y=py,
                midi=midi,
                value=value,
                hit=hit,
                inside=inside,
                grid_col=col,
                grid_row=row,
                activations=cell_hits,
            )
        )

    layout = grid_layout_dict(
        time_flow=flow,
        x_axis=config.x_axis,
        y_axis=config.y_axis,
        time_cells=time_cells,
        pitch_cells=pitch_cells,
    )

    return Channel(
        config=config,
        geometry=geometry,
        events=events,
        source_points=source_points,
        grid_time=time_cells,
        grid_pitch=pitch_cells,
        grid_layout=layout,
        radial_center=(cx, cy) if flow == TimeFlow.RADIAL else None,
        max_radius=max_r if flow == TimeFlow.RADIAL else 0.0,
    )


def _moving_point_values(
    px: float,
    py: float,
    config: ChannelConfig,
    bounds: tuple[float, float, float, float],
) -> tuple[float, int, float]:
    minx, miny, maxx, maxy = bounds
    sound = config.sound
    if sound.mode == "synth":
        midi, release = sound.synth_pitch_release(px, py, minx=minx, maxx=maxx, miny=miny, maxy=maxy)
        return float(midi), int(midi), release
    slot, level = sound.sample_slot_level(px, py, minx=minx, maxx=maxx, miny=miny, maxy=maxy)
    return float(slot), 0, level


def _interpret_moving_points(config: ChannelConfig, geometry: BaseGeometry) -> Channel:
    mp_cfg = config.space.moving_points
    if mp_cfg is None:
        raise ValueError("moving_points flow requires space.moving_points")

    bounds = geometry.bounds
    minx, miny, maxx, maxy = bounds
    pitch_cells = config.space.pitch_cells
    release_cells = config.space.release_cells
    gminx, gminy, gmaxx, gmaxy = grid_bounds(minx, miny, maxx, maxy, pitch_cells, release_cells)
    grid_bounds_tuple = (gminx, gminy, gmaxx, gmaxy)
    n_steps = config.time.n_steps
    pattern = config.time.pattern()

    nodes, edges = resolve_graph(geometry, mp_cfg)
    edge_set = {(min(a, b), max(a, b)) for a, b in edges}
    movers = mp_cfg.movers or []

    mover_paths: dict[str, list[int]] = {}
    mover_positions: dict[str, list] = {}
    for mover in movers:
        path, positions = compute_mover_positions(
            nodes,
            edge_set,
            mover,
            n_steps=n_steps,
            beats_per_step=config.time.beats_per_step,
        )
        mover_paths[mover.name] = path
        mover_positions[mover.name] = positions

    events: list[StepEvent] = []
    for step in range(n_steps):
        step_on = bool(pattern[step])
        cell_hits: list[CellHit] = []
        for mover in movers:
            pos = mover_positions[mover.name][step]
            px, py = pos.x, pos.y
            col = _cell_index(px, gminx, gmaxx, pitch_cells)
            row = _cell_index(py, gminy, gmaxy, release_cells)
            value, midi, release = _moving_point_values(px, py, config, grid_bounds_tuple)
            should_hit = step_on and (mover.movement == "sync" or pos.arrival or pos.edge is None)
            cell_hits.append(
                CellHit(
                    x=px,
                    y=py,
                    grid_col=col,
                    grid_row=row,
                    midi=midi,
                    value=value,
                    hit=should_hit and value > 0,
                    release=release,
                    mover=mover.name,
                )
            )

        primary = next((c for c in cell_hits if c.hit), cell_hits[0] if cell_hits else None)
        time_beats = step * config.time.beats_per_step
        time_sec = time_beats * config.time.beat_sec()
        if primary:
            events.append(
                StepEvent(
                    step=step,
                    time_beats=time_beats,
                    time_sec=time_sec,
                    x=primary.x,
                    y=primary.y,
                    midi=primary.midi,
                    value=primary.value,
                    hit=any(c.hit for c in cell_hits),
                    inside=bool(cell_hits),
                    grid_col=primary.grid_col,
                    grid_row=primary.grid_row,
                    activations=cell_hits,
                )
            )
        else:
            events.append(
                StepEvent(
                    step=step,
                    time_beats=time_beats,
                    time_sec=time_sec,
                    x=0.0,
                    y=0.0,
                    midi=0,
                    value=0.0,
                    hit=False,
                    inside=False,
                    grid_col=-1,
                    grid_row=-1,
                    activations=[],
                )
            )

    mp_meta = {
        "nodes": [{"index": i, "x": x, "y": y} for i, (x, y) in enumerate(nodes)],
        "edges": [list(e) for e in edges],
        "movers": [
            {
                "name": m.name,
                "movement": m.movement,
                "speed": m.speed,
                "path": mover_paths.get(m.name, []),
                "positions": [
                    {
                        "step": p.step,
                        "x": p.x,
                        "y": p.y,
                        "node_index": p.node_index,
                        "edge": list(p.edge) if p.edge else None,
                        "edge_t": p.edge_t,
                        "arrival": p.arrival,
                    }
                    for p in mover_positions.get(m.name, [])
                ],
            }
            for m in movers
        ],
    }

    layout = grid_layout_dict(
        time_flow=TimeFlow.MOVING_POINTS,
        x_axis=config.x_axis,
        y_axis=config.y_axis,
        time_cells=n_steps,
        pitch_cells=pitch_cells,
    )
    layout["release_cells"] = release_cells
    layout["grid_bounds"] = {
        "minx": gminx,
        "miny": gminy,
        "maxx": gmaxx,
        "maxy": gmaxy,
    }

    return Channel(
        config=config,
        geometry=geometry,
        events=events,
        source_points=nodes,
        grid_time=n_steps,
        grid_pitch=pitch_cells,
        grid_layout=layout,
        moving_points=mp_meta,
    )


def count_hits(channel: Channel) -> int:
    total = 0
    for event in channel.events:
        if event.activations:
            total += sum(1 for activation in event.activations if activation.hit)
        elif event.hit:
            total += 1
    return total


def interpret_channel(config: ChannelConfig, geometry: BaseGeometry) -> Channel:
    if config.time_flow == TimeFlow.MOVING_POINTS:
        return _interpret_moving_points(config, geometry)
    if config.space.mode == "points-0":
        return _interpret_points_0(config, geometry)
    raise ValueError(f"Unknown space mode: {config.space.mode!r}")
