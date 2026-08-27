#!/usr/bin/env python3

import argparse
from pathlib import Path

import config
from engine import AgentMapEngine, serve

ROOT = Path(__file__).resolve().parent


def parse_args():
    p = argparse.ArgumentParser(description="XYPI map-agent livecoding v13")
    p.add_argument("--map", choices=sorted(config.MAP_PRESETS), default=config.DEFAULT_MAP, help="startup map preset")
    p.add_argument("--zoom", type=float, default=None, help="Web-map style zoom; larger = closer")
    p.add_argument("--lat", type=float, default=None, help="custom center latitude")
    p.add_argument("--lon", type=float, default=None, help="custom center longitude")
    p.add_argument("--name", default="Custom map", help="name for a custom --lat/--lon map")
    p.add_argument("--port", type=int, default=8001, help="local viewer HTTP port")
    p.add_argument("--list-maps", action="store_true", help="print available presets and exit")
    return p.parse_args()


def main():
    args = parse_args()
    if args.list_maps:
        for key, value in config.MAP_PRESETS.items():
            lat, lon = value["center"]
            print(f"{key:9s} {value['name']:20s} center=({lat:.5f}, {lon:.5f}) zoom={value['zoom']}")
        return

    if (args.lat is None) != (args.lon is None):
        raise SystemExit("--lat and --lon must be supplied together")
    if args.lat is not None:
        zoom = 16.0 if args.zoom is None else args.zoom
        config.MAP = config.make_map(args.name, args.lat, args.lon, zoom)
    else:
        config.MAP = config.preset_map(args.map, args.zoom)

    lat, lon = config.MAP["center"]
    print(f"[map] selected {config.MAP['name']} center=({lat:.5f}, {lon:.5f}) zoom={config.MAP['zoom']}")
    engine = AgentMapEngine(config, ROOT / "live.py")
    engine.start()
    serve(engine, port=args.port, index_name="index_v13.html")


if __name__ == "__main__":
    main()
