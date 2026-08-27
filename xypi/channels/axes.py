from __future__ import annotations

from enum import Enum


class AxisRole(str, Enum):
    TIME = "time"
    PITCH = "pitch"
    OCTAVE = "octave"
    RELEASE = "release"


class TimeFlow(str, Enum):
    """Where musical time lives in the spatial map."""

    X = "x"        # time progresses along x (columns)
    Y = "y"        # time progresses along y (rows, vertical)
    RADIAL = "radial"  # expanding ring from center to perimeter
    MOVING_POINTS = "moving_points"  # one or more points hopping along graph edges
