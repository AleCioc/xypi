# XYPI — OpenStreetMap grids + street agents

**Final v9 reference README**

XYPI is a live-coding environment that turns OpenStreetMap data into two concurrent musical systems:

1. **POI grids** — fixed geographic points of interest are quantized into a step sequencer.
2. **Street agents** — autonomous agents move through the actual OSM street graph and trigger sound when they reach corners/intersections.

The browser is used only for **visualization and live-code editing**. All sound is sent by OSC to **SuperCollider**. Both grids and street agents use the same OSC event format.

---

## 1. Run

Start SuperCollider and evaluate:

```text
supercollider_receiver.scd
```

Then start XYPI:

```bash
python run.py
```

Open:

```text
http://127.0.0.1:8080/
```

Default OSC target:

```text
127.0.0.1:57120
```

Available command-line options:

```bash
python run.py --location trento
python run.py --location taranto
python run.py --location antwerp
python run.py --zoom 15
python run.py --osc-host 127.0.0.1 --osc-port 57120
python run.py --host 127.0.0.1 --port 8080
python run.py --list-locations
```

No mandatory third-party Python packages are required. `certifi` is optional if the local Python SSL certificate store causes HTTPS problems:

```bash
pip install certifi
```

---

## 2. Live-code structure

Both musical systems use the same `l1`, `l2`, ... connection naming style:

```python
l1 = grid("hospitals", steps=8, bpm=120, direction="horizontal", movement="linear", sound="hh")

l2 = grid("restaurants", steps=12, bpm=138, direction="vertical", movement="backforth", sound="harmonic")

l3 = agent("area", [(0.15,0.15), (0.75,0.15), (0.72,0.72), (0.20,0.78)], speed=8, behaviour=random_walk, sound="bass")
```

The variable name is the connection name. Therefore `l1`, `l2`, and `l3` are also the names sent to SuperCollider in OSC messages.

Changes can be applied from the browser with **Apply** or **Cmd/Ctrl+Enter**.

---

# 3. Sound / synth names

The `sound=` argument selects the SuperCollider sound used by either a grid or an agent.

## Canonical sound names

| Live-code name | SuperCollider SynthDef | Description |
|---|---|---|
| `kick` | `xypiKick` | Kick drum |
| `snare` | `xypiSnare` | Snare/noise percussion |
| `hh` | `xypiHH` | Hi-hat / metallic noise |
| `sine` | `xypiSine` | Sine-based pitched synth |
| `bass` | `xypiBass` | Filtered VarSaw bass |
| `harmonic` | `xypiHarmonic` | Three-part harmonic synth |

## Accepted aliases

| Alias | Same as |
|---|---|
| `bd` | `kick` |
| `sd` | `snare` |
| `hat` | `hh` |

Examples:

```python
l1 = grid("schools", steps=8, sound="kick")
l2 = grid("restaurants", steps=12, sound="hh")
l3 = agent("area", [...], sound="bass")
l4 = agent("line", [...], sound="harmonic")
```

Any unrecognized sound name falls back to `xypiSine` in the supplied SuperCollider receiver. For predictable live coding, use the names listed above.

If a grid has no explicit `sound=`, it defaults to `sine`. There is no synth/sample `mode`: every grid and agent simply names the SuperCollider sound it wants to trigger.

---

# 4. Street agents

Street agents move over the real OpenStreetMap street graph. They do **not** use a global BPM sequencer. A sound event is generated when an agent reaches a meaningful street node/corner.

The two constructor names are equivalent:

```python
agent(...)
moving_agent(...)
```

`agent` is the shorter alias normally used in `live.py`.

## Agent types / shapes

There are three agent shapes.

### `area`

```python
l1 = agent(
    "area",
    [(0.15,0.15), (0.75,0.15), (0.72,0.72), (0.20,0.78)],
    speed=8,
    behaviour=random_walk,
    sound="bass"
)
```

The coordinates define a polygon. The agent is constrained to the connected street network inside that area.

Minimum coordinates: **3**.

Default behaviour: `random_walk`.

### `line`

```python
l2 = agent(
    "line",
    [(0.08,0.75), (0.45,0.45), (0.90,0.68)],
    speed=6,
    behaviour=straightish,
    sound="hh"
)
```

The control points are routed through the street network and define a street-following corridor.

Minimum coordinates: **2**.

Default behaviour: `straightish`.

### `points`

```python
l3 = agent(
    "points",
    [(0.22,0.25), (0.68,0.76), (0.84,0.30)],
    speed=5,
    behaviour=point_attract,
    sound="harmonic"
)
```

The points act as attraction targets while the agent remains on the street graph.

Minimum coordinates: **1**.

Default behaviour: `point_attract`.

All agent coordinates are normalized map coordinates:

```text
x = 0   west
x = 1   east
y = 0   south
y = 1   north
```

## Agent parameters

