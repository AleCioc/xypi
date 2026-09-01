#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from core import DEFAULT_LOCATION, MAP_PRESETS, list_locations
from server import serve_ui


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="XYPI: POI grid sequencer + street agents")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--location", choices=sorted(MAP_PRESETS), default=DEFAULT_LOCATION)
    p.add_argument("--zoom", type=float, default=None)
    p.add_argument("--osc-host", default="127.0.0.1")
    p.add_argument("--osc-port", type=int, default=4560)
    p.add_argument("--live", type=Path, default=None)
    p.add_argument("--list-locations", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_locations:
        for loc in list_locations():
            lat, lon = loc["center"]
            print(f"{loc['id']:9s} {loc['name']:22s} ({lat:.5f}, {lon:.5f}) zoom={loc['zoom']}")
        return
    serve_ui(args.host, args.port, args.location, args.zoom, args.live, args.osc_host, args.osc_port)


if __name__ == "__main__":
    main()
