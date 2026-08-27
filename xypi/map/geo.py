"""Shared geo helpers for map / street graph code."""

from __future__ import annotations

import math


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def turn_deg(a, b, c) -> float:
    ax, ay = a[1] - b[1], a[0] - b[0]
    cx, cy = c[1] - b[1], c[0] - b[0]
    na = max(math.hypot(ax, ay), 1e-12)
    nc = max(math.hypot(cx, cy), 1e-12)
    cosv = max(-1.0, min(1.0, (ax * cx + ay * cy) / (na * nc)))
    return abs(180.0 - math.degrees(math.acos(cosv)))