```text
agent(
    shape,
    coordinates,
    speed=1.4,
    behaviour=<default for shape>,
    sound="sine",
    output="osc",
)
```

`speed` is measured in metres per second and must be greater than zero.

`output` can be:

```text
osc
none
```

---

# 5. Agent movement behaviours

All eight built-in behaviours are directly available in `live.py`.

## `random_walk`

Chooses randomly among the available outgoing streets, normally avoiding immediate reversal when another option exists.

```python
behaviour=random_walk
```

## `straightish`

Prefers the outgoing street whose direction continues most closely from the incoming street.

```python
behaviour=straightish
```

## `backtrack`

Returns to the previous street node whenever possible.

```python
behaviour=backtrack
```

## `clockwiseish`

Prefers the outgoing street corresponding to the strongest clockwise turn relative to the incoming direction.

```python
behaviour=clockwiseish
```

## `anticlockwiseish`

Prefers the outgoing street corresponding to the strongest anticlockwise turn relative to the incoming direction.

```python
behaviour=anticlockwiseish
```

## `shortest_street`

Chooses the shortest available outgoing street segment.

```python
behaviour=shortest_street
```

## `longest_street`

Chooses the longest available outgoing street segment.

```python
behaviour=longest_street
```

## `point_attract`

Chooses streets that tend toward the declared attraction points. This is the default behaviour for `points` agents.

```python
behaviour=point_attract
```

### Complete behaviour list

```text
random_walk
straightish
backtrack
clockwiseish
anticlockwiseish
shortest_street
longest_street
point_attract
```

Behaviours can be supplied either as functions:

```python
behaviour=straightish
```

or by name:

```python
behaviour="straightish"
```

---

# 6. POI grid sequencer

A grid queries one category of real OpenStreetMap points of interest inside the current map view, normalizes their geographic coordinates, and quantizes them into a square spatial grid.

Example:

```python
l1 = grid(
    "hospitals",
    steps=8,
    bpm=120,
    direction="horizontal",
    movement="linear",
    sound="hh"
)
```

`steps` defines **both axes** of the quantization. Therefore:

```text
steps=8  -> 8 x 8 grid
steps=12 -> 12 x 12 grid
steps=16 -> 16 x 16 grid
```

There is no `rows` parameter.

If several POIs fall into the same cell, that cell is treated as one occupied sequencer cell.

---

# 7. Grid POI names

## Canonical POI category names

These are the canonical strings accepted by `grid(...)`:

```text
schools
hospitals
restaurants
bars
bus_stops
monuments
```

### `schools`

Main OSM tag:

```text
amenity=school
```

Also includes:

```text
amenity=kindergarten
amenity=college
building=school
```

Accepted aliases:

```text
school
kindergarten
college
```

Example:

```python
l1 = grid("schools", steps=8, sound="sine")
```

### `hospitals`

Main OSM tag:

```text
amenity=hospital
```

Also includes:

```text
amenity=clinic
healthcare=hospital
```

Accepted aliases:

```text
hospital
clinic
```

Example:

```python
l2 = grid("hospitals", steps=8, sound="harmonic")
```

### `restaurants`

OSM tag:

```text
amenity=restaurant
```

Accepted alias:

```text
restaurant
```

Example:

```python
l3 = grid("restaurants", steps=12, sound="hh")
```

### `bars`

Main OSM tag:

```text
amenity=bar
```

Also includes:

```text
amenity=pub
```

Accepted aliases:

```text
bar
pub
```

Example:

```python
l4 = grid("bars", steps=12, sound="snare")
```

### `bus_stops`

OSM tag:

```text
highway=bus_stop
```

Accepted aliases:

```text
bus_stop
busstop
```

Example:

```python
l5 = grid("bus_stops", steps=16, sound="kick")
```

### `monuments`

OSM tag:

```text
historic=monument
```

Accepted alias:

```text
monument
```

Example:

```python
l6 = grid("monuments", steps=8, sound="harmonic")
```

## Complete POI vocabulary

Canonical names:

```text
schools
hospitals
restaurants
bars
bus_stops
monuments
```

Accepted aliases:

```text
school
kindergarten
college
hospital
clinic
restaurant
bar
pub
bus_stop
busstop
monument
```

**Trees are intentionally not queried or exposed.**

---

# 8. Grid directions

Two canonical directions are available.

## `horizontal`

```python
direction="horizontal"
```

Map X becomes sequencer time. Map Y selects the other grid coordinate.

The active transport is visualized along the **bottom** of the browser.

Accepted aliases:

```text
horizontal
x
h
```

## `vertical`

```python
direction="vertical"
```

Map Y becomes sequencer time. Map X selects the other grid coordinate.

The active transport is visualized along the **left** side of the browser.

Accepted aliases:

```text
vertical
y
v
```

---

# 9. Grid movement names

There are three canonical grid movement modes.

## `linear`

```python
movement="linear"
```

Sequence:

