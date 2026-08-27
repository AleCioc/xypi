"""Copy-paste spatial channel examples for the unified UI (POI-focused)."""

from __future__ import annotations

CHANNEL_EXAMPLES: list[dict[str, str]] = [
    {
        "id": "schools_synth",
        "label": "Schools · synth",
        "code": (
            "play(schools_pattern(), name='schools', mode='synth', root_midi=48,\n"
            "     time_flow='x', pitch_cells=8, n_steps=8)"
        ),
    },
    {
        "id": "hospitals_sample",
        "label": "Hospitals · sample",
        "code": (
            "play(hospitals_pattern(), name='hospitals', mode='sample',\n"
            "     time_flow='x', pitch_cells=6, n_steps=8)"
        ),
    },
    {
        "id": "schools_vertical",
        "label": "Schools · vertical time · synth",
        "code": (
            "play(schools_pattern(), name='schools_y', mode='synth', time_flow='y',\n"
            "     x_axis='pitch', y_axis='time', pitch_cells=8)"
        ),
    },
    {
        "id": "poi_moving_points",
        "label": "School POIs · moving_points · synth",
        "code": (
            "nodes = pois_to_points(schools())[:6]\n"
            "edges = [(i, i + 1) for i in range(len(nodes) - 1)]\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "play(g, name='school_walk', mode='synth', time_flow='moving_points',\n"
            "     moving_points=MovingPointsConfig(\n"
            "         edges=edges,\n"
            "         movers=[MoverConfig(name='walker', path=list(range(len(nodes))) + [0])]))"
        ),
    },
    {
        "id": "dual_poi_sample",
        "label": "Schools + hospitals · sample",
        "code": (
            "play(schools_pattern(max_points=12), name='schools', mode='sample', pitch_cells=6)\n"
            "play(hospitals_pattern(max_points=8), name='hospitals', mode='sample', pitch_cells=5)"
        ),
    },
]
