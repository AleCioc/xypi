#!/usr/bin/env python3
"""Experiment 0 — web mixer viewer (GeoJSON export).

Four polygons · points-0 · 8 steps @ 150 BPM · complementary pitch grids.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xypi.channels.interpreter import interpret_channel, count_hits
from xypi.experiments.shared.setup import build_composition, channel_summary
from xypi.spatial.geojson import export_channel_geojson

OUTPUT_DIR = Path(__file__).parent / "output"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    composition = build_composition()

    for config in composition.channels.values():
        geometry = composition.patterns[config.spatial_pattern_id]
        channel = interpret_channel(config, geometry)
        export_channel_geojson(OUTPUT_DIR / f"{config.name}.geojson", channel, bpm=composition.bpm)
        hits = count_hits(channel)
        print(channel_summary(config, hits=hits, source_points=len(channel.source_points),
                              grid=(channel.grid_time, channel.grid_pitch)))

    print(f"\nOpen viewer: cd {Path(__file__).resolve().parent.parent / 'experiment_2'} && python -m http.server 8000")


if __name__ == "__main__":
    main()
