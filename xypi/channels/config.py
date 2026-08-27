from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from xypi.channels.axes import AxisRole, TimeFlow
from xypi.spatial.space_config import SpaceConfig, resolve_time_flow, validate_space_config


Mode = Literal["synth", "sample"]


@dataclass
class TimeConfig:
    n_steps: int = 8
    bpm: float = 150.0
    beats_per_step: float = 1.0
    time_pattern: list[int] | int = 1
    flow: TimeFlow = TimeFlow.X

    def pattern(self) -> list[int]:
        if self.time_pattern == 1:
            return [1] * self.n_steps
        if self.time_pattern == 0:
            return [0] * self.n_steps
        p = list(self.time_pattern)
        if len(p) < self.n_steps:
            p = (p * ((self.n_steps // len(p)) + 1))[: self.n_steps]
        return p[: self.n_steps]

    def beat_sec(self) -> float:
        return 60.0 / self.bpm

    def step_sec(self) -> float:
        return self.beat_sec() * self.beats_per_step


@dataclass
class SoundParams:
    mode: Mode = "synth"
    root_midi: int = 48
    pitch_range: int = 12
    note_semitones: int = 12

    def pitch_to_midi(self, coord: float, *, min_coord: float, max_coord: float) -> int:
        span = max(max_coord - min_coord, 1e-9)
        norm = (coord - min_coord) / span
        return self.root_midi + int(norm * self.pitch_range) % max(self.pitch_range, 1)

    def pitch_to_sample(self, coord: float, *, min_coord: float, max_coord: float) -> int:
        span = max(max_coord - min_coord, 1e-9)
        norm = (coord - min_coord) / span
        return int(norm * 4) % 4 + 1

    def release_from_coord(self, coord: float, *, min_coord: float, max_coord: float) -> float:
        span = max(max_coord - min_coord, 1e-9)
        return max(0.0, min(1.0, (coord - min_coord) / span))

    def synth_pitch_release(
        self,
        px: float,
        py: float,
        *,
        minx: float,
        maxx: float,
        miny: float,
        maxy: float,
    ) -> tuple[int, float]:
        midi = self.pitch_to_midi(px, min_coord=minx, max_coord=maxx)
        release = self.release_from_coord(py, min_coord=miny, max_coord=maxy)
        return midi, release

    def sample_slot_level(
        self,
        px: float,
        py: float,
        *,
        minx: float,
        maxx: float,
        miny: float,
        maxy: float,
    ) -> tuple[int, float]:
        slot = self.pitch_to_sample(px, min_coord=minx, max_coord=maxx)
        level = self.release_from_coord(py, min_coord=miny, max_coord=maxy)
        return slot, level

    def value_from_coord(
        self,
        coord: float,
        *,
        min_coord: float,
        max_coord: float,
    ) -> float:
        if self.mode == "synth":
            return float(self.pitch_to_midi(coord, min_coord=min_coord, max_coord=max_coord))
        return float(self.pitch_to_sample(coord, min_coord=min_coord, max_coord=max_coord))

    def midi_from_note_octave(
        self,
        x: float,
        y: float,
        *,
        minx: float,
        maxx: float,
        miny: float,
        maxy: float,
        note_cells: int,
        octave_cells: int,
    ) -> float:
        note = int((x - minx) / max(maxx - minx, 1e-9) * note_cells) % max(self.note_semitones, 1)
        octave = int((y - miny) / max(maxy - miny, 1e-9) * octave_cells)
        return float(self.root_midi + note + 12 * octave)


@dataclass
class ChannelConfig:
    name: str
    spatial_pattern_id: str
    x_axis: AxisRole
    y_axis: AxisRole
    sound: SoundParams = field(default_factory=SoundParams)
    time: TimeConfig = field(default_factory=TimeConfig)
    space: SpaceConfig = field(default_factory=SpaceConfig)

    @property
    def time_flow(self) -> TimeFlow:
        return resolve_time_flow(x_axis=self.x_axis, y_axis=self.y_axis, flow=self.time.flow)

    def __post_init__(self) -> None:
        validate_space_config(
            self.space,
            x_axis=self.x_axis,
            y_axis=self.y_axis,
            time_flow=self.time_flow,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "spatial_pattern_id": self.spatial_pattern_id,
            "x_axis": self.x_axis.value,
            "y_axis": self.y_axis.value,
            "sound": {
                "mode": self.sound.mode,
                "root_midi": self.sound.root_midi,
                "pitch_range": self.sound.pitch_range,
                "note_semitones": self.sound.note_semitones,
            },
            "time": {
                "n_steps": self.time.n_steps,
                "bpm": self.time.bpm,
                "beats_per_step": self.time.beats_per_step,
                "time_pattern": self.time.time_pattern,
                "flow": self.time_flow.value,
            },
            "space": self.space.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelConfig:
        sound = data.get("sound", {})
        time = data.get("time", {})
        x_axis = AxisRole(data["x_axis"])
        y_axis = AxisRole(data["y_axis"])
        flow_raw = time.get("flow")
        if flow_raw == "moving_point":
            flow_raw = "moving_points"
        flow = TimeFlow(flow_raw) if flow_raw else None
        resolved = resolve_time_flow(x_axis=x_axis, y_axis=y_axis, flow=flow)
        return cls(
            name=data["name"],
            spatial_pattern_id=data["spatial_pattern_id"],
            x_axis=x_axis,
            y_axis=y_axis,
            sound=SoundParams(
                mode=sound.get("mode", "synth"),
                root_midi=int(sound.get("root_midi", 48)),
                pitch_range=int(sound.get("pitch_range", 12)),
                note_semitones=int(sound.get("note_semitones", 12)),
            ),
            time=TimeConfig(
                n_steps=int(time.get("n_steps", 8)),
                bpm=float(time.get("bpm", 150)),
                beats_per_step=float(time.get("beats_per_step", 1.0)),
                time_pattern=time.get("time_pattern", 1),
                flow=resolved,
            ),
            space=SpaceConfig.from_dict(data.get("space", {})),
        )


@dataclass
class Composition:
    bpm: float = 150.0
    channels: dict[str, ChannelConfig] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)

    def add_pattern(self, pattern_id: str, geometry: Any) -> None:
        self.patterns[pattern_id] = geometry

    def add_channel(self, config: ChannelConfig) -> None:
        config.time.bpm = self.bpm
        self.channels[config.name] = config
