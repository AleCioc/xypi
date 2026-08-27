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

# --- Street moving_agent (OSC / SuperCollider corners) ---
l1 = moving_agent(
    "area",
    [(0.45, 0.15), (0.45, 0.30), (0.20, 0.45), (0.45, 0.20)],
    speed=50,
    behaviour=random_walk,
    sound="bass",
    output="osc",
)
