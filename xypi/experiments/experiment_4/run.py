#!/usr/bin/env python3
"""Experiment 4 — interactive Python terminal + map mixer.

Build GeoDataFrame variables in the terminal and call play() to render them
as musical maps in the browser.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from xypi.experiments.experiment_4.server import serve


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="XYPI experiment 4 — REPL + map mixer")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8002)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
