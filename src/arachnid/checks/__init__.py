"""Optional AST scanners (enhancements 2.6 - 2.8, 2.10).

Each scanner is opt-in via a CLI flag and contributes findings to the audit's
extra-issue stream. ``run_checks`` is the single entry point the audit runner
calls; it fans out to whichever scanners the caller enabled and returns the
merged findings in a stable order (events, loops, attrs, then plugin).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .attr_scanner import scan_attrs
from .event_scanner import scan_events
from .loop_scanner import scan_loops
from .plugin_loader import run_extra_scanner

__all__ = [
    "run_checks",
    "scan_attrs",
    "scan_events",
    "scan_loops",
    "run_extra_scanner",
]


def run_checks(
    root: Path,
    scanned: list[str],
    cfg: dict[str, Any],
    *,
    events: bool = False,
    loops: bool = False,
    attrs: bool = False,
    extra_scanner: Path | None = None,
) -> list[dict[str, Any]]:
    """Run the enabled AST scanners and return their merged findings."""
    findings: list[dict[str, Any]] = []
    if events:
        findings.extend(scan_events(root, scanned, cfg))
    if loops:
        findings.extend(scan_loops(root, scanned, cfg))
    if attrs:
        findings.extend(scan_attrs(root, scanned, cfg))
    if extra_scanner is not None:
        findings.extend(run_extra_scanner(root, scanned, Path(extra_scanner)))
    return findings
