from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.file_utils import glob_match
from .defaults import DEFAULT_CONFIG
from .standards import resolve_loc_limits


def deep_copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deep_copy_json(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_config(out[key], value)
        else:
            out[key] = value
    return out


def normalize_config_path(root: Path, explicit_config: str | None = None) -> Path:
    root = root.resolve()
    if explicit_config:
        config_path = Path(explicit_config).expanduser()
        if not config_path.is_absolute():
            config_path = root / config_path
        return config_path
    return root / ".repo-standards.json"


def load_json_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_repo_config(
    root: Path, explicit_config: str | None = None
) -> tuple[dict[str, Any], str | None]:
    config_path = normalize_config_path(root, explicit_config)
    if not config_path.exists():
        return deep_copy_json(DEFAULT_CONFIG), None
    return merge_config(DEFAULT_CONFIG, load_json_config(config_path)), str(config_path.resolve())


from .discovery import (
    always_ignored,
    file_list,
    git_files,
    gitignore_rules,
    ignored_by_gitignore,
    is_text_file,
    manual_files,
    matches,
    normalize_path,
    path_tokens,
    rule_matches,
)


def has_size_justification(lines: list[str], cfg: dict[str, Any]) -> bool:
    markers = cfg["schema_models"]["justification_markers"]
    limit = int(cfg["schema_models"]["justification_search_first_lines"])
    return any(marker in line for line in lines[:limit] for marker in markers)


def non_import_logic_lines(lines: list[str]) -> int:
    count = 0
    in_doc = False
    triple = (chr(34) * 3, chr(39) * 3)
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        marks = sum(stripped.count(x) for x in triple)
        if marks:
            if marks % 2:
                in_doc = not in_doc
            continue
        if in_doc:
            continue
        if stripped.startswith(("import ", "from ", "__all__", "__version__")):
            continue
        count += 1
    return count


def issue(
    severity: str, rule: str, path: str, actual: int, limit: int, message: str
) -> dict[str, Any]:
    return {
        "severity": severity,
        "rule": rule,
        "path": path,
        "actual": actual,
        "limit": limit,
        "message": message,
    }


def classify_file(root: Path, item: str, cfg: dict[str, Any]) -> dict[str, Any]:
    path = root / item
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    loc = len(lines)
    is_router = bool(cfg["routers"]["enabled"]) and matches(item, cfg["routers"]["patterns"])
    is_schema = matches(item, cfg["schema_models"]["patterns"])
    justified = has_size_justification(lines, cfg)
    problems: list[dict[str, Any]] = []

    # Enhancement 2.1: limits resolved per file extension. For ``.py`` the
    # defaults match the legacy flat limits, so router and schema-model
    # behavior below is unchanged; documentation and config get their own
    # generous ceilings.
    warn_limit, base_hard = resolve_loc_limits(path.suffix, cfg)
    hard = min(base_hard, int(cfg["loc"]["router_hard"])) if is_router else base_hard

    if is_schema and loc > base_hard:
        needs = int(cfg["loc"]["schema_model_requires_justification_above"])
        schema_hard = int(cfg["loc"]["schema_model_hard_with_justification"])
        if loc > schema_hard:
            problems.append(
                issue(
                    "hard",
                    "schema_model_over_justified_limit",
                    item,
                    loc,
                    schema_hard,
                    f"{item} has {loc} LOC. Schema/model hard limit is {schema_hard}.",
                )
            )
        elif not justified:
            data = issue(
                "hard",
                "schema_model_missing_size_justification",
                item,
                loc,
                needs,
                f"{item} has {loc} LOC. Schema/model files above {needs} LOC need justification.",
            )
            data["required_marker_any_of"] = cfg["schema_models"]["justification_markers"]
            problems.append(data)
        else:
            problems.append(
                {
                    "severity": "justified",
                    "rule": "schema_model_size_exception",
                    "path": item,
                    "actual": loc,
                    "message": f"{item} has {loc} LOC with justification.",
                }
            )
    elif loc > hard:
        problems.append(
            issue(
                "hard",
                "router_over_limit" if is_router else "file_over_limit",
                item,
                loc,
                hard,
                f"{item} has {loc} LOC. Limit is {hard}.",
            )
        )
    elif loc > warn_limit:
        problems.append(
            issue(
                "warning",
                "file_over_warning",
                item,
                loc,
                warn_limit,
                f"{item} has {loc} LOC. Warning is {warn_limit}.",
            )
        )

    router_report = None
    if is_router:
        non_import = non_import_logic_lines(lines)
        sibling = path.with_suffix("")
        sibling_rel = normalize_path(sibling.relative_to(root))
        router_report = {
            "path": item,
            "loc": loc,
            "non_import_logic_lines": non_import,
            "expected_sibling_folder": sibling_rel,
            "expected_sibling_folder_exists": sibling.is_dir(),
        }
        logic_limit = int(cfg["routers"]["logic_warning_lines"])
        folder_threshold = int(cfg["routers"]["expect_sibling_folder_above_loc"])
        if non_import > logic_limit:
            problems.append(
                issue(
                    "warning",
                    "router_contains_logic",
                    item,
                    non_import,
                    logic_limit,
                    f"{item} has {non_import} non-import/non-comment lines. Router files should mainly delegate.",
                )
            )
        if loc > folder_threshold and not sibling.is_dir():
            data = issue(
                "warning",
                "router_missing_sibling_folder",
                item,
                loc,
                folder_threshold,
                f"{item} is router-like and above {folder_threshold} LOC but has no sibling folder.",
            )
            data["expected_sibling_folder"] = sibling_rel
            problems.append(data)

    return {
        "path": item,
        "loc": loc,
        "is_router_file": is_router,
        "is_schema_model_file": is_schema,
        "has_size_justification": justified,
        "issues": problems,
        "router_report": router_report,
    }


def directory_audit(
    scanned: list[str], cfg: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files: dict[str, set[str]] = {".": set()}
    children: dict[str, set[str]] = {".": set()}
    for item in scanned:
        p = Path(item)
        parent = "." if str(p.parent) == "." else normalize_path(p.parent)
        files.setdefault(parent, set()).add(p.name)
        children.setdefault(parent, set())
        parts = p.parts[:-1]
        if parts:
            children["."].add(parts[0])
        for i in range(len(parts)):
            here = "/".join(parts[: i + 1])
            files.setdefault(here, set())
            children.setdefault(here, set())
            if i + 1 < len(parts):
                children[here].add(parts[i + 1])

    reports: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for directory in sorted(set(files) | set(children), key=lambda x: (x.count("/"), x)):
        file_count = len(files.get(directory, set()))
        child_count = len(children.get(directory, set()))
        leaf = child_count == 0
        warning = int(
            cfg["directories"]["leaf_warning_files"]
            if leaf
            else cfg["directories"]["warning_files"]
        )
        hard = int(
            cfg["directories"]["leaf_hard_files"]
            if leaf
            else cfg["directories"]["hard_files"]
        )
        issues: list[dict[str, Any]] = []
        if file_count > hard:
            issues.append(
                {
                    "severity": "hard",
                    "rule": "directory_over_limit",
                    "path": directory,
                    "actual": file_count,
                    "limit": hard,
                    "is_leaf_directory": leaf,
                    "message": f"{directory} contains {file_count} direct files. Limit is {hard}.",
                }
            )
        elif file_count > warning:
            issues.append(
                {
                    "severity": "warning",
                    "rule": "directory_over_warning",
                    "path": directory,
                    "actual": file_count,
                    "limit": warning,
                    "is_leaf_directory": leaf,
                    "message": f"{directory} contains {file_count} direct files. Warning is {warning}.",
                }
            )
        reports.append(
            {
                "path": directory,
                "direct_file_count": file_count,
                "direct_child_folder_count": child_count,
                "is_leaf_directory": leaf,
                "warning_limit": warning,
                "hard_limit": hard,
                "issues": issues,
            }
        )
        problems.extend(issues)
    return reports, problems


def recompute_summary(report: dict[str, Any]) -> None:
    """Recompute issue counts and the pass flag over every issue stream.

    Called after the runner appends coverage and AST-scanner findings so the
    counts reflect the full set. ``pass`` depends only on hard issues
    (enhancement 2.9); info issues never fail the build, warnings fail only
    when the caller opts in.
    """
    streams = (
        report.get("file_issues", []),
        report.get("directory_issues", []),
        report.get("extra_issues", []),
    )
    hard = warning = info = justified = 0
    for stream in streams:
        for x in stream:
            sev = x.get("severity")
            if sev == "hard":
                hard += 1
            elif sev == "warning":
                warning += 1
            elif sev == "info":
                info += 1
            elif sev == "justified":
                justified += 1
    summary = report["summary"]
    summary["hard_issue_count"] = hard
    summary["warning_issue_count"] = warning
    summary["info_issue_count"] = info
    summary["justified_exception_count"] = justified
    summary["pass"] = hard == 0


def scan_repo(
    root: Path,
    cfg: dict[str, Any],
    config_path: str | None = None,
    shortcut: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    candidates, ignore_mode, ignored = file_list(root, cfg)

    # Enhancement 2.2: honor --exclude globs in the audit too (the graph
    # already did). Excluded candidates move to the ignored list.
    exclude_globs = [str(g) for g in (cfg["scan"].get("exclude_globs") or []) if g]
    if exclude_globs:
        kept: list[str] = []
        for item in candidates:
            if glob_match(item, exclude_globs):
                ignored.append(item)
            else:
                kept.append(item)
        candidates = kept
        ignored = sorted(set(ignored))

    files: list[dict[str, Any]] = []
    file_issues: list[dict[str, Any]] = []
    routers: list[dict[str, Any]] = []
    scanned: list[str] = []

    for item in candidates:
        path = root / item
        if not path.is_file():
            continue
        if not is_text_file(path, cfg):
            files.append(
                {"path": item, "skipped": True, "reason": "non_text_or_extension_excluded"}
            )
            continue
        scanned.append(item)
        report = classify_file(root, item, cfg)
        files.append(report)
        file_issues.extend(report["issues"])
        if report["router_report"]:
            routers.append(report["router_report"])

    dirs, dir_issues = directory_audit(scanned, cfg)
    issues = file_issues + dir_issues
    hard_count = sum(x["severity"] == "hard" for x in issues)
    warning_count = sum(x["severity"] == "warning" for x in issues)
    info_count = sum(x["severity"] == "info" for x in issues)
    justified_count = sum(x["severity"] == "justified" for x in issues)

    return {
        "schema": "arachnid-audit/1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "shortcut": shortcut,
        "root": str(root),
        "config_path": config_path,
        "ignore_mode": ignore_mode,
        "standards": cfg,
        "summary": {
            "candidate_file_count": len(candidates),
            "scanned_text_file_count": len(scanned),
            "skipped_file_count": len(files) - len(scanned),
            "directory_count": len(dirs),
            "router_file_count": len(routers),
            "hard_issue_count": hard_count,
            "warning_issue_count": warning_count,
            "info_issue_count": info_count,
            "justified_exception_count": justified_count,
            "pass": hard_count == 0,
        },
        "file_issues": file_issues,
        "directory_issues": dir_issues,
        # Coverage (2.5) and AST scanner (2.6 - 2.8) findings land here.
        "extra_issues": [],
        "router_reports": routers,
        "files": files,
        "directories": dirs,
        "scanned_files": scanned,
        "ignored_paths_sample": ignored[:200],
    }


def write_report(root: Path, output_dir: str, report: dict[str, Any]) -> Path:
    root = root.expanduser().resolve()
    out_dir = Path(output_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"arachnid_audit_report_{stamp}.json"
    output = out_dir / name
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output
