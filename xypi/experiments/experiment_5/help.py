"""Experiment 5 — REPL help payload (moving_points focus)."""

from __future__ import annotations

from xypi.experiments.experiment_5.session import MovingPointsReplSession
from xypi.experiments.experiment_5.templates import MOVING_POINTS_SNIPPETS

_session = MovingPointsReplSession()


def get_session() -> MovingPointsReplSession:
    return _session


def help_payload() -> dict:
    return {
        "intro": "XYPI Experiment 5 — moving_points time flow (pitch × release, multiple movers).",
        "welcome_lines": [
            "x = pitch · y = release · declare several MoverConfig on one graph",
            "movement sync | async per mover · edges define allowed hops",
            "Click Templates · help_templates() in terminal",
        ],
        "play": _session.help_play(),
        "examples": [
            "nodes = [(1, 1), (3, 3), (10, 1), (12, 4)]",
            "edges = [(0, 1), (2, 3)]",
            "play(point_graph(nodes, edges).to_geodataframe(), name='islands',",
            "     time_flow='moving_points', x_axis='pitch', y_axis='release',",
            "     moving_points=MovingPointsConfig(edges=edges, movers=[",
            "         MoverConfig(name='alpha', path=[0, 1, 0, 1]),",
            "         MoverConfig(name='beta', path=[2, 3, 2, 3]),]))",
            "help_templates()",
        ],
        "templates": MOVING_POINTS_SNIPPETS,
    }
