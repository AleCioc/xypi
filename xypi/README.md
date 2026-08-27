# XYPI

Geospatial patterns mapped to musical **channels**.

See the [repository README](../README.md) for setup and all experiments.

## Defaults

8 time steps · 150 BPM · space mode `points-0`

## Time flows

| Flow | Axes |
|------|------|
| `x` / `y` | time × pitch |
| `radial` | note × octave |
| `moving_points` | pitch × release — graph-based, multiple movers |

## Key modules

| Module | Role |
|--------|------|
| `channels/` | Axis roles, `ChannelConfig`, interpreter (multi-hit `activations` per step) |
| `spatial/patterns.py` | `point_graph`, polygons, lines |
| `spatial/moving_points.py` | `MoverConfig`, `MovingPointsConfig` |
| `spatial/geojson.py` | Channel → GeoJSON export |
| `experiments/shared/viewer/` | Web mixer — grid, multi-mover playback |

## Experiments

| Experiment | Port | Description |
|------------|------|-------------|
| `experiment_0` | — | Export polygon GeoJSON |
| `experiment_2` | 8000 | Web mixer viewer |
| `experiment_1` | — | Sonic Pi OSC |
| `experiment_3` | 8001 | Mixed geometries + radial time |
| `experiment_4` | 8002 | Python REPL + live map mixer |
| `experiment_5` | 8003 | `moving_points` REPL — sync/async, multi-mover graphs |
| **Unified UI** | **8080** | Map agents + spatial channels — `python xypi/run.py` |

Shared playback UI lives in `experiments/shared/viewer/`; unified UI in `ui/`.
