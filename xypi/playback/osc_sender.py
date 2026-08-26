from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from xypi.channels.interpreter import Channel, StepEvent

try:
    from pythonosc.udp_client import SimpleUDPClient
except ImportError as exc:
    raise ImportError("Install python-osc: pip install python-osc") from exc


@dataclass
class OscTarget:
    host: str = "127.0.0.1"
    port: int = 4560
    synth_path: str = "/xypi/synth"
    sample_path: str = "/xypi/sample"
    step_path: str = "/xypi/step"


@dataclass
class OscPlayback:
    """Send interpreted channel events to Sonic Pi via OSC."""

    channels: list[Channel]
    bpm: float = 150.0
    target: OscTarget = field(default_factory=OscTarget)
    _client: SimpleUDPClient | None = field(default=None, init=False, repr=False)

    @property
    def n_steps(self) -> int:
        return self.channels[0].config.time.n_steps if self.channels else 8

    @property
    def step_sec(self) -> float:
        return (60.0 / self.bpm) * self.channels[0].config.time.beats_per_step

    @property
    def cycle_sec(self) -> float:
        return self.n_steps * self.step_sec

    def connect(self) -> None:
        self._client = SimpleUDPClient(self.target.host, self.target.port)

    def send_event(self, channel: Channel, event: StepEvent) -> None:
        if not self._client or not event.hit or event.value <= 0:
            return
        name = channel.config.name
        mode = channel.config.sound.mode
        amp = 0.45
        if mode == "sample":
            self._client.send_message(
                self.target.sample_path,
                [name, int(event.value), amp, event.step, float(event.x), float(event.y)],
            )
        else:
            self._client.send_message(
                self.target.synth_path,
                [name, int(event.value), amp, event.step, float(event.x), float(event.y)],
            )

    def send_step(self, step: int) -> None:
        if not self._client:
            return
        self._client.send_message(self.target.step_path, [step, self.bpm])
        for channel in self.channels:
            if step < len(channel.events):
                self.send_event(channel, channel.events[step])

    def run_forever(
        self,
        *,
        max_cycles: int | None = None,
        on_step: Callable[[int, int], None] | None = None,
    ) -> None:
        """Loop steps indefinitely (or for ``max_cycles``) and send OSC hits."""
        if not self._client:
            self.connect()

        cycle = 0
        try:
            while max_cycles is None or cycle < max_cycles:
                next_tick = time.perf_counter()
                for step in range(self.n_steps):
                    self.send_step(step)
                    if on_step:
                        on_step(step, cycle)
                    next_tick += self.step_sec
                    delay = next_tick - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                cycle += 1
        except KeyboardInterrupt:
            pass
