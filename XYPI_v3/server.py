from __future__ import annotations

import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core import POI_FILTERS, XYPIEngine, list_locations


class XYPIHandler(BaseHTTPRequestHandler):
    engine: XYPIEngine
    root: Path

    def log_message(self, fmt: str, *args) -> None:
        request = str(args[0] if args else "")
        if "runtime/state.json" not in request and "runtime/map.json" not in request and "/api/state" not in request:
            super().log_message(fmt, *args)

    def _headers(self, content_type: str, length: int, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._headers("application/json; charset=utf-8", len(body), status)
        self.wfile.write(body)

    def _bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self._headers(content_type, len(body), status)
        self.wfile.write(body)

    def _body(self, max_size: int = 512_000) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > max_size:
            return b""
        return self.rfile.read(length)

    def do_OPTIONS(self) -> None:
        self._headers("text/plain; charset=utf-8", 0, 204)

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/locations":
            self._json({"locations": list_locations(), "active": self.engine.location_id})
            return
        if path == "/api/pois":
            self._json(self.engine.pois_payload())
            return
        if path == "/api/channels":
            self._json({"channels": self.engine.channel_payloads()})
            return
        if path == "/api/state":
            self._json(self.engine.state())
            return
        if path == "/api/transport":
            self._json(self.engine.transport_state())
            return
        if path == "/api/map":
            self._json(self.engine.map_state())
            return
        if path in ("/api/live", "/live.py"):
            self._bytes(self.engine.live_path.read_bytes(), "text/plain; charset=utf-8")
            return
        if path == "/api/help":
            self._json({
                "poi_categories": list(POI_FILTERS),
                "examples": [
                    "l1 = grid('hospitals', steps=8, bpm=120, direction='horizontal', movement='linear')",
                    "l2 = grid('schools', steps=12, bpm=145, direction='vertical', movement='backforth')",
                    "l3 = grid('restaurants', steps=16, bpm=130, direction='horizontal', movement='random')",
                    "l4 = agent('area', [(0.2,0.2),(0.8,0.2),(0.7,0.8)], speed=8, behaviour=random_walk, sound='bass')",
                ],
            })
            return
        if path.startswith("/runtime/"):
            candidate = (self.engine.runtime_dir / path.removeprefix("/runtime/")).resolve()
            if candidate.is_file() and candidate.is_relative_to(self.engine.runtime_dir.resolve()):
                self._bytes(candidate.read_bytes(), "application/json; charset=utf-8")
                return
        if path in ("/", "/index.html", "/UI.html"):
            candidate = self.root / "static" / "index.html"
        elif path.startswith("/static/"):
            candidate = (self.root / path.lstrip("/")).resolve()
            if not candidate.is_relative_to((self.root / "static").resolve()):
                self.send_error(403)
                return
        else:
            self.send_error(404)
            return
        if not candidate.is_file():
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(str(candidate))
        self._bytes(candidate.read_bytes(), mime or "application/octet-stream")

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/live":
            source = self._body(256_000).decode("utf-8")
            result = self.engine.update_live_source(source)
            self._json(result, 200 if result.get("ok") else 400)
            return
        if path == "/api/location":
            try:
                body = json.loads(self._body().decode("utf-8") or "{}")
                location = str(body.get("location", "")).strip()
                zoom = body.get("zoom")
                self.engine.request_location(location, float(zoom) if zoom is not None else None)
                self._json({"ok": True, "location": location})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return
        if path == "/api/reload":
            result = self.engine.reload_live(force=True)
            self._json(result, 200 if result.get("ok") else 400)
            return
        if path == "/api/transport":
            try:
                body = json.loads(self._body().decode("utf-8") or "{}")
                action = str(body.get("action", "")).strip().lower()
                if action == "play":
                    self._json(self.engine.play_grids())
                elif action == "stop":
                    self._json(self.engine.stop_grids())
                else:
                    self._json({"ok": False, "error": "transport action must be 'play' or 'stop'"}, 400)
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            return
        self.send_error(404)


def serve_ui(host: str = "127.0.0.1", port: int = 8080, location_id: str = "trento", zoom: float | None = None, live_path: Path | None = None, osc_host: str = "127.0.0.1", osc_port: int = 57120) -> None:
    root = Path(__file__).resolve().parent
    live_path = live_path or root / "live.py"
    engine = XYPIEngine(root, live_path, location_id, zoom, osc_host, osc_port)
    handler = type("BoundXYPIHandler", (XYPIHandler,), {"engine": engine, "root": root})
    ThreadingHTTPServer.allow_reuse_address = True
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        if exc.errno in (48, 98):
            raise SystemExit(f"Port {port} is already in use. Stop the other server or run: python run.py --port {port + 1}") from exc
        raise
    engine.start()
    print(f"XYPI at http://{host}:{port}/")
    print(f"Map: {location_id}; OSC: {osc_host}:{osc_port}")
    print("Open the URL above in the browser. Directly opening static/index.html is also supported on the default port.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        engine.stop()
        server.server_close()


if __name__ == "__main__":
    serve_ui()
