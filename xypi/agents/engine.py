"""Map-backed street agent engine — simulation + runtime snapshots."""

from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Callable

from xypi.agents.behaviours import Context
from xypi.agents.layer import (
    configure_layer_graph,
    layer_from_spec,
    layer_signature,
    random_colour,
)
from xypi.agents.live import LiveProgram
from xypi.agents.osc import CornerOscSender
from xypi.agents.runtime import StreetAgent
from xypi.agents.spec import StreetAgentSpec
from xypi.map.graph import StreetGraph, edge_position
from xypi.map.locations import preset_map
from xypi.map.overpass import download_hospitals, download_schools, load_street_graph
from xypi.map.view import MapView


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


class AgentMapEngine:
    """One active location, street graph, live-coded agents, optional OSC output."""

    def __init__(
        self,
        *,
        data_dir: Path,
        live_path: Path,
        location_id: str = "trento",
        zoom: float | None = None,
        osc_host: str = "127.0.0.1",
        osc_port: int = 57120,
        osc_path: str = "/xypi/corner",
        on_corner: Callable[[StreetAgent, dict], None] | None = None,
    ):
        self.data_dir = data_dir
        self.cache_dir = data_dir / "cache"
        self.runtime_dir = data_dir / "runtime"
        self.live_path = live_path
        self.location_id = location_id
        self.zoom = zoom
        self.map_cfg = preset_map(location_id, zoom)
        self.view = MapView.from_bbox(self.map_cfg["bbox"])
        self.osc = CornerOscSender(osc_host, osc_port, osc_path)
        self.on_corner = on_corner
        self.live = LiveProgram(live_path)
        self.graph: StreetGraph | None = None
        self.schools: list[dict] = []
        self.hospitals: list[dict] = []
        self.layers: list = []
        self.agents: list[StreetAgent] = []
        self.colours: dict[str, str] = {}
        self.status = "loading map"
        self.error: str | None = None
        self.live_status = "ready"
        self.live_error: str | None = None
        self.lock = threading.RLock()
        self.running = True
        self._reload_requested = False
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.map_json_path = self.runtime_dir / "map.json"
        self.state_json_path = self.runtime_dir / "state.json"
        self._publish_map()
        self._publish_state()

    def start(self) -> None:
        threading.Thread(target=self._load_map, daemon=True).start()
        threading.Thread(target=self._simulation_loop, daemon=True).start()

    def request_location(self, location_id: str, zoom: float | None = None) -> None:
        with self.lock:
            self.location_id = location_id
            self.zoom = zoom
            self.map_cfg = preset_map(location_id, zoom)
            self.view = MapView.from_bbox(self.map_cfg["bbox"])
            self.status = "loading map"
            self.error = None
            self.graph = None
            self.schools = []
            self.hospitals = []
            self.layers = []
            self.agents = []
        self._reload_requested = True
        threading.Thread(target=self._load_map, daemon=True).start()

    def _load_map(self) -> None:
        try:
            graph = load_street_graph(self.map_cfg, self.cache_dir)
            with self.lock:
                self.graph = graph
                self.status = "map ready"
                self.error = None
            self._publish_map()
            self._sync_live_program(force=True)
            self._publish_state()
            print(
                f"[map] {self.map_cfg['name']}: {len(graph.nodes)} nodes, "
                f"{len(graph.edges)} street segments"
            )

            schools = download_schools(self.map_cfg, self.cache_dir)
            hospitals = download_hospitals(self.map_cfg, self.cache_dir)
            with self.lock:
                self.schools = schools
                self.hospitals = hospitals
            self._publish_map()
            self._publish_state()
            if schools or hospitals:
                print(f"[map] POIs: {len(schools)} schools, {len(hospitals)} hospitals")
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.status = "error"
            print(f"[map] {exc}")
            self._publish_map()
            self._publish_state()

    def _sync_live_program(self, force: bool = False) -> None:
        changed = self.live.reload() if not force else True
        if not changed and not force:
            return
        with self.lock:
            graph = self.graph
            if graph is None:
                return
            old_layers = {layer.name: layer for layer in self.layers}
            old_agents = {agent.layer.name: agent for agent in self.agents}

        try:
            defs = self.live.unit_defs()
            names = [name for name, _ in defs]
            new_layers = []
            new_agents = []
            for name, spec in defs:
                colour = self.colours.setdefault(name, random_colour())
                candidate = layer_from_spec(name, spec, colour)
                old = old_layers.get(name)
                if old is not None and layer_signature(old) == layer_signature(candidate):
                    layer = old
                    agent_obj = old_agents[name]
                else:
                    layer = candidate
                    configure_layer_graph(graph, layer)
                    if not layer.allowed_nodes:
                        raise RuntimeError(f"{name!r} does not intersect a usable street route")
                    geom = layer.shape_geometry()
                    anchor = (geom.centroid.x, geom.centroid.y) if layer.shape == "area" else layer.coords[0]
                    start = graph.nearest_node(anchor, layer.allowed_nodes)
                    x, y = graph.xy(start)
                    agent_obj = StreetAgent(name=name, layer=layer, node=start, x=x, y=y)

                speed = spec.speed_mps
                behaviour_name, behaviour_fn = self.live.resolve_behaviour(spec.behaviour)
                agent_obj.speed_mps = speed
                agent_obj.behaviour = behaviour_name
                agent_obj.behaviour_fn = behaviour_fn
                agent_obj.sound = spec.sound
                agent_obj.output = spec.output
                new_layers.append(layer)
                new_agents.append(agent_obj)

            with self.lock:
                self.layers = new_layers
                self.agents = new_agents
                self.error = None
                self.live_status = "applied"
                self.live_error = None
        except Exception as exc:
            with self.lock:
                self.live_status = "rejected"
                self.live_error = str(exc)
            print(f"[live] program update rejected: {exc}")

    def _set_agent_status(self, agent: StreetAgent, status: str) -> None:
        if agent.status != status:
            agent.status = status

    def _choose_edge(self, agent: StreetAgent, now: float) -> None:
        assert self.graph is not None
        neighbours = tuple(n for n in self.graph.adj.get(agent.node, {}) if n in agent.layer.allowed_nodes)
        if not neighbours:
            self._set_agent_status(agent, "blocked: no connected street segment inside shape")
            return
        if agent.behaviour_fn is None:
            self._set_agent_status(agent, "waiting for behaviour")
            return
        ctx = Context(
            agent.node,
            agent.previous_node,
            neighbours,
            self.graph,
            agent.layer.shape,
            tuple(agent.layer.coords),
        )
        try:
            target = agent.behaviour_fn(ctx)
            if target not in neighbours:
                raise ValueError(f"behaviour returned unavailable node {target}")
        except Exception as exc:
            self._set_agent_status(agent, f"behaviour error: {exc}")
            return

        edge = self.graph.adj[agent.node][target]
        agent.target_node = target
        agent.edge = edge
        agent.street_started = now
        agent.edge_last_update = now
        agent.edge_progress_m = 0.0
        agent.edge_duration = edge.length_m / max(agent.speed_mps, 0.05)
        self._set_agent_status(
            agent,
            f"moving with {agent.behaviour}: {edge.length_m:.1f} m at {agent.speed_mps:.2f} m/s",
        )

    def _arrive(self, agent: StreetAgent, now: float) -> None:
        assert self.graph is not None and agent.target_node is not None
        agent.previous_node = agent.node
        agent.node = agent.target_node
        agent.target_node = None
        agent.edge = None
        actual_duration = max(now - agent.street_started, 0.0)
        agent.edge_progress_m = 0.0
        agent.edge_last_update = now
        x, y = self.graph.xy(agent.node)
        agent.x, agent.y = x, y
        event = {
            "time": time.time(),
            "sound": agent.sound,
            "output": agent.output,
            "x_timbre": x,
            "y_pitch": y,
            "duration": actual_duration,
            "mover": agent.name,
        }
        agent.last_event = event
        agent.status = f"arrived at corner; previous street {actual_duration:.2f} s"
        if agent.output == "osc":
            self.osc.send_corner(agent.name, agent.sound, y, x, actual_duration)
        if self.on_corner:
            self.on_corner(agent, event)
        print(f"[corner] {agent.name:12s} sound={agent.sound:8s} pitch={y:.3f} timbre={x:.3f}")

    def _simulation_loop(self) -> None:
        last_publish = 0.0
        while self.running:
            if self._reload_requested:
                self._reload_requested = False
            self._sync_live_program()
            now = time.monotonic()
            with self.lock:
                graph = self.graph
                agents = list(self.agents)
            if graph is not None:
                for agent in agents:
                    if agent.target_node is None:
                        self._choose_edge(agent, now)
                    if agent.target_node is None or agent.edge is None:
                        continue
                    dt = max(0.0, now - agent.edge_last_update)
                    agent.edge_last_update = now
                    agent.edge_progress_m += agent.speed_mps * dt
                    t = agent.edge_progress_m / max(agent.edge.length_m, 1e-9)
                    if t >= 1.0:
                        self._arrive(agent, now)
                    else:
                        agent.edge_duration = (agent.edge.length_m - agent.edge_progress_m) / max(
                            agent.speed_mps, 0.05
                        )
                        agent.x, agent.y = edge_position(graph, agent.edge, agent.node, agent.target_node, t)
            if now - last_publish >= 0.1:
                self._publish_state()
                last_publish = now
            time.sleep(1 / 30)

    def update_live_source(self, source: str) -> tuple[bool, str]:
        if len(source.encode("utf-8")) > 256_000:
            return False, "live.py is too large for the browser editor"
        try:
            self.live.validate_source(source, str(self.live_path))
            tmp = self.live_path.with_suffix(".py.browser.tmp")
            tmp.write_text(source, encoding="utf-8")
            os.replace(tmp, self.live_path)
            with self.lock:
                self.live_status = "saved"
                self.live_error = None
            return True, "saved; engine will hot-reload it"
        except Exception as exc:
            with self.lock:
                self.live_status = "editor error"
                self.live_error = str(exc)
            return False, str(exc)

    def map_state(self) -> dict:
        with self.lock:
            pois = {"schools": self.schools, "hospitals": self.hospitals}
            if self.graph is None:
                return {"ready": False, "streets": {"nodes": {}, "edges": []}, "pois": pois}
            return {"ready": True, "streets": self.graph.public_state(), "pois": pois}

    def state(self) -> dict:
        with self.lock:
            graph = self.graph
            return {
                "status": self.status,
                "error": self.error,
                "location": {
                    "id": self.location_id,
                    "name": self.map_cfg.get("name", "map"),
                    "bbox": self.map_cfg["bbox"],
                    "center": self.map_cfg.get("center"),
                    "zoom": self.map_cfg.get("zoom"),
                    "street_segments": len(graph.edges) if graph else 0,
                    "corner_nodes": len(graph.nodes) if graph else 0,
                    "schools": len(self.schools),
                    "hospitals": len(self.hospitals),
                },
                "layers": [layer.public_state() for layer in self.layers],
                "agents": [agent.public_state() for agent in self.agents],
                "live": {"status": self.live_status, "error": self.live_error},
                "osc": {"host": self.osc.addr[0], "port": self.osc.addr[1], "path": self.osc.path},
            }

    def _publish_map(self) -> None:
        try:
            write_json_atomic(self.map_json_path, self.map_state())
        except Exception as exc:
            print(f"[viewer] failed to write map snapshot: {exc}")

    def _publish_state(self) -> None:
        try:
            write_json_atomic(self.state_json_path, self.state())
        except Exception as exc:
            print(f"[viewer] failed to write state snapshot: {exc}")

    def pois_payload(self) -> dict:
        with self.lock:
            return {"schools": self.schools, "hospitals": self.hospitals}
