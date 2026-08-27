"""Moving-points templates for experiment_5 REPL."""

from __future__ import annotations

MOVING_POINTS_SNIPPETS: list[dict[str, str]] = [
    {
        "title": "Sync triangle — one mover",
        "code": (
            "nodes = [(2, 2), (8, 2), (5, 7)]\n"
            "edges = [(0, 1), (1, 2), (2, 0)]\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "play(g, name='tri_sync', time_flow='moving_points',\n"
            "     pitch_cells=8, release_cells=6,\n"
            "     moving_points=MovingPointsConfig(\n"
            "         edges=edges,\n"
            "         movers=[MoverConfig(name='walker', movement='sync', path=[0, 1, 2, 0])]))"
        ),
    },
    {
        "title": "Two movers on separate islands",
        "code": (
            "nodes = [(1, 1), (3, 3), (10, 1), (12, 4)]\n"
            "edges = [(0, 1), (2, 3)]  # islands not connected\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "play(g, name='dual_islands', time_flow='moving_points', mode='sample',\n"
            "     moving_points=MovingPointsConfig(\n"
            "         edges=edges,\n"
            "         movers=[\n"
            "             MoverConfig(name='alpha', path=[0, 1, 0, 1]),\n"
            "             MoverConfig(name='beta', path=[2, 3, 2, 3]),\n"
            "         ]))"
        ),
    },
    {
        "title": "Async + sync on same graph",
        "code": (
            "nodes = [(2, 2), (8, 2), (5, 7)]\n"
            "edges = [(0, 1), (1, 2), (2, 0)]\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "mp = MovingPointsConfig(\n"
            "    edges=edges,\n"
            "    movers=[\n"
            "        MoverConfig(name='clock', movement='sync', path=[0, 1, 2, 0]),\n"
            "        MoverConfig(name='glide', movement='async', speed=2.0, path=[2, 0, 1, 2]),\n"
            "    ])\n"
            "play(g, name='duo', time_flow='moving_points', beats_per_step=0.5, moving_points=mp)"
        ),
    },
    {
        "title": "List-comprehension node chain + two movers",
        "code": (
            "nodes = [(x, 1 + (x % 3)) for x in range(2, 14, 2)]\n"
            "edges = [(i, i + 1) for i in range(len(nodes) - 1)]\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "play(g, name='chain', time_flow='moving_points',\n"
            "     moving_points=MovingPointsConfig(\n"
            "         edges=edges,\n"
            "         movers=[\n"
            "             MoverConfig(name='fwd', path=list(range(len(nodes)))),\n"
            "             MoverConfig(name='back', path=list(range(len(nodes)-1, -1, -1))),\n"
            "         ]))"
        ),
    },
]

# Legacy alias
MOVING_POINT_SNIPPETS = MOVING_POINTS_SNIPPETS


def help_templates() -> str:
    lines = ["moving_points templates — x=pitch, y=release, multiple movers on one graph\n"]
    for i, snippet in enumerate(MOVING_POINTS_SNIPPETS, 1):
        lines.append(f"--- {i}. {snippet['title']} ---")
        lines.append(snippet["code"])
        lines.append("")
    text = "\n".join(lines)
    print(text)
    return text
