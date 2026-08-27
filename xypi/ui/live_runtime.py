"""Apply unified live.py — street agents + spatial channels in one script."""

from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Any

from xypi.agents.engine import AgentMapEngine
from xypi.agents.live import LiveProgram
from xypi.agents.spec import LIVE_API, StreetAgentSpec
from xypi.ui.session import UnifiedSession


def _street_defs(namespace: dict[str, Any]) -> list[tuple[str, StreetAgentSpec]]:
    units = []
    for name, value in namespace.items():
        if name.startswith("l") and name[1:].isdigit() and isinstance(value, StreetAgentSpec):
            units.append((name, value))
    units.sort(key=lambda item: int(item[0][1:]))
    return units


def apply_live_script(
    source: str,
    session: UnifiedSession,
    engine: AgentMapEngine,
) -> dict[str, Any]:
    """Validate, save, and run one live.py containing play() and l1… street agents."""
    if len(source.encode("utf-8")) > 256_000:
        return {"ok": False, "error": "live.py is too large for the browser editor"}
    if not source.strip():
        return {"ok": False, "error": "live.py is empty — reload default or paste your script"}

    session.clear()
    namespace: dict[str, Any] = {}
    namespace.update(LIVE_API)
    namespace.update(session.namespace)

    try:
        compiled = compile(source, str(engine.live_path), "exec")
        exec(compiled, namespace)
        _street_defs(namespace)
    except Exception:
        err = traceback.format_exc()
        with engine.lock:
            engine.live_status = "rejected"
            engine.live_error = err
        return {"ok": False, "error": err, "payloads": [], "channels": []}

    try:
        tmp = engine.live_path.with_suffix(".py.browser.tmp")
        tmp.write_text(source, encoding="utf-8")
        os.replace(tmp, engine.live_path)
        engine.live.reload(force=True)
        with engine.lock:
            engine.live_status = "applied"
            engine.live_error = None
        engine._sync_live_program(force=True)
        session.sync_playback()
    except Exception as exc:
        with engine.lock:
            engine.live_status = "rejected"
            engine.live_error = str(exc)
        return {
            "ok": False,
            "error": str(exc),
            "payloads": session.channel_payloads(),
            "channels": session.channel_names(),
        }

    return {
        "ok": True,
        "message": "applied",
        "payloads": session.browser_payloads(),
        "channels": session.channel_names(),
        "meta": dict(session._channel_meta),
        "browser_channels": session.browser_channel_names(),
        "stdout": "",
        "error": None,
    }
