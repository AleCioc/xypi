from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.spatial.moving_points import MoverConfig, MovingPointsConfig

SpaceMode = Literal["points-0"]
SPACE_MODES = frozenset({"points-0"})


@dataclass
class SpaceConfig:
    """Rules for drawing activation points from a spatial pattern."""

    mode: SpaceMode = "points-0"
    pitch_cells: int = 8
    octave_cells: int = 4
    release_cells: int = 6
    center_x: float | None = None
    center_y: float | None = None
    moving_points: MovingPointsConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "pitch_cells": self.pitch_cells,
            "octave_cells": self.octave_cells,
            "release_cells": self.release_cells,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }
        if self.moving_points is not None:
            payload["moving_points"] = self.moving_points.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpaceConfig:
        mp_raw = data.get("moving_points") or data.get("moving_point")
        moving_points = MovingPointsConfig.from_dict(mp_raw) if mp_raw else None
        return cls(
            mode=data.get("mode", "points-0"),
            pitch_cells=int(data.get("pitch_cells", 8)),
            octave_cells=int(data.get("octave_cells", 4)),
            release_cells=int(data.get("release_cells", 6)),
            center_x=data.get("center_x"),
            center_y=data.get("center_y"),
            moving_points=moving_points,
        )


def resolve_time_flow(
    *,
    x_axis: AxisRole,
    y_axis: AxisRole,
    flow: TimeFlow | None = None,
) -> TimeFlow:
    if flow is not None:
        return flow
    if x_axis == AxisRole.TIME:
        return TimeFlow.X
    if y_axis == AxisRole.TIME:
        return TimeFlow.Y
    return TimeFlow.RADIAL


def grid_bounds(
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
    pitch_cells: int,
    release_cells: int,
) -> tuple[float, float, float, float]:
    """Pad geometry bounds by half a cell so nodes on the bbox land inside cells."""
    span_x = max(maxx - minx, 1e-9)
    span_y = max(maxy - miny, 1e-9)
    pad_x = span_x / (2 * max(pitch_cells, 1))
    pad_y = span_y / (2 * max(release_cells, 1))
    return minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y


def grid_shape(
    *,
    time_flow: TimeFlow,
    n_steps: int,
    pitch_cells: int,
    octave_cells: int = 4,
) -> tuple[int, int]:
    """Return (time_cells, pitch_cells) for axis time; (n_steps, pitch*octave) hints for radial."""
    if time_flow == TimeFlow.RADIAL:
        return n_steps, pitch_cells
    if time_flow == TimeFlow.MOVING_POINTS:
        return n_steps, pitch_cells
    return n_steps, pitch_cells


def grid_layout_dict(
    *,
    time_flow: TimeFlow,
    x_axis: AxisRole,
    y_axis: AxisRole,
    time_cells: int,
    pitch_cells: int,
) -> dict[str, Any]:
    if time_flow == TimeFlow.X:
        return {
            "time_flow": "x",
            "time_cells": time_cells,
            "pitch_cells": pitch_cells,
            "time_axis": "x",
            "pitch_axis": "y" if y_axis in (AxisRole.PITCH, AxisRole.OCTAVE) else "y",
        }
    if time_flow == TimeFlow.Y:
        return {
            "time_flow": "y",
            "time_cells": time_cells,
            "pitch_cells": pitch_cells,
            "time_axis": "y",
            "pitch_axis": "x" if x_axis in (AxisRole.PITCH, AxisRole.OCTAVE) else "x",
        }
    if time_flow == TimeFlow.RADIAL:
        return {
            "time_flow": "radial",
            "time_cells": time_cells,
            "pitch_cells": pitch_cells,
            "time_axis": "radial",
            "pitch_axis_x": x_axis.value,
            "pitch_axis_y": y_axis.value,
        }
    if time_flow == TimeFlow.MOVING_POINTS:
        return {
            "time_flow": "moving_points",
            "time_cells": time_cells,
            "pitch_cells": pitch_cells,
            "time_axis": "moving_points",
            "pitch_axis": "x",
            "release_axis": "y",
        }
    raise ValueError(f"Unknown time flow: {time_flow!r}")


def validate_space_config(
    space: SpaceConfig,
    *,
    x_axis: AxisRole,
    y_axis: AxisRole,
    time_flow: TimeFlow,
) -> None:
    if space.pitch_cells < 1:
        raise ValueError("pitch_cells must be >= 1")

    if time_flow == TimeFlow.RADIAL:
        if AxisRole.TIME in (x_axis, y_axis):
            raise ValueError("radial time: x and y must be pitch/octave, not time")
        if x_axis not in (AxisRole.PITCH, AxisRole.OCTAVE) or y_axis not in (
            AxisRole.PITCH,
            AxisRole.OCTAVE,
        ):
            raise ValueError("radial time requires pitch/octave on both x and y")
        return

    if time_flow == TimeFlow.MOVING_POINTS:
        if x_axis != AxisRole.PITCH or y_axis != AxisRole.RELEASE:
            raise ValueError("moving_points requires x_axis=pitch and y_axis=release")
        if space.moving_points is None:
            raise ValueError("moving_points flow requires space.moving_points configuration")
        if not space.moving_points.movers:
            raise ValueError("moving_points requires at least one mover")
        for mover in space.moving_points.movers:
            if mover.speed <= 0 and mover.movement == "async":
                raise ValueError(f"async mover {mover.name!r} requires speed > 0")
        return

    has_time = AxisRole.TIME in (x_axis, y_axis)
    has_pitch = AxisRole.PITCH in (x_axis, y_axis) or AxisRole.OCTAVE in (x_axis, y_axis)
    if not has_time or not has_pitch:
        raise ValueError(
            "points-0 axis time requires one time axis and one pitch/octave axis "
            f"(got x={x_axis.value}, y={y_axis.value}, flow={time_flow.value})"
        )
    if time_flow == TimeFlow.X and x_axis != AxisRole.TIME:
        raise ValueError("time.flow=x requires x_axis=time")
    if time_flow == TimeFlow.Y and y_axis != AxisRole.TIME:
        raise ValueError("time.flow=y requires y_axis=time")
