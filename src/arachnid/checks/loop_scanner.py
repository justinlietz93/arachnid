"""Enhancement 2.7: redundant work inside hot loops.

In the files that tend to hold a program's main cadence (``*loop*.py``,
``*main*.py``), an expensive call repeated inside a single loop body is a
classic recompute smell: counting, scanning, traversing, or recomputing
components/entropy/metrics on every pass when once would do. This scanner
flags a loop when a call whose name matches the redundancy pattern appears
more than once in the same loop body.

Loop scoping is exact. A call is attributed to the nearest enclosing loop, so
a call inside a nested loop counts for that inner loop, not the outer one. The
check never crosses a loop boundary when tallying.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from ..core.file_utils import glob_match, rel_posix

_LOOP_TYPES = (ast.For, ast.While, ast.AsyncFor)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _direct_calls(loop: ast.AST) -> list[ast.Call]:
    """Calls lexically inside ``loop`` but not inside a deeper nested loop."""
    found: list[ast.Call] = []

    def walk(node: ast.AST, *, at_root: bool) -> None:
        for child in ast.iter_child_nodes(node):
            # A nested loop owns its own calls; do not descend into it here.
            if isinstance(child, _LOOP_TYPES) and not at_root:
                continue
            if isinstance(child, ast.Call):
                found.append(child)
            walk(child, at_root=False)

    # The loop node itself is the root; its body children are walked, but the
    # iterator/test of the loop is fair game too (it runs every pass).
    walk(loop, at_root=True)
    return found


class _LoopVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, pattern: re.Pattern[str]) -> None:
        self.rel = rel
        self._pattern = pattern
        self.findings: list[dict[str, Any]] = []

    def _check_loop(self, node: ast.AST) -> None:
        names = [
            name
            for call in _direct_calls(node)
            if (name := _call_name(call)) and self._pattern.search(name)
        ]
        counts = Counter(names)
        for name, count in sorted(counts.items()):
            if count > 1:
                self.findings.append(
                    {
                        "severity": "warning",
                        "rule": "redundant_call_in_loop",
                        "path": f"{self.rel}:{node.lineno}",
                        "actual": count,
                        "limit": 1,
                        "message": (
                            f"'{name}()' is called {count} times inside the loop "
                            f"at line {node.lineno}; hoist or cache it if the result "
                            f"is loop-invariant."
                        ),
                        "call": name,
                    }
                )

    def visit_For(self, node: ast.For) -> None:  # noqa: N802
        self._check_loop(node)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802
        self._check_loop(node)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        self._check_loop(node)
        self.generic_visit(node)


def scan_loops(
    root: Path, scanned: list[str], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return warning findings for redundant calls in hot loops."""
    checks = cfg.get("checks", {})
    globs = [str(g) for g in checks.get("loop_file_globs", [])]
    if not globs:
        return []
    pattern = re.compile(str(checks.get("loop_redundant_pattern", "")))

    findings: list[dict[str, Any]] = []
    for rel in scanned:
        p = PurePosixPath(rel)
        if p.suffix != ".py" or not glob_match(rel, globs):
            continue
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        visitor = _LoopVisitor(rel_posix(Path(rel)), pattern)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings
