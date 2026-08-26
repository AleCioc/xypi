from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from xypi.channels.axes import AxisRole, TimeFlow

SpaceMode = Literal["points-0"]
SPACE_MODES = frozenset({"points-0"})


@dataclass
class SpaceConfig:
    """Rules for drawing activation points from a spatial pattern."""

    mode: SpaceMode = "points-0"
    pitch_cells: int = 8
    octave_cells: int = 4
    center_x: float | None = None
    center_y: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "pitch_cells": self.pitch_cells,
            "octave_cells": self.octave_cells,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpaceConfig:
        return cls(
            mode=data.get("mode", "points-0"),
            pitch_cells=int(data.get("pitch_cells", 8)),
            octave_cells=int(data.get("octave_cells", 4)),
            center_x=data.get("center_x"),
            center_y=data.get("center_y"),
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
    return {
        "time_flow": "radial",
        "time_cells": time_cells,
        "pitch_cells": pitch_cells,
        "time_axis": "radial",
        "pitch_axis_x": x_axis.value,
        "pitch_axis_y": y_axis.value,
    }


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
