# XYPI

Geospatial patterns mapped to musical **channels**.

Map Shapely geometries (points, lines, polygons) onto pitch/time grids, export GeoJSON for a web viewer, or drive Sonic Pi over OSC.

**Defaults:** 8 time steps · 150 BPM · space mode `points-0`

## Setup

Requires Python 3.10+.

```bash
cd /path/to/xypi
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

All experiment commands assume you are in the **repository root**.

## Time flow

| `time.flow` | Meaning |
|-------------|---------|
| `x` | Time progresses horizontally (columns) |
| `y` | **Vertical time** — tempo moves bottom→top (rows) |
| `radial` | Expanding ring from center to perimeter; x/y are pitch (note + octave) |
| `moving_points` | Time follows one or more points hopping along graph edges; x=pitch, y=release |

## Experiments

### experiment_0 — GeoJSON export (polygons)

```bash
python xypi/experiments/experiment_0/run.py
```

Generates four polygon channel GeoJSON files under `experiment_0/output/`.

### experiment_2 — web mixer

Interactive browser mixer for experiment_0 output.

```bash
python xypi/experiments/experiment_0/run.py   # if outputs missing
cd xypi/experiments/experiment_2 && python -m http.server 8000
```

Open [http://localhost:8000/index.html](http://localhost:8000/index.html).

### experiment_1 — Sonic Pi OSC

1. Load `xypi/experiments/experiment_1/xypi_receiver.spi` in Sonic Pi.
2. Run `python xypi/experiments/experiment_1/run.py`

### experiment_3 — mixed geometries + radial time

```bash
python xypi/experiments/experiment_3/run.py
cd xypi/experiments/experiment_3 && python -m http.server 8001
```

Open [http://localhost:8001/index.html](http://localhost:8001/index.html).

### experiment_4 — Python REPL + live map mixer

Split UI: **Python terminal** (left) + **map mixer** (right). Define spatial pattern variables as GeoDataFrames, then activate them with `play()`.

```bash
python xypi/experiments/experiment_4/run.py
# → http://127.0.0.1:8002/
```

Terminal helpers (preloaded in the REPL namespace):

| Function | Purpose |
|----------|---------|
| `polygon`, `multipoint`, `line_string`, … | Build patterns → `.to_geodataframe()` |
| `coords_gdf`, `grid_coords`, `wave_line`, … | List-comprehension helpers (see below) |
| `load_geojson(path)` | Load a GeoJSON file as GeoDataFrame |
| `play(gdf, name=..., x_axis='time', y_axis='pitch', ...)` | Interpret geometry and add a music map |
| `help_templates()` | Print all copy-paste pattern templates |
| `stop(name)` / `clear()` / `list_channels()` | Manage active channels |

Click **Templates** in the terminal panel (or run `help_templates()`) for ready-made list-comprehension snippets.

**List-comprehension templates:**

```python
# Grid of points
grid = coords_gdf([(x, y) for x in range(1, 9) for y in range(1, 7)])
play(grid, name="grid", pitch_cells=6)

# Diagonal melody
diag = coords_gdf([(i, i) for i in range(1, 9)])
play(diag, name="diag", root_midi=60)

# Zigzag line (vertical time)
zig = line_string([(i, 1 + (3 if i % 2 else 0)) for i in range(1, 9)]).to_geodataframe()
play(zig, name="zigzag", time_flow="y", x_axis="pitch", y_axis="time")

# Multi-row lines
rows = multi_line_string([[(c, r) for c in range(1, 9)] for r in range(1, 5)]).to_geodataframe()
play(rows, name="rows", mode="sample")

# Or use helpers directly
play(coords_gdf(grid_coords(cols=8, rows=4)), name="helper_grid")
play(line_string(wave_line(n=16)).to_geodataframe(), name="wave")
```

**Load from GeoJSON:**

A sample file ships at `xypi/experiments/experiment_4/examples/city_paths.geojson` (streets + stations).

```python
paths = load_geojson("city_paths.geojson")
print(paths[["name", "geometry"]])
play(paths, name="city", pitch_cells=8)

