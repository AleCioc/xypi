"""Unified moving_agent keyword — street agents and grid movers."""

from __future__ import annotations

from xypi.agents.spec import StreetAgentSpec, agent, moving_agent, pois_to_points
from xypi.spatial.moving_points import (
    MoverConfig,
    MovingPointConfig,
    MovingPointsConfig,
    compute_mover_positions,
    resolve_graph,
)

__all__ = [
    "MoverConfig",
    "MovingPointConfig",
    "MovingPointsConfig",
    "StreetAgentSpec",
    "agent",
    "compute_mover_positions",
    "moving_agent",
    "pois_to_points",
    "resolve_graph",
]
