"""XYPI live performance file.

Run this file directly to syntax-check the declarations, or edit it while run.py is active.
"""

from core import agent, grid, random_walk


# Real OSM schools -> horizontal 8-step sequencer.
l0 = grid("schools", steps=8, bpm=120, direction="vertical", movement="linear", sound="bd")

# Real OSM hospitals -> horizontal 8-step sequencer.
l1 = grid("hospitals", steps=8, bpm=120, direction="horizontal", movement="linear", sound="hh")

# Real OSM restaurants -> vertical scanner that bounces at the ends.
#l2 = grid("restaurants", steps=24, bpm=60, direction="vertical", movement="backforth", sound="bass")

# Street topology -> autonomous moving agent.
#l3 = agent("area", [(0.45, 0.15), (0.72, 0.28), (0.68, 0.65), (0.25, 0.58)], speed=8, behaviour=random_walk, sound="harmonic")
#l4 = agent("area", [(0.45, 0.15), (0.72, 0.28), (0.68, 0.65), (0.25, 0.58)], speed=800000, behaviour=random_walk, sound="hh")

l3 = agent(
    "points",
    [(0.52,0.85), (0.68,0.76), (0.84,0.30)],
    speed=75,
    behaviour=point_attract,
    sound="harmonic"
)
