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
| `moving_points` | One or more points hop along graph edges; **x = pitch**, **y = release** |

## moving_points — graph-based time

Instead of scanning a grid left-to-right or bottom-to-top, time follows **movers** travelling on a **node graph**. Each mover has its own path; every step can trigger **multiple notes** (one per mover that lands on a node).

### Axes and grid

- **x** → pitch (MIDI or sample slot)
- **y** → release / level (0–1)
- Grid size: `pitch_cells` × `release_cells` (defaults 8 × 6)
- Nodes are placed in world coordinates; the viewer maps them to pitch×release cells with padded bounds so dots sit **inside** their cells

### Configuration

Build a graph with `point_graph(nodes, edges)` — nodes are `(x, y)` tuples, edges are `(from_index, to_index)` pairs.

**MovingPointsConfig** — shared graph for all movers:

| Field | Meaning |
|-------|---------|
| `edges` | Allowed hops `[(0, 1), (2, 3), …]` — movers can only travel along these |
| `movers` | List of `MoverConfig` (each independent) |

**MoverConfig** — one travelling point:

| Field | Meaning |
|-------|---------|
| `name` | Mover id (shown in the mixer step label) |
| `movement` | `"sync"` — one node per clock step; `"async"` — speed × edge length |
| `speed` | Spatial units per beat (`async` only) |
| `path` | Node indices e.g. `[0, 1, 2, 0]` — consecutive pairs must share an edge |
| `start_node` | Starting node when path is auto-built (default `0`) |
| `loop` | Repeat path (default `True`) |

### Movement modes

| Mode | Behaviour |
|------|-----------|
| **sync** | Jumps one node per step on the global clock — every step can sound |
| **async** | Travels continuously at `speed` units/beat — notes fire on **arrival** at nodes; longer edges take more beats |

### REPL shortcut — `play()` auto-axes

When `time_flow='moving_points'` or `moving_points=…` is passed, `play()` automatically sets **x = pitch** and **y = release**. You do not need to pass `x_axis` / `y_axis` unless overriding.

```python
nodes = [(2, 2), (8, 2), (5, 7)]
edges = [(0, 1), (1, 2), (2, 0)]
g = point_graph(nodes, edges).to_geodataframe()

play(g, name="walker", time_flow="moving_points",
     moving_points=MovingPointsConfig(
         edges=edges,
         movers=[MoverConfig(name="walker", movement="sync", path=[0, 1, 2, 0])]))
```

### Multiple movers on one graph

Declare several `MoverConfig` entries sharing the same `edges`. Each step merges hits from all movers into one event with multiple **activations** — e.g. two movers on separate islands → two notes per step.

**Two islands (disconnected subgraphs):**

```python
nodes = [(1, 1), (3, 3), (10, 1), (12, 4)]
edges = [(0, 1), (2, 3)]  # no edge between islands

play(point_graph(nodes, edges).to_geodataframe(), name="islands",
     time_flow="moving_points",
     moving_points=MovingPointsConfig(
         edges=edges,
         movers=[
             MoverConfig(name="alpha", path=[0, 1, 0, 1, 0, 1, 0, 1]),
             MoverConfig(name="beta",  path=[2, 3, 2, 3, 2, 3, 2, 3]),
         ]))
```

**Sync + async on the same triangle:**

```python
mp = MovingPointsConfig(
    edges=edges,
    movers=[
        MoverConfig(name="clock", movement="sync", path=[0, 1, 2, 0]),
        MoverConfig(name="glide", movement="async", speed=2.0, path=[2, 0, 1, 2]),
    ])
play(g, name="duo", time_flow="moving_points", beats_per_step=0.5, moving_points=mp)
```

### Viewer

The shared web mixer (`experiments/shared/viewer/`) shows:

- Graph edges as blue lines, static nodes as small dots
- **Coloured mover dots** per step (one colour per mover)
- **Pitch×release grid** — during playback, only the **current step's** cells are highlighted
- Step bar and label list each mover's note (e.g. `alpha:midi 48, beta:midi 52`)

### Library API (ChannelConfig)

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

