"""HTTP server bootstrap for experiment_4."""

from __future__ import annotations

from pathlib import Path

from xypi.experiments.experiment_4.help import get_session, help_payload
from xypi.experiments.shared.repl.server import serve_repl

EXP_DIR = Path(__file__).parent


def serve(host: str = "127.0.0.1", port: int = 8002) -> None:
    serve_repl(
        exp_dir=EXP_DIR,
        session=get_session(),
        help_payload=help_payload,
        host=host,
        port=port,
        label="Experiment 4 REPL",
        server_version="XYPIExperiment4/1.0",
    )
