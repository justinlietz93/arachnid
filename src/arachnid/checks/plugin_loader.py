"""Enhancement 2.10: user-supplied AST scanners.

A team can drop in a Python file that defines ``visit(node)`` or
``visit(node, path)`` and have it run against every AST node of every scanned
``.py`` file, with its findings merged into the audit's extra-issue stream.
This is the escape hatch for project-specific rules that do not belong in the
core scanners.

Contract for the plugin:
    * Define a top-level callable ``visit``.
    * It receives each ``ast`` node (and the file's repo-relative path when it
      declares a second parameter).
    * It returns nothing, a single finding dict, or a list of finding dicts.
      Each finding may set ``severity``/``rule``/``message``/``path``; sensible
      defaults are filled in, and ``path`` is stamped with the current file and
      line when the plugin leaves it blank.

A plugin that fails to load, or raises while visiting, stops the run with a
precise message. A broken rule should be loud, not silent.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from ..core.file_utils import rel_posix

_ALLOWED_SEVERITIES = {"hard", "warning", "info"}


def _load_visit(script: Path) -> tuple[Callable[..., Any], bool]:
    """Import ``script`` and return its ``visit`` callable + arity flag.

    The boolean is True when ``visit`` should be called with ``(node, path)``
    and False when it takes only ``(node)``.
    """
    script = script.expanduser().resolve()
    if not script.is_file():
        raise RuntimeError(f"extra scanner not found: {script}")

    spec = importlib.util.spec_from_file_location(f"arachnid_plugin_{script.stem}", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load extra scanner: {script}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # the plugin's own import-time failure
        raise RuntimeError(f"extra scanner {script} failed to import: {exc}") from exc

    visit = getattr(module, "visit", None)
    if not callable(visit):
        raise RuntimeError(f"extra scanner {script} must define a callable visit()")

    wants_path = _accepts_two_args(visit)
    return visit, wants_path


def _accepts_two_args(func: Callable[..., Any]) -> bool:
    """True when ``func`` can take a second positional (path) argument."""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    positional = 0
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            return True
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional += 1
    return positional >= 2


def _normalize(
    finding: Any, rel: str, node: ast.AST, script_name: str
) -> dict[str, Any] | None:
    if not isinstance(finding, dict):
        return None
    severity = str(finding.get("severity", "info"))
    if severity not in _ALLOWED_SEVERITIES:
        severity = "info"
    line = getattr(node, "lineno", None)
    path = finding.get("path")
    if not path:
        path = f"{rel}:{line}" if line is not None else rel
    result = dict(finding)
    result["severity"] = severity
    result["rule"] = str(finding.get("rule", f"extra:{script_name}"))
    result["path"] = path
    result.setdefault("message", "(extra scanner finding)")
    return result


def run_extra_scanner(
    root: Path, scanned: list[str], script: Path
) -> list[dict[str, Any]]:
    """Run a user plugin over every node of every scanned ``.py`` file."""
    visit, wants_path = _load_visit(script)
    script_name = Path(script).stem

    findings: list[dict[str, Any]] = []
    for rel in scanned:
        p = PurePosixPath(rel)
        if p.suffix != ".py":
            continue
        rel_norm = rel_posix(Path(rel))
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            try:
                result = visit(node, rel_norm) if wants_path else visit(node)
            except Exception as exc:
                line = getattr(node, "lineno", "?")
                raise RuntimeError(
                    f"extra scanner {script_name} raised at {rel_norm}:{line}: {exc}"
                ) from exc
            if result is None:
                continue
            items = result if isinstance(result, list) else [result]
            for item in items:
                normalized = _normalize(item, rel_norm, node, script_name)
                if normalized is not None:
                    findings.append(normalized)
    return findings
