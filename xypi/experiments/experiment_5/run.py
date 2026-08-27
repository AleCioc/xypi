#!/usr/bin/env python3
"""Experiment 5 — moving_points REPL + map mixer.

Interactive Python editor (like experiment_4) focused on moving_points time flow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xypi.experiments.experiment_5.server import serve


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="XYPI experiment 5 — moving_points REPL + map")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8003)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
