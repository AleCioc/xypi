"""Experiment 4 — REPL help payload."""

from __future__ import annotations

from xypi.experiments.experiment_4.session import ReplSession
from xypi.experiments.experiment_4.templates import GEOJSON_EXAMPLE, TEMPLATE_SNIPPETS

_session = ReplSession()


def get_session() -> ReplSession:
    return _session


def help_payload() -> dict:
    return {
        "intro": "XYPI Experiment 4 — GeoDataFrame variables → musical maps.",
        "welcome_lines": [
            "Click Templates for list-comprehension patterns.",
            "Type help_templates() in the terminal for the full catalog.",
        ],
        "play": _session.help_play(),
        "examples": [
            "pts = multipoint([(2,2), (4,4), (6,2), (5,5)]).to_geodataframe()",
            "play(pts, name='scatter', x_axis='time', y_axis='pitch')",
            "grid = coords_gdf([(x, y) for x in range(1, 9) for y in range(1, 7)])",
            "play(grid, name='grid', pitch_cells=6)",
            "paths = load_geojson('city_paths.geojson')",
            "play(paths, name='city')",
            "help_templates()",
            "list_channels()",
        ],
        "templates": TEMPLATE_SNIPPETS,
        "geojson_example": GEOJSON_EXAMPLE,
    }
