"""Unified REPL session — spatial channels + map location context."""

from __future__ import annotations

from typing import Any

from xypi.agents.engine import AgentMapEngine
from xypi.agents.spec import pois_to_points
from xypi.experiments.experiment_4.session import ReplSession
from xypi.map.locations import list_locations
from xypi.spatial.moving_agent import moving_agent
from xypi.spatial.patterns import multipoint, point_graph, to_geodataframe


class UnifiedSession(ReplSession):
    """ReplSession extended with active map location and OSM POI helpers."""

    def __init__(self, engine: AgentMapEngine | None = None) -> None:
        self.engine = engine
        self._spatial_playback = None
        super().__init__()

    def bind_playback(self, playback) -> None:
        self._spatial_playback = playback

    def sync_playback(self) -> None:
        if self._spatial_playback is not None:
            self._spatial_playback.sync(self)

    def bind_engine(self, engine: AgentMapEngine) -> None:
        self.engine = engine
        self.namespace["set_location"] = self.set_location
        self.namespace["list_locations"] = list_locations
        self.namespace["schools"] = self.schools
        self.namespace["hospitals"] = self.hospitals
        self.namespace["pois"] = self.pois
        self.namespace["schools_pattern"] = self.schools_pattern
        self.namespace["hospitals_pattern"] = self.hospitals_pattern

    def _seed_namespace(self) -> None:
        super()._seed_namespace()
        self.namespace["moving_agent"] = moving_agent
        self.namespace["pois_to_points"] = pois_to_points
        self.namespace["list_locations"] = list_locations
        self.namespace["set_location"] = self.set_location
        self.namespace["schools"] = self.schools
        self.namespace["hospitals"] = self.hospitals
        self.namespace["pois"] = self.pois
        self.namespace["schools_pattern"] = self.schools_pattern
        self.namespace["hospitals_pattern"] = self.hospitals_pattern

    def set_location(self, location_id: str, zoom: float | None = None) -> str:
        if self.engine is None:
            raise RuntimeError("Map engine is not available")
        self.engine.request_location(location_id, zoom)
        name = self.engine.map_cfg.get("name", location_id)
        print(f"▶ Loading location {name!r}…")
        return location_id

    def schools(self) -> list[dict[str, Any]]:
        if self.engine is None:
            return []
        return list(self.engine.schools)

    def hospitals(self) -> list[dict[str, Any]]:
        if self.engine is None:
            return []
        return list(self.engine.hospitals)

    def pois(self) -> dict[str, list[dict[str, Any]]]:
        if self.engine is None:
            return {"schools": [], "hospitals": []}
        return self.engine.pois_payload()

    def schools_pattern(self, name: str = "schools", max_points: int = 24):
        """Build a MultiPoint GeoDataFrame from OSM schools."""
        pts = pois_to_points(self.schools(), max_points=max_points)
        if not pts:
            raise ValueError("No schools loaded for the active location yet")
        return multipoint(pts).to_geodataframe()

    def hospitals_pattern(self, name: str = "hospitals", max_points: int = 24):
        pts = pois_to_points(self.hospitals(), max_points=max_points)
        if not pts:
            raise ValueError("No hospitals loaded for the active location yet")
        return multipoint(pts).to_geodataframe()