### Backward compatibility

- `time_flow="moving_point"` (singular) still works
- Old GeoJSON with `"moving_point"` keys loads via aliases
- `MovingPointConfig` is an alias for `MovingPointsConfig`
- Legacy single-mover dicts (without a `movers` list) load as one mover named `mover_0`

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
| `point_graph(nodes, edges)` | MultiPoint + LineString edges for `moving_points` |
| `MoverConfig`, `MovingPointsConfig` | Configure graph movers |
| `coords_gdf`, `grid_coords`, `wave_line`, … | List-comprehension helpers (see below) |
| `load_geojson(path)` | Load a GeoJSON file as GeoDataFrame |
| `play(gdf, …)` | Interpret geometry and add a music map |
| `help_templates()` | Print all copy-paste pattern templates |
| `stop(name)` / `clear()` / `list_channels()` | Manage active channels |

**`play()` defaults:**

| Context | Default axes | Default flow |
|---------|--------------|--------------|
| General | `x_axis='time'`, `y_axis='pitch'` | `time_flow='x'` |
| `moving_points` | `x_axis='pitch'`, `y_axis='release'` (automatic) | — |

Pass `moving_points=MovingPointsConfig(…)` or `time_flow='moving_points'` — axes switch to pitch×release unless you override them.

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

Same **Python editor + map mixer** layout as experiment_4, with templates focused on `moving_points` — sync/async movers, dual islands, list-comprehension chains.

```bash
python xypi/experiments/experiment_5/run.py
# → http://127.0.0.1:8003/
```

Click **Templates** for copy-paste snippets. Optional static export:

```bash
python xypi/experiments/experiment_5/export_demos.py
# → experiment_5/output/*.geojson
```

See [moving_points](#moving_points--graph-based-time) above for the full API. Experiment 5 is the quickest way to try multi-mover graphs interactively.

## Unified UI (XYPI_v2 + spatial channels)

The **`xypi/ui`** module merges the map-agent live editor (XYPI_v2) with spatial channel REPL functionality.

```bash
python xypi/run.py
# → http://127.0.0.1:8080/
python xypi/run.py --location taranto
python xypi/run.py --list-locations
```

### Locations (one active at a time)

| ID | City |
|----|------|
| `trento` | Trento, Italy (default) |
| `taranto` | Taranto, Italy |
| `antwerp` | Antwerp, Belgium |

On startup the server loads **OpenStreetMap** data: road network, schools (`amenity=school`), and hospitals (`amenity=hospital`). POIs appear as dots on the map; use `schools()`, `hospitals()`, and `schools_pattern()` in the Channels panel.

### `moving_agent` — unified keyword

| Mode | Usage |
|------|--------|
| **Street** (map agents) | `moving_agent("points", [(0.5, 0.5)], speed=14, sound="harmonic")` in `live.py` as `l1`, `l2`, … |
| **Grid** (spatial channels) | `moving_agent("alpha", path=[0, 1], movement="sync")` inside `MovingPointsConfig` |

### Output modes

| Type | Audio |
|------|-------|
| Street agents (`live.py`) | OSC → SuperCollider — `xypi/ui/receivers/supercollider_receiver.scd` |
| Spatial channels (`play()`) | WebAudio in browser, or Sonic Pi — `xypi/ui/receivers/sonicpi_receiver.spi` |

Experiments 0–5 continue to work independently on their original ports.

## Project layout

```
xypi/
  channels/            # axis roles, channel config, interpreter
  map/                 # OSM locations, street graph, POIs
  agents/              # street moving_agent engine
  ui/                  # unified web server + interface
  spatial/             # patterns, moving_points, moving_agent
  playback/            # scheduling and OSC sender
  run.py               # unified entry point
  experiments/
    shared/viewer/     # shared web mixer (player.js, style.css)
    shared/repl/       # legacy REPL UI (experiments 4/5)
    experiment_0/      # GeoJSON export
    experiment_2/      # web mixer viewer
    experiment_4/      # REPL + live map
    experiment_5/      # moving_points REPL + demos
```
