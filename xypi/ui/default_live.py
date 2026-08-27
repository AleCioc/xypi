"""Default live performance script for the unified XYPI UI.

Axis configs (same as experiments 3–5):
  time_flow='x'  → horizontal time, vertical pitch   (x=time, y=pitch)
  time_flow='y'  → vertical time, horizontal pitch   (x=pitch, y=time)
  time_flow='moving_points' → horizontal pitch, vertical release (x=pitch, y=release)
  mode='sample'  → pitch axis = sample slot, release axis = level
"""

# --- OSM schools: time × pitch (experiment 4 default) ---
play(
    schools_pattern(max_points=120),
    name="schools",
    time_flow="x",
    x_axis="time",
    y_axis="pitch",
    mode="synth",
    root_midi=48,
    pitch_cells=8,
    release_cells=6,
    n_steps=8,
)

# --- Vertical time (experiment 3) ---
# play(schools_pattern(), name="schools_y", time_flow="y", x_axis="pitch", y_axis="time", pitch_cells=8)

# --- Sample + release level on y (experiment 4 rows) ---
# play(schools_pattern(), name="schools_sample", mode="sample", pitch_cells=5, release_cells=6)

# --- Pitch × release moving_points (experiment 5) ---
# nodes = pois_to_points(schools())[:12]
# edges = [(i, i + 1) for i in range(len(nodes) - 1)]
# play(
#     point_graph(nodes, edges).to_geodataframe(),
#     name="school_walk",
#     time_flow="moving_points",
#     x_axis="pitch",
#     y_axis="release",
#     pitch_cells=8,
#     release_cells=6,
#     moving_points=MovingPointsConfig(
#         edges=edges,
#         movers=[moving_agent("walker", path=list(range(len(nodes))) + [0])],
#     ),
# )

# --- Street moving_agent (OSC / SuperCollider corners) ---
# l1 = moving_agent(
#     "area",
#     [(0.45, 0.15), (0.45, 0.30), (0.20, 0.45), (0.45, 0.20)],
#     speed=50,
#     behaviour=random_walk,
#     sound="bass",
#     output="osc",
# )
