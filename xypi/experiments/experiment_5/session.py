"""Experiment 5 REPL session — moving_points templates in namespace."""

from __future__ import annotations

from xypi.experiments.experiment_4.session import ReplSession
from xypi.experiments.experiment_5.templates import help_templates


class MovingPointsReplSession(ReplSession):
    def _seed_namespace(self) -> None:
        super()._seed_namespace()
        self.namespace["help_templates"] = help_templates
