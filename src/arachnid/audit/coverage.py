"""Enhancement 2.5: test-coverage heuristic.

Source files above a line threshold that have no matching test file are
flagged ``untested_module`` at info severity. This never fails a build on its
own (info is advisory, see enhancement 2.9); it is a nudge, not a gate.

The check is deliberately structural and cheap. It does not run tests or read
coverage data. It asks one question: for a substantial source module, does a
file named like its test exist anywhere in the repository? A ``parser.py`` of
600 lines with no ``test_parser.py`` is the smell this surfaces.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

# Files that are never expected to carry their own unit test.
_EXEMPT_STEMS = frozenset({"__init__", "__main__", "conftest", "setup", "_version"})


def _is_test_path(rel: str, tests_dir: str) -> bool:
    """True when ``rel`` is itself test code (so it needs no test of its own)."""
    parts = PurePosixPath(rel).parts
    if tests_dir and tests_dir in parts:
        return True
    stem = PurePosixPath(rel).stem
    return stem.startswith("test_") or stem.endswith("_test")


def _test_basenames(scanned: list[str]) -> set[str]:
    """Collect the basenames of every test file in the repository."""
    names: set[str] = set()
    for rel in scanned:
        p = PurePosixPath(rel)
        if p.suffix != ".py":
            continue
        stem = p.stem
        if stem.startswith("test_") or stem.endswith("_test"):
            names.add(p.name)
    return names


def coverage_info(report: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return info-level ``untested_module`` findings for the scanned repo.

    Reads the file reports that ``scan_repo`` already produced, so no file is
    read twice. A finding is emitted when a ``.py`` source module is larger
    than ``coverage.min_loc`` and no file named ``test_<stem>.py`` or
    ``<stem>_test.py`` exists anywhere in the repository.
    """
    coverage_cfg = cfg.get("coverage", {})
    if not coverage_cfg.get("enabled", True):
        return []

    min_loc = int(coverage_cfg.get("min_loc", 200))
    tests_dir = str(coverage_cfg.get("tests_dir", "tests"))

    scanned: list[str] = report.get("scanned_files", [])
    existing_tests = _test_basenames(scanned)

    findings: list[dict[str, Any]] = []
    for entry in report.get("files", []):
        if entry.get("skipped"):
            continue
        rel = entry.get("path", "")
        p = PurePosixPath(rel)
        if p.suffix != ".py":
            continue
        if p.stem in _EXEMPT_STEMS:
            continue
        if _is_test_path(rel, tests_dir):
            continue
        loc = int(entry.get("loc", 0))
        if loc <= min_loc:
            continue

        wanted = {f"test_{p.stem}.py", f"{p.stem}_test.py"}
        if wanted & existing_tests:
            continue

        findings.append(
            {
                "severity": "info",
                "rule": "untested_module",
                "path": rel,
                "actual": loc,
                "limit": min_loc,
                "message": (
                    f"{rel} has {loc} LOC and no matching test file "
                    f"(expected one of: test_{p.stem}.py, {p.stem}_test.py)."
                ),
                "expected_test_any_of": sorted(wanted),
            }
        )
    return findings
