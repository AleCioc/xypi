"""Pattern templates and GeoJSON loading for experiment_4 REPL."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import geopandas as gpd

from xypi.spatial.patterns import line_string, multi_line_string, multipoint

EXAMPLES_DIR = Path(__file__).parent / "examples"


def load_geojson(path: str | Path) -> gpd.GeoDataFrame:
    """Load a GeoJSON file as GeoDataFrame.

    Relative paths are resolved against ``experiment_4/examples/`` first,
    then the current working directory.
    """
    path = Path(path)
    if not path.is_absolute():
        candidate = EXAMPLES_DIR / path
        if candidate.exists():
            path = candidate
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {path}")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def coords_gdf(coords: list[tuple[float, float]], *, name: str = "pattern") -> gpd.GeoDataFrame:
    """Build a one-row GeoDataFrame from a list of (x, y) points."""
    return multipoint(coords, name=name).to_geodataframe()


def grid_coords(
    *,
    cols: int = 8,
    rows: int = 6,
    x0: float = 1,
    y0: float = 1,
    dx: float = 1,
    dy: float = 1,
) -> list[tuple[float, float]]:
    """Rectangular grid — use inside a list comp or pass to ``coords_gdf``."""
    return [(x0 + c * dx, y0 + r * dy) for r in range(rows) for c in range(cols)]


def diagonal_coords(*, n: int = 8, x0: float = 1, y0: float = 1) -> list[tuple[float, float]]:
    return [(x0 + i, y0 + i) for i in range(n)]


def ring_coords(
    cx: float,
    cy: float,
    radius: float,
    *,
    n: int = 12,
) -> list[tuple[float, float]]:
    return [
        (cx + radius * math.cos(2 * math.pi * i / n), cy + radius * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def zigzag_coords(*, n: int = 8, x0: float = 1, y0: float = 1, amp: float = 3) -> list[tuple[float, float]]:
    return [(x0 + i, y0 + (amp if i % 2 else 0)) for i in range(n)]


def wave_line(
    *,
    n: int = 16,
    x0: float = 1,
    y0: float = 4,
    amp: float = 2,
    wavelength: float = 4,
) -> list[tuple[float, float]]:
    return [(x0 + i, y0 + amp * math.sin(2 * math.pi * i / wavelength)) for i in range(n)]


def rows_as_lines(
    *,
    cols: int = 8,
    rows: int = 4,
    x0: float = 1,
    y0: float = 1,
    dx: float = 1,
    dy: float = 1,
) -> list[list[tuple[float, float]]]:
    """One horizontal line per row — feed to ``multi_line_string``."""
    return [[(x0 + c * dx, y0 + r * dy) for c in range(cols)] for r in range(rows)]


def staggered_cols(*, cols: int = 8, x0: float = 1, y0: float = 1, dy: float = 1) -> list[tuple[float, float]]:
    """One point per column, pitch alternates — good for arpeggio-like grids."""
    return [(x0 + c, y0 + (c % 3) * dy) for c in range(cols)]


TEMPLATE_SNIPPETS: list[dict[str, str]] = [
    {
        "title": "Grid of points",
        "code": (
            "coords = [(x, y) for x in range(1, 9) for y in range(1, 7)]\n"
            "grid = coords_gdf(coords, name='grid')\n"
            "play(grid, name='grid', pitch_cells=6)"
        ),
    },
    {
        "title": "Diagonal melody",
        "code": (
            "diag = coords_gdf([(i, i) for i in range(1, 9)])\n"
            "play(diag, name='diag', root_midi=60)"
        ),
    },
    {
        "title": "Ring + radial time",
        "code": (
            "ring = coords_gdf([(8 + 3*math.cos(k), 8 + 3*math.sin(k)) "
            "for k in [2*math.pi*i/12 for i in range(12)]])\n"
            "play(ring, name='ring', time_flow='radial', x_axis='pitch', "
            "y_axis='octave', pitch_cells=12, center_x=8, center_y=8)"
        ),
    },
    {
        "title": "Zigzag line (vertical time)",
        "code": (
            "zig = line_string([(i, 1 + (3 if i % 2 else 0)) for i in range(1, 9)]"
            ").to_geodataframe()\n"
            "play(zig, name='zigzag', time_flow='y', x_axis='pitch', y_axis='time')"
        ),
    },
    {
        "title": "Wave line",
        "code": (
            "wave = line_string(wave_line(n=16, amp=2)).to_geodataframe()\n"
            "play(wave, name='wave', pitch_cells=8)"
        ),
    },
    {
        "title": "Multi-row lines",
        "code": (
            "rows = multi_line_string(\n"
            "    [[(c, r) for c in range(1, 9)] for r in range(1, 5)]\n"
            ").to_geodataframe()\n"
            "play(rows, name='rows', mode='sample', pitch_cells=5)"
        ),
    },
    {
        "title": "Staggered columns (arpeggio)",
        "code": (
            "arp = coords_gdf([(c, 1 + c % 3) for c in range(1, 9)])\n"
            "play(arp, name='arp', root_midi=48, pitch_cells=8)"
        ),
    },
    {
        "title": "Moving points — sync hops (pitch × release)",
        "code": (
            "nodes = [(2, 2), (8, 2), (5, 7)]\n"
            "edges = [(0, 1), (1, 2), (2, 0)]\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "play(g, name='walker', time_flow='moving_points',\n"
            "     pitch_cells=8, release_cells=6,\n"
            "     moving_points=MovingPointsConfig(\n"
            "         edges=edges,\n"
            "         movers=[MoverConfig(name='walker', movement='sync', path=[0,1,2,0])]))"
        ),
    },
    {
        "title": "Moving points — async (speed × segment length)",
        "code": (
            "nodes = [(2, 2), (8, 2), (5, 7)]\n"
            "edges = [(0, 1), (1, 2), (2, 0)]\n"
            "g = point_graph(nodes, edges).to_geodataframe()\n"
            "play(g, name='glide', time_flow='moving_points',\n"
            "     beats_per_step=0.5,\n"
            "     moving_points=MovingPointsConfig(\n"
            "         edges=edges,\n"
            "         movers=[MoverConfig(name='glide', movement='async', speed=2.0, path=[0,1,2,0])]))"
        ),
    },
]

GEOJSON_EXAMPLE: dict[str, str] = {
    "title": "Load GeoJSON file",
    "file": "city_paths.geojson",
    "code": (
        "# Sample file ships in experiment_4/examples/\n"
        "paths = load_geojson('city_paths.geojson')\n"
        "print(paths[['name', 'geometry']])\n"
        "play(paths, name='city', pitch_cells=8)\n"
        "\n"
        "# Or an absolute / custom path:\n"
        "# routes = load_geojson('/path/to/your/file.geojson')"
    ),
}


def help_templates() -> str:
    lines = [
        "List-comprehension & helper templates — copy blocks into the terminal.\n",
        f"Example GeoJSON directory: {EXAMPLES_DIR}\n",
    ]
    for i, snippet in enumerate(TEMPLATE_SNIPPETS, 1):
        lines.append(f"--- {i}. {snippet['title']} ---")
        lines.append(snippet["code"])
        lines.append("")
    lines.append(f"--- GeoJSON: {GEOJSON_EXAMPLE['title']} ---")
    lines.append(GEOJSON_EXAMPLE["code"])
    text = "\n".join(lines)
    print(text)
    return text


def template_names() -> list[str]:
    return [s["title"] for s in TEMPLATE_SNIPPETS]
