from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from xypi.channels.config import ChannelConfig
from xypi.channels.interpreter import Channel, StepEvent
from xypi.spatial.patterns import geometry_to_feature_dict

XYPI_VERSION = 3


def export_channel_geojson(
    path: str | Path,
    channel: Channel,
    *,
    bpm: float = 150.0,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    events = [
        {
            "step": e.step,
            "time_beats": e.time_beats,
            "time_sec": e.time_sec,
            "x": e.x,
            "y": e.y,
            "midi": e.midi,
            "value": e.value,
            "hit": e.hit,
            "inside": e.inside,
            "grid_col": e.grid_col,
            "grid_row": e.grid_row,
        }
        for e in channel.events
    ]

    xypi_props: dict[str, Any] = {
        "version": XYPI_VERSION,
        "bpm": bpm,
        "channel": channel.config.to_dict(),
        "grid": {"time": channel.grid_time, "pitch": channel.grid_pitch},
        "grid_layout": channel.grid_layout,
        "source_points": [{"x": x, "y": y} for x, y in channel.source_points],
        "events": events,
    }
    if channel.radial_center is not None:
        xypi_props["radial"] = {
            "center": {"x": channel.radial_center[0], "y": channel.radial_center[1]},
            "max_radius": channel.max_radius,
        }

    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "properties": {"xypi": xypi_props},
        "features": [
            geometry_to_feature_dict(channel.config.spatial_pattern_id, channel.geometry)
        ],
    }
    path.write_text(json.dumps(collection, indent=2))
    return path


def load_channel_geojson(path: str | Path) -> tuple[ChannelConfig, Any, list[StepEvent], float]:
    data = json.loads(Path(path).read_text())
    props = data["properties"]["xypi"]
    bpm = float(props.get("bpm", 150))
    config = ChannelConfig.from_dict(props["channel"])
    geometry = shape(data["features"][0]["geometry"])
    events = [
        StepEvent(
            step=e["step"],
            time_beats=e["time_beats"],
            time_sec=e["time_sec"],
            x=e["x"],
            y=e["y"],
            midi=e["midi"],
            value=float(e.get("value", e.get("midi", 0))),
            hit=e["hit"],
            inside=e["inside"],
            grid_col=int(e.get("grid_col", -1)),
            grid_row=int(e.get("grid_row", -1)),
        )
        for e in props["events"]
    ]
    return config, geometry, events, bpm
