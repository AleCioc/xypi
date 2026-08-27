"""XYPI LIVE PERFORMANCE FILE

Declare each spatial agent independently, Tidal-style:

    l1 = agent("area",   [(x,y), ...], speed=3, behaviour=random_walk, sound="bass")
    l2 = agent("line",   [(x,y), ...], speed=5, behaviour=straightish, sound="hh")
    l3 = agent("points", [(x,y), ...], speed=4, sound="harmonic")

Normalized coordinates:
    x = 0 west, 1 east
    y = 0 south, 1 north

SHAPES
    "area"    territory: the agent can use connected streets inside the polygon
    "line"    corridor: the line is routed along real streets through the control points
    "points"  attraction constellation: dots pull the agent while it remains on streets

PREDEFINED BEHAVIOURS
    random_walk
    straightish
    backtrack
    clockwiseish
    anticlockwiseish
    shortest_street
    longest_street
    point_attract      # the single point-specific behaviour

DEFAULT BEHAVIOUR BY SHAPE
    area   -> random_walk
    line   -> straightish
    points -> point_attract

PREDEFINED SUPERCOLLIDER SOUNDS
    "kick", "snare", "hh", "sine", "bass", "harmonic"

Only variables named l1, l2, l3, ... are performed.
Delete/comment them all to see only the map.
"""

# Examples -- uncomment, edit, and Apply / save:





l1 = agent("area", [(0.45,0.15), (0.45,0.3), (0.2,0.45), (0.45,0.2)], 
    speed=50, 
    behaviour=random_walk, 
    sound="bass")

l2 = agent("line", [(0.08,0.75), (0.45,0.45), (0.90,0.68)], 
    speed=30, 
    behaviour=straightish, 
    sound="hh")

l3 = agent("points", [(0.22,0.35)], 
    speed=14, 
    sound="harmonic")

l4 = agent("line", [(0.9,0.4), (0.4, 0.9)], 
    speed=10, 
    behaviour=random_walk, 
    sound="kick")


# IMPLEMENT SOMETHING LIKE: 

l5 = place("hospitals", steps=16, direction="vertical", bpm=160)









