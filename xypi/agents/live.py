"""Hot-reload live.py performance scripts."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Callable

from xypi.agents.behaviours import BEHAVIOUR_REGISTRY
from xypi.agents.spec import LIVE_API, StreetAgentSpec


class _StubGeo:
    """Placeholder geometry for play() lines ignored during street-agent reload."""

    def to_geodataframe(self) -> "_StubGeo":
        return self


def _spatial_channel_stubs() -> dict:
    """No-op spatial helpers so unified live.py can reload for l1… street agents."""
    return {
        "play": lambda *args, **kwargs: None,
        "schools": lambda: [],
        "hospitals": lambda: [],
        "pois": lambda: {"schools": [], "hospitals": []},
        "schools_pattern": lambda *args, **kwargs: _StubGeo(),
        "hospitals_pattern": lambda *args, **kwargs: _StubGeo(),
        "pois_to_points": lambda *args, **kwargs: [],
        "list_channels": lambda: [],
        "clear_channels": lambda: None,
        "set_location": lambda *args, **kwargs: None,
        "list_locations": lambda: [],
        "point_graph": lambda *args, **kwargs: _StubGeo(),
        "multipoint": lambda *args, **kwargs: _StubGeo(),
        "to_geodataframe": lambda *args, **kwargs: _StubGeo(),
    }


def load_live_module(path: Path, module_name: str, source: str | None = None) -> ModuleType:
    source = path.read_text(encoding="utf-8") if source is None else source
    module = ModuleType(module_name)
    module.__file__ = str(path)
    module.__dict__.update(LIVE_API)
    module.__dict__.update(_spatial_channel_stubs())
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


class LiveProgram:
    def __init__(self, path: Path):
        self.path = path
        self.stamp = None
        self.failed_stamp = None
        self.module: ModuleType | None = None
        self.generation = 0
        self.reload(force=True)

    @staticmethod
    def _unit_defs(module: ModuleType) -> list[tuple[str, StreetAgentSpec]]:
        units = []
        for name, value in module.__dict__.items():
            if name.startswith("l") and name[1:].isdigit() and isinstance(value, StreetAgentSpec):
                units.append((name, value))
        units.sort(key=lambda item: int(item[0][1:]))
        return units

    def reload(self, force: bool = False) -> bool:
        try:
            st = self.path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
            if not force and (stamp == self.stamp or stamp == self.failed_stamp):
                return False
            module = load_live_module(self.path, "xypi_live_program")
            self._unit_defs(module)
            self.module = module
            self.stamp = stamp
            self.failed_stamp = None
            self.generation += 1
            print("[live] live.py reloaded")
            return True
        except Exception as exc:
            try:
                self.failed_stamp = (self.path.stat().st_mtime_ns, self.path.stat().st_size)
            except OSError:
                pass
            print(f"[live] live.py reload failed: {exc}")
            return False

    @classmethod
    def validate_source(cls, source: str, filename: str = "live.py") -> ModuleType:
        fake_path = Path(filename)
        module = load_live_module(fake_path, "xypi_live_candidate", source=source)
        cls._unit_defs(module)
        return module

    def source(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def unit_defs(self) -> list[tuple[str, StreetAgentSpec]]:
        return self._unit_defs(self.module) if self.module else []

    def resolve_behaviour(self, spec) -> tuple[str | None, Callable | None]:
        if spec is None:
            return None, None
        if callable(spec):
            return getattr(spec, "__name__", "<behaviour>"), spec
        if isinstance(spec, str):
            fn = getattr(self.module, spec, None) if self.module else None
            if not callable(fn):
                fn = BEHAVIOUR_REGISTRY.get(spec) or LIVE_API.get(spec)
            if not callable(fn):
                raise RuntimeError(f"Behaviour {spec!r} is not callable in live.py")
            return spec, fn
        raise TypeError("behaviour must be a function, a function name, or None")
