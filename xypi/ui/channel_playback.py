"""Server-side OSC playback for spatial channels (experiment 1 / Sonic Pi style)."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from xypi.channels.interpreter import Channel
from xypi.playback.osc_sender import OscPlayback, OscTarget

if TYPE_CHECKING:
    from xypi.ui.session import UnifiedSession


class SpatialChannelPlayback:
    """Loop spatial channel sequencers over OSC (/xypi/synth, /xypi/sample, /xypi/step)."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 57120) -> None:
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._playback: OscPlayback | None = None
        self.active_outputs: list[str] = []

    def sync(self, session: UnifiedSession) -> None:
        """Start, restart, or stop OSC playback from the current session channels."""
        self.stop()
        pairs = session.channel_output_pairs()
        osc_channels = [ch for ch, output in pairs if output in ("osc", "both")]
        self.active_outputs = [output for _, output in pairs if output in ("osc", "both")]
        if not osc_channels:
            return

        bpm = float(osc_channels[0].config.time.bpm)
        self._playback = OscPlayback(
            channels=osc_channels,
            bpm=bpm,
            target=OscTarget(host=self.host, port=self.port),
        )
        self._playback.connect()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="xypi-spatial-osc", daemon=True)
        self._thread.start()
        names = [ch.config.name for ch in osc_channels]
        print(f"[audio] OSC spatial → {self.host}:{self.port} · {', '.join(names)}")

    def _run(self) -> None:
        playback = self._playback
        if not playback or not playback._client:
            return
        try:
            while not self._stop.is_set():
                next_tick = time.perf_counter()
                for step in range(playback.n_steps):
                    if self._stop.is_set():
                        return
                    playback.send_step(step)
                    next_tick += playback.step_sec
                    delay = next_tick - time.perf_counter()
                    if delay > 0:
                        if self._stop.wait(delay):
                            return
        except Exception as exc:
            print(f"[audio] OSC spatial playback stopped: {exc}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._playback = None
        self.active_outputs = []
