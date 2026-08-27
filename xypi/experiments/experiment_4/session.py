"""Python REPL session for experiment_4 — GeoDataFrame variables → music maps."""

from __future__ import annotations

import io
import math
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.channels.config import ChannelConfig, SoundParams, TimeConfig
from xypi.channels.interpreter import Channel, count_hits, interpret_channel
from xypi.experiments.experiment_4.templates import (
    EXAMPLES_DIR,
    GEOJSON_EXAMPLE,
    TEMPLATE_SNIPPETS,
    coords_gdf,
    diagonal_coords,
    grid_coords,
    help_templates,
    load_geojson,
    ring_coords,
    rows_as_lines,
    staggered_cols,
    wave_line,
    zigzag_coords,
)
from xypi.spatial.geojson import channel_to_geojson_dict
from xypi.spatial.moving_points import MoverConfig, MovingPointsConfig
from xypi.spatial.patterns import (
    line_string,
    multi_line_string,
    multi_polygon,
    multipoint,
    point_graph,
    polygon,
    to_geodataframe,
)
from xypi.spatial.space_config import SpaceConfig

_AXIS_ALIASES = {
    "time": AxisRole.TIME,
    "pitch": AxisRole.PITCH,
    "octave": AxisRole.OCTAVE,
    "release": AxisRole.RELEASE,
    "t": AxisRole.TIME,
    "p": AxisRole.PITCH,
    "o": AxisRole.OCTAVE,
    "r": AxisRole.RELEASE,
}

_FLOW_ALIASES = {
    "x": TimeFlow.X,
    "y": TimeFlow.Y,
    "radial": TimeFlow.RADIAL,
    "moving_points": TimeFlow.MOVING_POINTS,
    "moving_point": TimeFlow.MOVING_POINTS,
    "moving": TimeFlow.MOVING_POINTS,
}


def _parse_axis(value: str | AxisRole) -> AxisRole:
    if isinstance(value, AxisRole):
        return value
    key = str(value).strip().lower()
    if key not in _AXIS_ALIASES:
        raise ValueError(f"Unknown axis {value!r} — use time, pitch, or octave")
    return _AXIS_ALIASES[key]


def _parse_flow(value: str | TimeFlow) -> TimeFlow:
    if isinstance(value, TimeFlow):
        return value
    key = str(value).strip().lower()
    if key not in _FLOW_ALIASES:
        raise ValueError(f"Unknown time flow {value!r} — use x, y, radial, or moving_points")
    return _FLOW_ALIASES[key]


def gdf_to_geometry(gdf: gpd.GeoDataFrame) -> BaseGeometry:
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError(f"Expected GeoDataFrame, got {type(gdf).__name__}")
    if gdf.empty:
        raise ValueError("GeoDataFrame is empty")
    geoms = [g for g in gdf.geometry if g is not None and not g.is_empty]
    if not geoms:
        raise ValueError("GeoDataFrame has no valid geometries")
    if len(geoms) == 1:
        return geoms[0]
    return unary_union(geoms)


