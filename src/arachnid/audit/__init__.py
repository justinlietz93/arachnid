"""Repository standards audit: LOC limits, directory hygiene, router and
schema-model rules, plus the coverage heuristic and AST scanners layered on by
the runner.
"""

from __future__ import annotations

from .coverage import coverage_info
from .defaults import DEFAULT_CONFIG, TEXT_EXTENSIONS
from .formatter import all_issues, render_audit_text, should_fail
from .runner import prepare_config, run_audit, write_audit_report
from .scanner import (
    classify_file,
    directory_audit,
    file_list,
    load_repo_config,
    recompute_summary,
    scan_repo,
    write_report,
)
from .standards import resolve_loc_limits

__all__ = [
    "DEFAULT_CONFIG",
    "TEXT_EXTENSIONS",
    "all_issues",
    "classify_file",
    "coverage_info",
    "directory_audit",
    "file_list",
    "load_repo_config",
    "prepare_config",
    "recompute_summary",
    "render_audit_text",
    "resolve_loc_limits",
    "run_audit",
    "scan_repo",
    "should_fail",
    "write_audit_report",
    "write_report",
]
