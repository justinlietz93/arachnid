"""Audit runner: compose the core scan with the optional analyses.

``scan_repo`` produces the LOC/router/schema/directory report. This runner
layers the test-coverage heuristic (2.5) and the opt-in AST scanners (2.6 -
2.8, 2.10) on top, lands their findings in ``report['extra_issues']``, and
recomputes the severity counts and pass flag so the report reflects the full
picture. The CLI and the orchestrator both go through here, so enrichment
happens in exactly one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..checks import run_checks
from .coverage import coverage_info
from .scanner import load_repo_config, recompute_summary, scan_repo, write_report


def prepare_config(
    root: Path,
    config_path: str | None = None,
    exclude: tuple[str, ...] = (),
) -> tuple[dict[str, Any], str | None]:
    """Load the audit config and fold in CLI ``--exclude`` globs (2.2).

    Returns ``(cfg, resolved_config_path)``. Used by both the ``audit``
    subcommand and the orchestrator so config handling lives in one place.
    """
    cfg, resolved = load_repo_config(root, config_path)
    if exclude:
        existing = list(cfg["scan"].get("exclude_globs") or [])
        cfg["scan"]["exclude_globs"] = existing + [g for g in exclude if g]
    return cfg, resolved


def run_audit(
    root: Path,
    cfg: dict[str, Any],
    *,
    config_path: str | None = None,
    shortcut: str | None = None,
    coverage: bool = True,
    events: bool = False,
    loops: bool = False,
    attrs: bool = False,
    extra_scanner: Path | None = None,
) -> dict[str, Any]:
    """Run the full audit and return the enriched report dict."""
    report = scan_repo(root, cfg, config_path=config_path, shortcut=shortcut)
    extra = report["extra_issues"]

    if coverage and cfg.get("coverage", {}).get("enabled", True):
        extra.extend(coverage_info(report, cfg))

    extra.extend(
        run_checks(
            root,
            report.get("scanned_files", []),
            cfg,
            events=events,
            loops=loops,
            attrs=attrs,
            extra_scanner=extra_scanner,
        )
    )

    recompute_summary(report)
    return report


def write_audit_report(root: Path, output_dir: str, report: dict[str, Any]) -> Path:
    """Persist the report as JSON; thin pass-through to the scanner writer."""
    return write_report(root, output_dir, report)
