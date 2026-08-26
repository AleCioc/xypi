# XYPI

Geospatial patterns mapped to musical **channels**.

## Defaults

8 time steps · 150 BPM · space mode `points-0`

## Time flow

| `time.flow` | Meaning |
|-------------|---------|
| `x` | Time progresses horizontally (columns) |
| `y` | **Vertical time** — tempo moves bottom→top (rows) |
| `radial` | Expanding ring from center to perimeter; x/y are pitch (note + octave) |

## Experiments

### experiment_0 — web mixer (polygons)

```bash
python xypi/experiments/experiment_0/run.py
cd xypi/viewer && python -m http.server 8000
```

### experiment_1 — Sonic Pi OSC

See `xypi/experiments/experiment_1/`.

### experiment_3 — mixed geometries + radial time

```bash
python xypi/experiments/experiment_3/run.py
cd xypi/experiments/experiment_3 && python -m http.server 8001
# → http://localhost:8001/index.html
```

Patterns: **MultiPoint**, **LineString**, **MultiLineString**, **Polygon**, **MultiPolygon**, radial point cloud.

| Channel | Pattern | Time |
|---------|---------|------|
| `pts_x_time` | MultiPoint | horizontal (x) |
| `line_y_time` | LineString | **vertical (y)** |
| `mlines_x_time` | MultiLineString | horizontal (x) |
| `mpoly_y_time` | MultiPolygon | **vertical (y)** |
| `radial_note_octave` | radial cloud | **radial** (x=note, y=octave) |

Viewer highlights active pitch cells on the orthogonal axis and shows an orange time band (column, row, or ring).
