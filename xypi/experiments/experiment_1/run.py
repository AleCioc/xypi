#!/usr/bin/env python3
"""Experiment 1 — infinite OSC loop driving Sonic Pi.

Uses the same spatial patterns as experiment_0. Run ``xypi_receiver.spi`` in
Sonic Pi first, then start this script.

  python xypi/experiments/experiment_1/run.py
  python xypi/experiments/experiment_1/run.py --host 127.0.0.1 --port 4560
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xypi.channels.interpreter import interpret_channel
from xypi.experiments.shared.setup import BPM, N_STEPS, build_composition, channel_summary
from xypi.playback.osc_sender import OscPlayback, OscTarget

SAMPLE_NAMES = ("", "kick", "snare", "hat", "blip")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="XYPI → Sonic Pi OSC loop")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4560)
    p.add_argument("--cycles", type=int, default=None, help="Stop after N cycles (default: infinite)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    composition = build_composition()
    channels = []
    for config in composition.channels.values():
        geometry = composition.patterns[config.spatial_pattern_id]
        ch = interpret_channel(config, geometry)
        channels.append(ch)
        hits = sum(1 for e in ch.events if e.hit)
        print(channel_summary(config, hits=hits, source_points=len(ch.source_points),
                              grid=(ch.grid_time, ch.grid_pitch)))

    playback = OscPlayback(
        channels=channels,
        bpm=BPM,
        target=OscTarget(host=args.host, port=args.port),
    )
    playback.connect()

    step_sec = playback.step_sec
    print(f"\nOSC → {args.host}:{args.port} · {BPM} BPM · {N_STEPS} steps · {step_sec:.3f}s/step")
    print("Ctrl+C to stop.\n")

    def on_step(step: int, cycle: int) -> None:
        parts = []
        for ch in channels:
            ev = ch.events[step]
            if not ev.hit:
                continue
            mode = ch.config.sound.mode
            if mode == "sample":
                slot = int(ev.value)
                parts.append(f"{ch.config.name}:{SAMPLE_NAMES[slot]}")
            else:
                parts.append(f"{ch.config.name}:midi{int(ev.value)}")
        if parts:
            print(f"cycle {cycle + 1} step {step + 1}/{N_STEPS}  " + "  ".join(parts))

    playback.run_forever(max_cycles=args.cycles, on_step=on_step)


if __name__ == "__main__":
    main()
