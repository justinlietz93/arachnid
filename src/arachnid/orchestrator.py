"""Scan orchestrator: run graph, audit, and snapshot into one output dir.

``arachnid scan`` is the headline command. It drives all three subsystems and
lays their artifacts out under ``ROOT/.arachnid_scans/<repo>_<timestamp>/``,
matching the layout of the original bash wrapper:

    repo_graph.json            graph, machine-readable
    repo_graph_report.txt      graph, human-readable
    repo_audit/                audit JSON + text report
    <repo>_docs.txt            docs snapshot
    summary.txt                run summary
    MANIFEST.txt               file inventory

Status aggregation: a graph or audit failure, optional cycle/warning gates, or
a scanner error sets a non-zero status. A missing docs directory is a warning,
never a failure.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from . import audit as audit_pkg
from .audit import render_audit_text, run_audit, should_fail, write_audit_report
from .graph import GraphRun, render_report, run_graph, to_json
from .snapshot import SnapshotResult, build_snapshot, write_snapshot


@dataclass
class ScanResult:
    out_dir: Path
    status: int
    graph: Optional[GraphRun] = None
    audit: Optional[Dict[str, Any]] = None
    snapshot: Optional[SnapshotResult] = None
    artifacts: Dict[str, Path] = field(default_factory=dict)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def run_scan(
    root: Path,
    *,
    out_dir: Optional[Path] = None,
    do_graph: bool = True,
    do_audit: bool = True,
    do_snap: bool = True,
    shortcut: Optional[str] = None,
    # graph options
    exclude: Sequence[str] = (),
    venv: Optional[Path] = None,
    sys_paths: Sequence[Path] = (),
    no_auto_src: bool = False,
    no_auto_venv: bool = False,
    granularity: str = "module",
    include_external: bool = False,
    package_root: Optional[str] = None,
    auto_package_root: bool = True,
    jobs: int = 1,
    top: int = 25,
    full_report: bool = False,
    fail_on_cycles: bool = False,
    # audit options
    config_path: Optional[str] = None,
    coverage: bool = True,
    events: bool = False,
    loops: bool = False,
    attrs: bool = False,
    extra_scanner: Optional[Path] = None,
    fail_on_warning: bool = False,
    # snapshot options
    docs_subdir: str = "docs",
    # io
    log=sys.stderr,
    quiet: bool = False,
) -> ScanResult:
    """Run the enabled subsystems and write every artifact under the out dir."""
    root = Path(root).expanduser().resolve()
    repo_name = root.name or "repo"

    if out_dir is None:
        out_dir = root / ".arachnid_scans" / f"{repo_name}_{_timestamp()}"
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir.resolve()

    if not quiet:
        print(f"arachnid: root   {root}", file=log)
        print(f"arachnid: output {out_dir}", file=log)

    status = 0
    artifacts: Dict[str, Path] = {}
    graph_run: Optional[GraphRun] = None
    audit_report: Optional[Dict[str, Any]] = None
    snap_result: Optional[SnapshotResult] = None

    if do_graph:
        try:
            graph_run = run_graph(
                root,
                exclude=exclude,
                sys_paths=sys_paths,
                venv=venv,
                no_auto_src=no_auto_src,
                no_auto_venv=no_auto_venv,
                granularity=granularity,
                include_external=include_external,
                package_root=package_root,
                auto_package_root=auto_package_root,
                jobs=jobs,
                top=top,
                log=log,
                quiet=quiet,
            )
            graph_json = out_dir / "repo_graph.json"
            graph_json.write_text(
                to_json(graph_run.G, graph_run.summary), encoding="utf-8"
            )
            graph_report = out_dir / "repo_graph_report.txt"
            graph_report.write_text(
                render_report(
                    graph_run.summary,
                    str(root),
                    graph_run.files_scanned,
                    top=top,
                    full=full_report,
                ),
                encoding="utf-8",
            )
            artifacts["graph_json"] = graph_json
            artifacts["graph_report"] = graph_report
            if not quiet:
                print(f"arachnid: graph  {graph_json}", file=log)
            if fail_on_cycles and not graph_run.summary.get("is_dag", True):
                status = 1
        except Exception as exc:  # keep the scan going; record the failure
            (out_dir / "repo_graph.stderr.txt").write_text(
                f"graph failed: {exc}\n", encoding="utf-8"
            )
            print(f"arachnid: graph failed; see repo_graph.stderr.txt ({exc})", file=log)
            status = 1

    if do_audit:
        try:
            cfg, resolved_cfg = audit_pkg.prepare_config(
                root, config_path, tuple(exclude)
            )
            audit_report = run_audit(
                root,
                cfg,
                config_path=resolved_cfg,
                shortcut=shortcut,
                coverage=coverage,
                events=events,
                loops=loops,
                attrs=attrs,
                extra_scanner=extra_scanner,
            )
            audit_dir = out_dir / "repo_audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            json_path = write_audit_report(root, str(audit_dir), audit_report)
            text_path = audit_dir / "repo_audit_report.txt"
            text_path.write_text(
                render_audit_text(
                    audit_report,
                    output_path=str(json_path),
                    issue_limit=None,
                    fail_on_warning=fail_on_warning,
                ),
                encoding="utf-8",
            )
            artifacts["audit_dir"] = audit_dir
            artifacts["audit_json"] = json_path
            artifacts["audit_report"] = text_path
            if not quiet:
                print(f"arachnid: audit  {audit_dir}", file=log)
            if should_fail(audit_report, fail_on_warning=fail_on_warning):
                status = 1
        except Exception as exc:
            (out_dir / "repo_audit.stderr.txt").write_text(
                f"audit failed: {exc}\n", encoding="utf-8"
            )
            print(f"arachnid: audit failed; see repo_audit.stderr.txt ({exc})", file=log)
            status = 1

    if do_snap:
        snap_file = out_dir / f"{repo_name}_docs.txt"
        snap_result = build_snapshot(root, docs_subdir=docs_subdir)
        write_snapshot(snap_result, snap_file)
        artifacts["snapshot"] = snap_file
        if not snap_result.docs_exists and not quiet:
            print(
                f"arachnid: no docs directory at {snap_result.docs_dir}; wrote "
                f"{snap_result.file_count} discovered docs",
                file=log,
            )
        elif not quiet:
            print(f"arachnid: docs   {snap_file}", file=log)

    summary_file = _write_summary(
        out_dir, root, status, do_graph, do_audit, do_snap, artifacts
    )
    manifest_file = _write_manifest(out_dir, root)
    artifacts["summary"] = summary_file
    artifacts["manifest"] = manifest_file
    if not quiet:
        print(f"arachnid: summary {summary_file}", file=log)
        print(f"arachnid: manifest {manifest_file}", file=log)

    return ScanResult(
        out_dir=out_dir,
        status=status,
        graph=graph_run,
        audit=audit_report,
        snapshot=snap_result,
        artifacts=artifacts,
    )


def _write_summary(
    out_dir: Path,
    root: Path,
    status: int,
    do_graph: bool,
    do_audit: bool,
    do_snap: bool,
    artifacts: Dict[str, Path],
) -> Path:
    lines = [
        "Arachnid scan summary",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Root: {root}",
        f"Output: {out_dir}",
        f"Status: {status}",
        "",
        "Artifacts:",
    ]
    if do_graph and "graph_json" in artifacts:
        lines.append(f"  Graph JSON: {artifacts['graph_json']}")
        lines.append(f"  Graph report: {artifacts['graph_report']}")
    if do_audit and "audit_dir" in artifacts:
        lines.append(f"  Audit directory: {artifacts['audit_dir']}")
    if do_snap and "snapshot" in artifacts:
        lines.append(f"  Docs snapshot: {artifacts['snapshot']}")
    summary_file = out_dir / "summary.txt"
    summary_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_file


def _write_manifest(out_dir: Path, root: Path) -> Path:
    files = sorted(p for p in out_dir.rglob("*") if p.is_file())
    lines = [
        "Arachnid manifest",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Root: {root}",
        f"Output: {out_dir}",
        "",
    ]
    lines.extend(str(p) for p in files)
    manifest_file = out_dir / "MANIFEST.txt"
    manifest_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_file