class ReplSession:
    """Persistent interpreter namespace with XYPI playback helpers."""

    def __init__(self) -> None:
        self._channels: dict[str, dict[str, Any]] = {}
        self._channel_meta: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self.namespace: dict[str, Any] = {}
        self._seed_namespace()

    def _seed_namespace(self) -> None:
        self.namespace.clear()
        self.namespace.update(
            {
                "__builtins__": __builtins__,
                "gpd": gpd,
                "math": math,
                "Path": Path,
                "polygon": polygon,
                "multipoint": multipoint,
                "line_string": line_string,
                "multi_line_string": multi_line_string,
                "multi_polygon": multi_polygon,
                "point_graph": point_graph,
                "MoverConfig": MoverConfig,
                "MovingPointsConfig": MovingPointsConfig,
                "MovingPointConfig": MovingPointsConfig,
                "load_geojson": load_geojson,
                "coords_gdf": coords_gdf,
                "grid_coords": grid_coords,
                "diagonal_coords": diagonal_coords,
                "ring_coords": ring_coords,
                "zigzag_coords": zigzag_coords,
                "wave_line": wave_line,
                "rows_as_lines": rows_as_lines,
                "staggered_cols": staggered_cols,
                "EXAMPLES_DIR": EXAMPLES_DIR,
                "AxisRole": AxisRole,
                "TimeFlow": TimeFlow,
                "ChannelConfig": ChannelConfig,
                "SoundParams": SoundParams,
                "TimeConfig": TimeConfig,
                "SpaceConfig": SpaceConfig,
                "play": self.play,
                "stop": self.stop,
                "clear": self.clear,
                "list_channels": self.list_channels,
                "channels": self._channels_view,
                "help_play": self.help_play,
                "help_templates": help_templates,
            }
        )

    def _channels_view(self) -> dict[str, dict[str, Any]]:
        return dict(self._channel_meta)

    def help_play(self) -> str:
        return (
            "play(gdf, name=None, x_axis=None, y_axis=None, time_flow=None, "
            "mode='synth', root_midi=48, pitch_range=12, n_steps=8, bpm=150, "
            "pitch_cells=6, octave_cells=4, release_cells=6, center_x=None, center_y=None, "
            "moving_points=None, beats_per_step=1.0)\n"
            "  Defaults: time×pitch (time_flow='x'); "
            "moving_points → pitch×release automatically."
        )

    def play(
        self,
        gdf: gpd.GeoDataFrame,
        name: str | None = None,
        *,
        x_axis: str | AxisRole | None = None,
        y_axis: str | AxisRole | None = None,
        time_flow: str | TimeFlow | None = None,
        mode: str = "synth",
        root_midi: int = 48,
        pitch_range: int = 12,
        note_semitones: int = 12,
        n_steps: int = 8,
        bpm: float = 150.0,
        pitch_cells: int = 6,
        octave_cells: int = 4,
        release_cells: int = 6,
        center_x: float | None = None,
        center_y: float | None = None,
        moving_points: MovingPointsConfig | None = None,
        beats_per_step: float = 1.0,
    ) -> str:
        geometry = gdf_to_geometry(gdf)
        self._counter += 1
        channel_name = name or f"channel_{self._counter}"

        flow = _parse_flow(time_flow or "x")
        if moving_points is not None:
            flow = TimeFlow.MOVING_POINTS

        if flow == TimeFlow.MOVING_POINTS:
            x_role = _parse_axis(x_axis or "pitch")
            y_role = _parse_axis(y_axis or "release")
        else:
            x_role = _parse_axis(x_axis or "time")
            y_role = _parse_axis(y_axis or "pitch")

        config = ChannelConfig(
            name=channel_name,
            spatial_pattern_id=channel_name,
            x_axis=x_role,
            y_axis=y_role,
            sound=SoundParams(
                mode=mode,  # type: ignore[arg-type]
                root_midi=root_midi,
                pitch_range=pitch_range,
                note_semitones=note_semitones,
            ),
            time=TimeConfig(n_steps=n_steps, bpm=bpm, flow=flow, beats_per_step=beats_per_step),
            space=SpaceConfig(
                pitch_cells=pitch_cells,
                octave_cells=octave_cells,
                release_cells=release_cells,
                center_x=center_x,
                center_y=center_y,
                moving_points=moving_points,
            ),
        )
        channel: Channel = interpret_channel(config, geometry)
        hits = count_hits(channel)
        payload = channel_to_geojson_dict(channel, bpm=bpm)
        self._channels[channel_name] = payload
        self._channel_meta[channel_name] = {
            "name": channel_name,
            "hits": hits,
            "steps": n_steps,
            "grid": [channel.grid_time, channel.grid_pitch],
            "time_flow": config.time_flow.value,
            "x_axis": x_role.value,
            "y_axis": y_role.value,
            "mode": mode,
            "source_points": len(channel.source_points),
        }
        print(
            f"▶ {channel_name}: {hits}/{n_steps} hits · {len(channel.source_points)} pts · "
            f"grid {channel.grid_time}×{channel.grid_pitch} · time={config.time_flow.value}"
        )
        return channel_name

    def stop(self, name: str) -> None:
        if name not in self._channels:
            raise KeyError(f"Unknown channel {name!r} — use list_channels()")
        del self._channels[name]
        del self._channel_meta[name]
        print(f"Stopped channel {name!r}")

    def clear(self) -> None:
        self._channels.clear()
        self._channel_meta.clear()
        print("Cleared all channels")

    def list_channels(self) -> list[str]:
        names = list(self._channels.keys())
        if not names:
            print("(no active channels)")
        else:
            for name in names:
                meta = self._channel_meta[name]
                print(
                    f"  {name}: {meta['hits']}/{meta['steps']} hits · "
                    f"time={meta['time_flow']} · {meta['mode']}"
                )
        return names

    def channel_payloads(self) -> list[dict[str, Any]]:
        return list(self._channels.values())

    def channel_names(self) -> list[str]:
        return list(self._channels.keys())

    def execute(self, code: str) -> dict[str, Any]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        result_repr: str | None = None
        error: str | None = None

        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                compiled = compile(code, "<terminal>", "exec")
                exec(compiled, self.namespace)
        except SyntaxError:
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = eval(code, self.namespace)
                if result is not None:
                    result_repr = repr(result)
            except Exception:
                error = traceback.format_exc()
        except Exception:
            error = traceback.format_exc()

        return {
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "result": result_repr,
            "error": error,
            "channels": self.channel_names(),
            "channel_meta": self._channel_meta,
        }

    def reset(self) -> None:
        self._channels.clear()
        self._channel_meta.clear()
        self._counter = 0
        self._seed_namespace()