```text
0 -> 1 -> 2 -> 3 -> ... -> last -> 0 -> ...
```

Accepted alias:

```text
forward
```

## `backforth`

```python
movement="backforth"
```

Sequence:

```text
0 -> 1 -> 2 -> 3 -> ... -> last -> ... -> 2 -> 1 -> 0 -> 1 -> ...
```

Accepted aliases:

```text
backforth
backandforth
pingpong
```

Hyphens and underscores are normalized, so forms such as `back-and-forth` and `back_and_forth` are also accepted.

## `random`

```python
movement="random"
```

Each sequencer tick selects a random temporal cell.

### Complete grid movement vocabulary

Canonical names:

```text
linear
backforth
random
```

Accepted aliases:

```text
forward
backandforth
pingpong
```

---

# 10. Complete `grid(...)` reference

The grid API has no `mode` argument. Audio is always sent by OSC; choose the receiving SuperCollider SynthDef with `sound=`.

```python
grid(
    places,
    steps=8,
    bpm=120,
    direction="horizontal",
    movement="linear",
    root_midi=48,
    pitch_range=12,
    beats_per_step=1.0,
    time_pattern=1,
    output="osc",
    amp=0.45,
    max_points=120,
    sound=None,
)
```

### Parameters

- `places` — POI category.
- `steps` — number of sequencer steps and number of spatial cells on both axes.
- `bpm` — grid tempo.
- `direction` — `horizontal` or `vertical`.
- `movement` — `linear`, `backforth`, or `random`.
- `root_midi` — retained pitch-grid parameter for compatibility.
- `pitch_range` — retained pitch-grid parameter for compatibility.
- `beats_per_step` — duration of one grid step in beats.
- `time_pattern` — optional binary mask over sequencer steps.
- `output` — OSC only. Legacy `browser` and `both` values are accepted but normalized to OSC.
- `amp` — retained channel amplitude metadata.
- `max_points` — maximum number of POIs used to construct the grid.
- `sound` — SuperCollider sound name.

Examples:

```python
l1 = grid("schools", steps=8, bpm=110, direction="horizontal", movement="linear", sound="sine")
l2 = grid("hospitals", steps=8, bpm=120, direction="vertical", movement="backforth", sound="harmonic")
l3 = grid("restaurants", steps=16, bpm=145, direction="horizontal", movement="random", sound="hh")
l4 = grid("bus_stops", steps=12, bpm=130, direction="vertical", movement="linear", sound="kick")
```

---

# 11. OSC protocol

Both POI grid hits and street-agent corner events send the same OSC message:

```text
/xypi/corner  connectionName  soundName  normalizedY  normalizedX  duration
```

Examples:

```text
/xypi/corner  l1  hh        0.63  0.27  0.50
/xypi/corner  l2  harmonic  0.41  0.72  0.43
/xypi/corner  l3  bass      0.58  0.35  1.12
```

For agents, `duration` is based on the actual traversal time of the previous street segment.

For grids, `duration` is the grid step duration:

```text
60 / bpm * beats_per_step
```

There is no browser audio path and no separate `/xypi/synth`, `/xypi/sample`, or `/xypi/step` protocol in this version.

---

# 12. Browser interface

The browser is a visual live-coding surface. It contains:

- the OSM street map as a full-screen background;
- transparent syntax-highlighted `live.py` above the map;
- text shadow/glow for readability;
- Code / Map interaction controls;
- `Hide UI` presentation toggle: hides the editor, buttons, status and legend while leaving the map, spatial layers, agents, corner pulses and sequencer indicators visible; the button remains as `Show UI`.
- pan, zoom, and reset for the map;
- location selection;
- POI points;
- quantized grid cells;
- street-agent areas, lines, and points;
- moving agents;
- fading-circle corner animations when agents trigger events;
- bottom sequencer lights for horizontal grids;
- left-side sequencer lights for vertical grids;
- Reload / Apply;
- Cmd/Ctrl+Enter to apply code;
- OSC grid transport Play / Stop.

The sequencer transport is intentionally kept at the browser edges rather than displayed as moving scan bands over the map.

---

# 13. Quick reference

## Sounds

```text
kick
bd
snare
sd
hh
hat
sine
bass
harmonic
```

## Agent constructors

```text
agent
moving_agent
```

## Agent shapes

```text
area
line
points
```

## Agent behaviours

```text
random_walk
straightish
backtrack
clockwiseish
anticlockwiseish
shortest_street
longest_street
point_attract
```

## Grid POIs

```text
schools
hospitals
restaurants
bars
bus_stops
monuments
```

## Grid directions

```text
horizontal
vertical
```

## Grid movements

```text
linear
backforth
random
```

---

# 14. Tests

```bash
python selftest.py
python live.py
```

`live.py` can be executed directly as a declaration/syntax check. The running XYPI engine performs the map binding, OSM loading, agent movement, grid clock, and OSC transmission.
