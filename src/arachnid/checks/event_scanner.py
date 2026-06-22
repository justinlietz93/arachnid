"""Enhancement 2.6: event-bus producer/consumer balance.

Walks the AST of the repository's event-plumbing files (``bus.py``,
``events.py``, ``adc.py``, and friends) and pairs the events that are produced
against the events that are consumed. An event published but never handled is
dead output; an event handled but never published is a dangling listener.
Both are surfaced at info severity.

The match is name-based and static. A call like ``bus.publish("tick", payload)``
records the event ``"tick"`` as produced; ``bus.subscribe("tick", handler)``
records it as consumed. When the event identity is a symbol rather than a
literal (``emit(TickEvent)``), the symbol name is used so producers and
consumers that share a constant still line up.
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Any

from ..core.file_utils import rel_posix


def _event_name(call: ast.Call) -> str | None:
    """Best-effort static identity of the event a call refers to.

    Prefers the first positional argument: a string literal becomes its value,
    a bare name or attribute becomes its trailing identifier. Returns ``None``
    when nothing nameable is present, so anonymous dispatch is simply skipped
    rather than guessed at.
    """
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.Name):
            return arg.id
        if isinstance(arg, ast.Attribute):
            return arg.attr
        # Only the first positional argument is meaningful as an identity.
        break
    return None


class _EventVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, producers: set[str], consumers: set[str]) -> None:
        self.rel = rel
        self._producers = producers
        self._consumers = consumers
        # name -> (rel_path, lineno) of first sighting, per role.
        self.produced: dict[str, tuple[str, int]] = {}
        self.consumed: dict[str, tuple[str, int]] = {}

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 (ast API)
        func = node.func
        method = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else None
        )
        if method is not None:
            if method in self._producers:
                name = _event_name(node)
                if name and name not in self.produced:
                    self.produced[name] = (self.rel, node.lineno)
            elif method in self._consumers:
                name = _event_name(node)
                if name and name not in self.consumed:
                    self.consumed[name] = (self.rel, node.lineno)
        self.generic_visit(node)


def scan_events(
    root: Path, scanned: list[str], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return info findings for unbalanced event production/consumption."""
    checks = cfg.get("checks", {})
    event_stems = {str(s) for s in checks.get("event_files", [])}
    if not event_stems:
        return []
    producers = {str(s) for s in checks.get("event_producers", [])}
    consumers = {str(s) for s in checks.get("event_consumers", [])}

    produced: dict[str, tuple[str, int]] = {}
    consumed: dict[str, tuple[str, int]] = {}

    for rel in scanned:
        p = PurePosixPath(rel)
        if p.suffix != ".py" or p.stem not in event_stems:
            continue
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        visitor = _EventVisitor(rel_posix(Path(rel)), producers, consumers)
        visitor.visit(tree)
        for name, loc in visitor.produced.items():
            produced.setdefault(name, loc)
        for name, loc in visitor.consumed.items():
            consumed.setdefault(name, loc)

    findings: list[dict[str, Any]] = []
    for name in sorted(set(produced) - set(consumed)):
        rel, line = produced[name]
        findings.append(
            {
                "severity": "info",
                "rule": "event_produced_never_consumed",
                "path": f"{rel}:{line}",
                "message": (
                    f"event '{name}' is produced but no consumer subscribes to it."
                ),
                "event": name,
            }
        )
    for name in sorted(set(consumed) - set(produced)):
        rel, line = consumed[name]
        findings.append(
            {
                "severity": "info",
                "rule": "event_consumed_never_produced",
                "path": f"{rel}:{line}",
                "message": (
                    f"event '{name}' has a consumer but is never produced."
                ),
                "event": name,
            }
        )
    return findings
