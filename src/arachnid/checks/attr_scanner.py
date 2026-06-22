"""Enhancement 2.8: attribute-ownership mismatch.

In state, runtime, and loop files, a private field (matching ``^_``) that is
written through one object but read through a different one is a quiet source
of bugs: mutate ``self._cache`` but read ``self.engine._cache`` and the two
never meet. This scanner records, per field, the set of object expressions it
is assigned through and the set it is read through, then flags any field read
through an object it is never written through.

Object identity is the unparsed receiver expression: ``self``, ``self.engine``,
``ctx.state``. Comparing those sets catches state that lands on the wrong
instance. Findings are info severity; this is a smell detector, not a gate.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path, PurePosixPath
from typing import Any

from ..core.file_utils import rel_posix


def _receiver(node: ast.Attribute) -> str | None:
    """Stable string identity for the object an attribute hangs off."""
    try:
        return ast.unparse(node.value)
    except Exception:
        value = node.value
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            return value.attr
        return None


class _AttrVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, pattern: re.Pattern[str]) -> None:
        self.rel = rel
        self._pattern = pattern
        # field -> {receiver -> first lineno}
        self.writes: dict[str, dict[str, int]] = {}
        self.reads: dict[str, dict[str, int]] = {}

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        field = node.attr
        if self._pattern.search(field):
            recv = _receiver(node)
            if recv is not None:
                table = self.writes if isinstance(node.ctx, ast.Store) else self.reads
                table.setdefault(field, {}).setdefault(recv, node.lineno)
        self.generic_visit(node)


def scan_attrs(
    root: Path, scanned: list[str], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return info findings for read/write object mismatches on private fields."""
    checks = cfg.get("checks", {})
    name_tokens = {str(s).lower() for s in checks.get("attr_files", [])}
    if not name_tokens:
        return []
    pattern = re.compile(str(checks.get("attr_pattern", "^_")))

    findings: list[dict[str, Any]] = []
    for rel in scanned:
        p = PurePosixPath(rel)
        if p.suffix != ".py":
            continue
        stem = p.stem.lower()
        if not any(token in stem for token in name_tokens):
            continue
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        visitor = _AttrVisitor(rel_posix(Path(rel)), pattern)
        visitor.visit(tree)

        for field in sorted(set(visitor.writes) & set(visitor.reads)):
            write_recv = visitor.writes[field]
            read_recv = visitor.reads[field]
            orphan_reads = set(read_recv) - set(write_recv)
            if not orphan_reads:
                continue
            example = sorted(orphan_reads)[0]
            line = read_recv[example]
            findings.append(
                {
                    "severity": "info",
                    "rule": "attr_ownership_mismatch",
                    "path": f"{visitor.rel}:{line}",
                    "message": (
                        f"field '{field}' is read through {example!r} but only ever "
                        f"written through {sorted(write_recv)}; verify the state lives "
                        f"on the object you think it does."
                    ),
                    "field": field,
                    "read_through": sorted(read_recv),
                    "written_through": sorted(write_recv),
                }
            )
    return findings
