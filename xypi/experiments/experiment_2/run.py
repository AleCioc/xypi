#!/usr/bin/env python3
"""Experiment 2 — web mixer viewer.

Loads GeoJSON exported by experiment_0 and serves the interactive mixer UI.
Run experiment_0 first if output files are missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

EXP_DIR = Path(__file__).parent
OUTPUT_DIR = EXP_DIR.parent / "experiment_0" / "output"
REQUIRED = [
    "poly_a_synth.geojson",
    "poly_b_synth.geojson",
    "poly_c_sample.geojson",
    "poly_d_sample.geojson",
]


def main() -> None:
    missing = [name for name in REQUIRED if not (OUTPUT_DIR / name).exists()]
    if missing:
        print("Missing GeoJSON — run experiment_0 first:")
        print("  python xypi/experiments/experiment_0/run.py")
        print(f"\nMissing files in {OUTPUT_DIR}:")
        for name in missing:
            print(f"  - {name}")
        raise SystemExit(1)

    print("Experiment 2 viewer ready.")
    print(f"  cd {EXP_DIR} && python -m http.server 8000")
    print("  → http://localhost:8000/index.html")


if __name__ == "__main__":
    main()
