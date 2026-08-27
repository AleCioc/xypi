"""Agent declaration — street moving_agent and grid MoverConfig bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xypi.agents.behaviours import (
    BEHAVIOUR_REGISTRY,
    point_attract,
    random_walk,
    straightish,
)
from xypi.spatial.moving_points import MoverConfig, MovingPointsConfig

_DEFAULT_BEHAVIOUR = object()


@dataclass(frozen=True)
class StreetAgentSpec:
    """Street-graph agent layer (normalized 0–1 coordinates)."""

    shape: str
    coords: tuple[tuple[float, float], ...]
    speed_mps: float
    behaviour: object
    sound: str
    output: str = "osc"


def moving_agent(
    shape_or_name: str,
    coords: list | tuple | None = None,
    *,
    speed: float = 1.4,
    behaviour=_DEFAULT_BEHAVIOUR,
    sound: str = "sine",
    output: str = "osc",
    movement: str | None = None,
    path: list[int] | None = None,
    edges: list[tuple[int, int]] | None = None,
    **kwargs: Any,
):
    """Unified moving agent keyword.

    Street mode (XYPI_v2 style):
        moving_agent("points", [(0.5, 0.5)], speed=14, sound="harmonic")

    Grid mode (spatial channel / moving_points):
        moving_agent("alpha", path=[0, 1, 0], movement="sync", edges=[(0, 1)])
    """
    shape = str(shape_or_name).strip().lower()
    if shape in {"points", "line", "area"}:
        if coords is None:
            raise ValueError(f"{shape} requires coordinate list")
        pts = tuple(tuple(map(float, p)) for p in coords)
        minimum = {"points": 1, "line": 2, "area": 3}[shape]
        if len(pts) < minimum:
            raise ValueError(f"{shape} needs at least {minimum} coordinate(s)")
        if any(len(p) != 2 or p[0] < 0 or p[0] > 1 or p[1] < 0 or p[1] > 1 for p in pts):
            raise ValueError("street moving_agent coords must be normalized (x, y) in [0, 1]")
        speed_m = float(speed)
        if speed_m <= 0:
            raise ValueError("speed must be > 0")
        sound_name = str(sound).strip()
        if not sound_name:
            raise ValueError("sound must be a non-empty string")
        if behaviour is _DEFAULT_BEHAVIOUR:
            behaviour = {"points": point_attract, "line": straightish, "area": random_walk}[shape]
        if behaviour is not None and not callable(behaviour) and not isinstance(behaviour, str):
            raise TypeError("behaviour must be a function, function name, or None")
        return StreetAgentSpec(
            shape=shape,
            coords=pts,
            speed_mps=speed_m,
            behaviour=behaviour,
            sound=sound_name,
            output=str(output),
        )

    # Grid mover — delegate to MoverConfig (for moving_points spatial channels)
    name = shape_or_name
    mov = movement or kwargs.get("movement", "sync")
    return MoverConfig(
        name=str(name),
        movement=mov,  # type: ignore[arg-type]
        speed=float(kwargs.get("mover_speed", speed)),
        path=list(path) if path is not None else kwargs.get("path"),
        start_node=int(kwargs.get("start_node", 0)),
        loop=bool(kwargs.get("loop", True)),
    )


def pois_to_points(pois: list[dict], *, max_points: int = 32) -> list[tuple[float, float]]:
    """Convert OSM POI records to normalized point coords for patterns."""
    out: list[tuple[float, float]] = []
    for poi in pois[:max_points]:
        out.append((float(poi["x"]), float(poi["y"])))
    return out


LIVE_API = {
    "moving_agent": moving_agent,
    "agent": moving_agent,
    "MoverConfig": MoverConfig,
    "MovingPointsConfig": MovingPointsConfig,
    "MovingPointConfig": MovingPointsConfig,
    **BEHAVIOUR_REGISTRY,
}

# Backward-compatible alias used in XYPI_v2 live.py
agent = moving_agent

__all__ = [
    "LIVE_API",
    "MoverConfig",
    "MovingPointsConfig",
    "StreetAgentSpec",
    "agent",
    "moving_agent",
    "pois_to_points",
]
