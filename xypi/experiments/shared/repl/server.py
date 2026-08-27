"""Shared REPL HTTP server for XYPI experiments."""

from __future__ import annotations

import json
import mimetypes
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def create_repl_handler(
    *,
    exp_dir: Path,
    session: Any,
    help_payload: Callable[[], dict[str, Any]],
    server_version: str = "XYPIRepl/1.0",
) -> type[BaseHTTPRequestHandler]:
    shared_viewer = exp_dir.parent / "shared" / "viewer"
    shared_repl = exp_dir.parent / "shared" / "repl"

    class ReplHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def _send_json(self, payload: dict, *, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _resolve_static(self, url_path: str) -> Path | None:
            if url_path in ("/", "/index.html"):
                return exp_dir / "index.html"
            if url_path.startswith("/shared/viewer/"):
                rel = url_path.removeprefix("/shared/viewer/")
                candidate = (shared_viewer / rel).resolve()
                if candidate.is_file() and candidate.is_relative_to(shared_viewer.resolve()):
                    return candidate
            if url_path.startswith("/shared/repl/"):
                rel = url_path.removeprefix("/shared/repl/")
                candidate = (shared_repl / rel).resolve()
                if candidate.is_file() and candidate.is_relative_to(shared_repl.resolve()):
                    return candidate
            rel = url_path.lstrip("/")
            candidate = (exp_dir / rel).resolve()
            if candidate.is_file() and candidate.is_relative_to(exp_dir.resolve()):
                return candidate
            return None

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/channels":
                self._send_json(
                    {
                        "channels": session.channel_names(),
                        "payloads": session.channel_payloads(),
                        "meta": session._channel_meta,
                    }
                )
                return

            if path == "/api/help":
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
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/exec":
                self.send_error(404)
                return

            body = self._read_json_body()
            code = str(body.get("code", "")).strip()
            if not code:
                self._send_json({"error": "Empty code"}, status=400)
                return

            result = session.execute(code)
            result["payloads"] = session.channel_payloads()
            self._send_json(result)

    ReplHandler.server_version = server_version
    return ReplHandler


def serve_repl(
    *,
    exp_dir: Path,
    session: Any,
    help_payload: Callable[[], dict[str, Any]],
    host: str = "127.0.0.1",
    port: int = 8002,
    label: str = "REPL",
    server_version: str = "XYPIRepl/1.0",
) -> None:
    handler = create_repl_handler(
        exp_dir=exp_dir,
        session=session,
        help_payload=help_payload,
        server_version=server_version,
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"{label} server at http://{host}:{port}/")
    print("Open the URL in your browser — Python editor left, map mixer right.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
