"""Runtime street agent state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from xypi.agents.layer import Layer
from xypi.map.graph import Edge


@dataclass
class StreetAgent:
    name: str
    layer: Layer
    node: int
    speed_mps: float = 1.4
    previous_node: int | None = None
    target_node: int | None = None
    edge: Edge | None = None
    street_started: float = 0.0
    edge_last_update: float = 0.0
    edge_progress_m: float = 0.0
    edge_duration: float = 0.0
    x: float = 0.0
    y: float = 0.0
    last_event: dict | None = None
    behaviour: str | None = None
    behaviour_fn: Callable | None = field(default=None, repr=False)
    sound: str = "sine"
    output: str = "osc"
    status: str = "waiting for agent configuration"

    def public_state(self) -> dict:
        return {
            "name": self.name,
            "layer": self.layer.name,
            "x": self.x,
            "y": self.y,
            "node": self.node,
            "target_node": self.target_node,
            "speed_mps": self.speed_mps,
            "behaviour": self.behaviour,
            "sound": self.sound,
            "output": self.output,
            "status": self.status,
            "edge_duration": self.edge_duration,
            "last_event": self.last_event,
        }

    def make_event(self) -> dict:
        return {
            "time": time.time(),
            "sound": self.sound,
            "output": self.output,
            "x_timbre": self.x,
            "y_pitch": self.y,
            "duration": max(time.time() - self.street_started, 0.0) if self.street_started else 0.0,
            "mover": self.name,
        }
