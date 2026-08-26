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

Or install dependencies only:

```bash
pip install -r requirements.txt
```

All experiment commands below assume you are in the **repository root** (the directory that contains the `xypi/` package folder).

## Time flow

| `time.flow` | Meaning |
|-------------|---------|
| `x` | Time progresses horizontally (columns) |
| `y` | **Vertical time** — tempo moves bottom→top (rows) |
| `radial` | Expanding ring from center to perimeter; x/y are pitch (note + octave) |

## Experiments

### experiment_0 — web mixer (polygons)

Generates four polygon channels as GeoJSON and opens the shared web viewer.

```bash
python xypi/experiments/experiment_0/run.py
cd xypi/viewer && python -m http.server 8000
```

Open [http://localhost:8000/index.html](http://localhost:8000/index.html), press **Play**, and toggle individual channels.

| Channel | Time | Sound |
|---------|------|-------|
| `poly_a_synth` | horizontal (x) | synth |
| `poly_b_synth` | vertical (y) | synth |
| `poly_c_sample` | horizontal (x) | sample |
| `poly_d_sample` | vertical (y) | sample |

### experiment_1 — Sonic Pi OSC

Uses the same spatial patterns as experiment_0, streamed over OSC to Sonic Pi.

1. Open Sonic Pi and load `xypi/experiments/experiment_1/xypi_receiver.spi`.
2. Run the sender (from the repo root):

```bash
python xypi/experiments/experiment_1/run.py
# optional flags:
python xypi/experiments/experiment_1/run.py --host 127.0.0.1 --port 4560 --cycles 4
```

Press Ctrl+C to stop the loop.

### experiment_3 — mixed geometries + radial time

Patterns: **MultiPoint**, **LineString**, **MultiLineString**, **Polygon**, **MultiPolygon**, radial point cloud.

```bash
python xypi/experiments/experiment_3/run.py
cd xypi/experiments/experiment_3 && python -m http.server 8001
```

Open [http://localhost:8001/index.html](http://localhost:8001/index.html).

| Channel | Pattern | Time |
|---------|---------|------|
| `pts_x_time` | MultiPoint | horizontal (x) |
| `line_y_time` | LineString | **vertical (y)** |
| `mlines_x_time` | MultiLineString | horizontal (x) |
| `mpoly_y_time` | MultiPolygon | **vertical (y)** |
| `radial_note_octave` | radial cloud | **radial** (x=note, y=octave) |

The viewer highlights active pitch cells on the orthogonal axis and shows an orange time band (column, row, or ring).

## Project layout

```
xypi/                  # Python package
  channels/            # axis roles, channel config, interpreter
  spatial/             # patterns, points, GeoJSON export
  playback/            # scheduling and OSC sender
  viewer/              # web mixer (HTML/JS)
  experiments/         # runnable demos
requirements.txt
pyproject.toml
```

## Python API (quick start)

```python
from xypi.channels.config import ChannelConfig, Composition, SoundParams, TimeConfig
from xypi.channels.interpreter import interpret_channel
from xypi.spatial.patterns import polygon
from xypi.spatial.geojson import export_channel_geojson
from xypi.channels.axes import AxisRole, TimeFlow
from xypi.spatial.space_config import SpaceConfig

composition = Composition(bpm=150)
composition.add_pattern("my_poly", polygon([(0, 0), (4, 0), (4, 4), (0, 4)]).geometry)
composition.add_channel(ChannelConfig(
    name="demo",
    spatial_pattern_id="my_poly",
    x_axis=AxisRole.TIME,
    y_axis=AxisRole.PITCH,
    sound=SoundParams(mode="synth", root_midi=60, pitch_range=12),
    time=TimeConfig(n_steps=8, bpm=150, flow=TimeFlow.X),
    space=SpaceConfig(pitch_cells=5),
))

config = composition.channels["demo"]
channel = interpret_channel(config, composition.patterns["my_poly"])
export_channel_geojson("demo.geojson", channel, bpm=150)
```
