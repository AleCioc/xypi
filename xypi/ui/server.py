"""Unified XYPI HTTP server — map agents, spatial channels, live editor."""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from xypi.agents.engine import AgentMapEngine
from xypi.map.locations import list_locations
from xypi.ui.channel_examples import CHANNEL_EXAMPLES
from xypi.ui.channel_playback import SpatialChannelPlayback
from xypi.ui.live_runtime import apply_live_script
from xypi.ui.session import UnifiedSession


def create_handler(
    *,
    ui_dir: Path,
    engine: AgentMapEngine,
    session: UnifiedSession,
    help_payload: Callable[[], dict[str, Any]] | None = None,
) -> type[BaseHTTPRequestHandler]:
    shared_viewer = ui_dir.parent / "experiments" / "shared" / "viewer"
    static_dir = ui_dir / "static"

    class UnifiedHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            request = str(args[0] if args else "")
            if "runtime/state.json" not in request and "runtime/map.json" not in request:
                return super().log_message(fmt, *args)

        def _send_json(self, payload: dict, *, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, data: bytes, content_type: str, *, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self, max_size: int = 512_000) -> bytes:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > max_size:
                return b""
            return self.rfile.read(length)

        def _resolve_static(self, url_path: str) -> Path | None:
            if url_path in ("/", "/index.html"):
                return static_dir / "index.html"
            if url_path.startswith("/static/"):
                rel = url_path.removeprefix("/static/")
                candidate = (static_dir / rel).resolve()
                if candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
                    return candidate
            if url_path.startswith("/shared/viewer/"):
                rel = url_path.removeprefix("/shared/viewer/")
                candidate = (shared_viewer / rel).resolve()
                if candidate.is_file() and candidate.is_relative_to(shared_viewer.resolve()):
                    return candidate
            if url_path.startswith("/runtime/"):
                rel = url_path.removeprefix("/runtime/")
                candidate = (engine.runtime_dir / rel).resolve()
                if candidate.is_file() and candidate.is_relative_to(engine.runtime_dir.resolve()):
                    return candidate
            if url_path.startswith("/receivers/"):
                rel = url_path.removeprefix("/receivers/")
                candidate = (ui_dir / "receivers" / rel).resolve()
                if candidate.is_file() and candidate.is_relative_to((ui_dir / "receivers").resolve()):
                    return candidate
            return None

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/locations":
                self._send_json({"locations": list_locations(), "active": engine.location_id})
                return

            if path == "/api/pois":
                self._send_json(engine.pois_payload())
                return

            if path == "/api/live":
                raw = engine.live.source().encode("utf-8")
                self._send_bytes(raw, "text/plain; charset=utf-8")
                return

            if path == "/api/examples":
                self._send_json({"examples": CHANNEL_EXAMPLES})
                return

            if path == "/api/channels":
                self._send_json(
                    {
                        "channels": session.channel_names(),
                        "payloads": session.browser_payloads(),
                        "meta": session._channel_meta,
                    }
                )
                return

            if help_payload and path == "/api/help":
                self._send_json(help_payload())
                return

            if path == "/api/reset":
                session.reset()
                self._send_json({"ok": True, "channels": [], "payloads": []})
                return

            static = self._resolve_static(path)
            if static is None:
                self.send_error(404)
                return
            content = static.read_bytes()
            mime, _ = mimetypes.guess_type(str(static))
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(content)))
            if path.startswith("/shared/viewer/") or path.startswith("/static/"):
                self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/location":
                try:
                    body = json.loads(self._read_body().decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._send_json({"ok": False, "error": "invalid JSON"}, status=400)
                    return
                location_id = str(body.get("location", "")).strip()
                zoom = body.get("zoom")
                try:
                    engine.request_location(location_id, float(zoom) if zoom is not None else None)
                    self._send_json({"ok": True, "location": location_id})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, status=400)
                return

            if path == "/api/live":
                source = self._read_body(max_size=256_000).decode("utf-8")
                result = apply_live_script(source, session, engine)
                self._send_json(result, status=200 if result.get("ok") else 400)
                return

            if path == "/api/exec":
                try:
                    body = json.loads(self._read_body().decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._send_json({"error": "invalid JSON"}, status=400)
                    return
                code = str(body.get("code", "")).strip()
                if not code:
                    self._send_json({"error": "Empty code"}, status=400)
                    return
                result = session.execute(code)
                result["payloads"] = session.channel_payloads()
                self._send_json(result)
                return

            self.send_error(404)

    return UnifiedHandler


def serve_ui(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    location_id: str = "trento",
    zoom: float | None = None,
    live_path: Path | None = None,
    osc_host: str = "127.0.0.1",
    osc_port: int = 57120,
) -> None:
    ui_dir = Path(__file__).resolve().parent
    data_dir = ui_dir
    default_live = ui_dir / "default_live.py"
    if live_path is None:
        live_path = ui_dir / "live.py"
    if not live_path.exists() or not live_path.read_text(encoding="utf-8").strip():
        source = default_live.read_text(encoding="utf-8")
        # Skip module docstring for the on-disk editor copy.
        lines = source.splitlines()
        if lines and lines[0].startswith('"""'):
            for i, line in enumerate(lines[1:], 1):
                if '"""' in line:
                    source = "\n".join(lines[i + 1 :]).lstrip("\n")
                    break
        live_path.write_text(source, encoding="utf-8")

    engine = AgentMapEngine(
        data_dir=data_dir,
        live_path=live_path,
        location_id=location_id,
        zoom=zoom,
        osc_host=osc_host,
        osc_port=osc_port,
    )
    session = UnifiedSession(engine)
    session.bind_engine(engine)
    spatial_playback = SpatialChannelPlayback(host=osc_host, port=osc_port)
    session.bind_playback(spatial_playback)

    def help_payload() -> dict[str, Any]:
        return {
            "intro": "XYPI — map agents + spatial channels",
            "welcome_lines": [
                "Select a location (Trento · Taranto · Antwerp)",
                "One editor: play(...) for spatial channels + l1… moving_agent for streets",
                "play(..., output='browser'|'osc'|'both') — browser WebAudio / SuperCollider / both",
                "Apply then ▶ Play for browser audio; load supercollider_receiver.scd for OSC",
            ],
            "play": session.help_play(),
            "examples": [
                "schools()  # OSM schools for active location",
                "play(schools_pattern(), name='schools', time_flow='x')",
                "nodes = pois_to_points(schools())[:8]",
                "play(point_graph(nodes, []).to_geodataframe(), name='poi_pts')",
                "list_channels()",
            ],
            "templates": CHANNEL_EXAMPLES,
            "channel_examples": CHANNEL_EXAMPLES,
            "locations": list_locations(),
        }

    handler = create_handler(ui_dir=ui_dir, engine=engine, session=session, help_payload=help_payload)
    os.chdir(ui_dir)
    engine.start()
    try:
        ThreadingHTTPServer.allow_reuse_address = True
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        if exc.errno in (48, 98):  # macOS / Linux "address already in use"
            raise SystemExit(
                f"Port {port} is already in use. Stop the other XYPI server or run:\n"
                f"  python xypi/run.py --port {port + 1}"
            ) from exc
        raise
    url = f"http://{host}:{port}/"
    print(f"XYPI unified server at {url}")
    print(f"  Location: {location_id} (change in UI)")
    print(f"  SuperCollider: load xypi/ui/receivers/supercollider_receiver.scd")
    print(f"  Sonic Pi: load xypi/ui/receivers/sonicpi_receiver.spi (spatial channels via OSC)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        engine.running = False
        spatial_playback.stop()
        server.server_close()
