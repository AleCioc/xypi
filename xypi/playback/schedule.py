from __future__ import annotations

from dataclasses import dataclass

from xypi.channels.config import Composition
from xypi.channels.interpreter import Channel, interpret_channel


@dataclass
class ScheduledEvent:
    time_sec: float
    channel: str
    step: int
    value: float
    x: float
    y: float
    mode: str


def schedule_channel(channel: Channel) -> list[ScheduledEvent]:
    """Return playable events for one interpreted channel."""
    events: list[ScheduledEvent] = []
    mode = channel.config.sound.mode
    for e in channel.events:
        activations = e.activations if e.activations else ([e] if e.hit and e.value > 0 else [])
        for a in activations:
            if not a.hit or a.value <= 0:
                continue
            events.append(
                ScheduledEvent(
                    time_sec=e.time_sec,
                    channel=channel.config.name,
                    step=e.step,
                    value=a.value,
                    x=a.x,
                    y=a.y,
                    mode=mode,
                )
            )
    return events


def schedule_composition(composition: Composition) -> list[ScheduledEvent]:
    """Interpret and schedule all channels in a composition."""
    all_events: list[ScheduledEvent] = []
    for name, config in composition.channels.items():
        geometry = composition.patterns.get(config.spatial_pattern_id)
        if geometry is None:
            raise KeyError(f"Spatial pattern {config.spatial_pattern_id!r} not found for channel {name!r}")
        channel = interpret_channel(config, geometry)
        all_events.extend(schedule_channel(channel))
    all_events.sort(key=lambda e: (e.time_sec, e.channel))
    return all_events
