"""Enhancement 2.9: human-readable audit rendering and the fail decision.

The audit carries three issue streams (file, directory, and the extra stream
where coverage and the AST scanners land). This module folds them into one
ordered view grouped by severity, and answers the single operational question
the CLI needs: given this report and the caller's flags, does the build fail?

Severity policy (2.9): hard always fails. Warnings fail only when the caller
opts in with ``--fail-on-warning``. Info never fails; it is advisory.
"""

from __future__ import annotations

from typing import Any

# Print order and display labels. ``justified`` is shown last and only on
# request, since it documents an accepted exception rather than a problem.
_SEVERITY_ORDER = ("hard", "warning", "info", "justified")
_SEVERITY_LABEL = {
    "hard": "HARD",
    "warning": "WARNINGS",
    "info": "INFO",
    "justified": "JUSTIFIED EXCEPTIONS",
}


def all_issues(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Every issue across the file, directory, and extra streams."""
    return [
        *report.get("file_issues", []),
        *report.get("directory_issues", []),
        *report.get("extra_issues", []),
    ]


def _group_by_severity(
    issues: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {s: [] for s in _SEVERITY_ORDER}
    for item in issues:
        grouped.setdefault(item.get("severity", "info"), []).append(item)
    return grouped


def should_fail(report: dict[str, Any], *, fail_on_warning: bool = False) -> bool:
    """Decide the exit status from the summary counts (enhancement 2.9)."""
    summary = report.get("summary", {})
    if int(summary.get("hard_issue_count", 0)) > 0:
        return True
    if fail_on_warning and int(summary.get("warning_issue_count", 0)) > 0:
        return True
    return False


def render_audit_text(
    report: dict[str, Any],
    *,
    output_path: str | None = None,
    issue_limit: int | None = 20,
    show_justified: bool = False,
    fail_on_warning: bool = False,
) -> str:
    """Render the audit report as grouped, severity-ordered plain text."""
    summary = report.get("summary", {})
    out: list[str] = []
    w = out.append

    w("=" * 60)
    w(f" arachnid audit :: {report.get('root', '')}")
    w("=" * 60)
    if output_path:
        w(f" report                   {output_path}")
    if report.get("shortcut"):
        w(f" shortcut                 {report['shortcut']}")
    w(f" ignore mode              {report.get('ignore_mode', 'unknown')}")
    w(f" scanned text files       {summary.get('scanned_text_file_count', 0)}")
    w(f" directories audited      {summary.get('directory_count', 0)}")
    w(f" hard issues              {summary.get('hard_issue_count', 0)}")
    w(f" warnings                 {summary.get('warning_issue_count', 0)}")
    w(f" info                     {summary.get('info_issue_count', 0)}")
    justified = int(summary.get("justified_exception_count", 0))
    if justified:
        w(f" justified exceptions     {justified}")
    verdict = "FAIL" if should_fail(report, fail_on_warning=fail_on_warning) else "PASS"
    w(f" result                   {verdict}")

    grouped = _group_by_severity(all_issues(report))
    for severity in _SEVERITY_ORDER:
        if severity == "justified" and not show_justified:
            continue
        items = grouped.get(severity, [])
        if not items:
            continue
        w("")
        w("-" * 60)
        w(f" {_SEVERITY_LABEL[severity]} ({len(items)})")
        w("-" * 60)
        shown = items if issue_limit is None else items[:issue_limit]
        for item in shown:
            path = item.get("path", "")
            rule = item.get("rule", "")
            message = item.get("message", "")
            w(f" [{rule}] {path}")
            w(f"     {message}")
        hidden = len(items) - len(shown)
        if hidden > 0:
            w(f" ... +{hidden} more")

    return "\n".join(out)