# Custom file (absolute path or relative to cwd)
routes = load_geojson("/path/to/your/data.geojson")
play(routes, name="routes")
```

Press **Play** in the map panel to hear all active channels.

### experiment_5 — moving_points REPL + map mixer

Same **Python editor + map mixer** layout as experiment_4, focused on `moving_points` — **multiple movers** on one spatial pattern.

```bash
python xypi/experiments/experiment_5/run.py
# → http://127.0.0.1:8003/
```

Click **Templates** for sync/async and dual-island snippets. Optional: `python xypi/experiments/experiment_5/export_demos.py` writes static GeoJSON under `output/`.

**MovingPointsConfig** — shared `edges` plus a list of **MoverConfig**:

| Field | Meaning |
|-------|---------|
| `edges` | Allowed hops for all movers `[(0, 1), (2, 3), …]` |
| `movers` | List of `MoverConfig`, each with its own `path`, `movement`, `speed` |

| MoverConfig field | Meaning |
|-------|---------|
| `name` | Mover id (shown in mixer / step label) |
| `movement` | `"sync"` (clock hops) or `"async"` (speed × distance) |
| `speed` | Spatial units per beat (async only) |
| `path` | Node indices e.g. `[0, 1, 0, 1]` — consecutive pairs must share an edge |

**Two movers on separate islands:**

```python
from xypi.spatial.moving_points import MoverConfig, MovingPointsConfig
from xypi.spatial.patterns import point_graph

nodes = [(1, 1), (3, 3), (10, 1), (12, 4)]
edges = [(0, 1), (2, 3)]  # no link between islands

play(point_graph(nodes, edges).to_geodataframe(), name="islands",
     time_flow="moving_points", x_axis="pitch", y_axis="release",
     moving_points=MovingPointsConfig(
         edges=edges,
         movers=[
             MoverConfig(name="alpha", path=[0, 1, 0, 1, 0, 1, 0, 1]),
             MoverConfig(name="beta",  path=[2, 3, 2, 3, 2, 3, 2, 3]),
         ]))
```

Each step triggers both movers independently — 2 notes per step when both land on nodes.

**Python example (single mover via ChannelConfig):**

```python
from xypi.channels.axes import AxisRole, TimeFlow
from xypi.channels.config import ChannelConfig, SoundParams, TimeConfig
from xypi.channels.interpreter import interpret_channel
from xypi.spatial.moving_points import MoverConfig, MovingPointsConfig
from xypi.spatial.patterns import point_graph
from xypi.spatial.space_config import SpaceConfig

nodes = [(2, 2), (8, 2), (5, 7)]
edges = [(0, 1), (1, 2), (2, 0)]
geom = point_graph(nodes, edges).geometry

config = ChannelConfig(
    name="walker",
    spatial_pattern_id="walker",
    x_axis=AxisRole.PITCH,
    y_axis=AxisRole.RELEASE,
    sound=SoundParams(mode="synth", root_midi=48, pitch_range=12),
    time=TimeConfig(n_steps=8, bpm=150, flow=TimeFlow.MOVING_POINTS),
    space=SpaceConfig(
        pitch_cells=8,
        release_cells=6,
        moving_points=MovingPointsConfig(
            edges=edges,
            movers=[MoverConfig(name="walker", movement="sync", path=[0, 1, 2, 0])],
        ),
    ),
)
channel = interpret_channel(config, geom)
```

Legacy `time_flow="moving_point"` and old single-mover GeoJSON still load via compatibility aliases.

## Project layout

```
xypi/
  channels/            # axis roles, channel config, interpreter
  spatial/             # patterns, points, GeoJSON export
  playback/            # scheduling and OSC sender
  experiments/
    shared/viewer/     # shared web mixer (player.js, style.css)
    experiment_0/      # GeoJSON export
    experiment_2/      # web mixer viewer
    experiment_4/      # REPL + live map
    experiment_5/      # moving_points time flow
```
