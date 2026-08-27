#!/usr/bin/env python3
"""XYPI unified entry point — map agents + spatial channels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running without install: python xypi/run.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xypi.map.locations import DEFAULT_LOCATION, MAP_PRESETS, list_locations
from xypi.ui.server import serve_ui


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="XYPI — unified map agents + spatial channels server",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--location", "--map", dest="location", choices=sorted(MAP_PRESETS), default=DEFAULT_LOCATION)
    p.add_argument("--zoom", type=float, default=None)
    p.add_argument("--osc-host", default="127.0.0.1")
    p.add_argument("--osc-port", type=int, default=57120)
    p.add_argument("--live", type=Path, default=None, help="path to live.py performance script")
    p.add_argument("--list-locations", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_locations:
        for loc in list_locations():
            lat, lon = loc["center"]
            print(f"{loc['id']:9s} {loc['name']:22s} ({lat:.5f}, {lon:.5f}) zoom={loc['zoom']}")
        return
    serve_ui(
        host=args.host,
        port=args.port,
        location_id=args.location,
        zoom=args.zoom,
        live_path=args.live,
        osc_host=args.osc_host,
        osc_port=args.osc_port,
    )


if __name__ == "__main__":
    main()
