"""Unified command line for arachnid."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import shortcuts
from ._version import __version__

# Cosmetic warning threshold for a single mermaid diagram.
MERMAID_NODE_WARN = 400

_GRAPH_DEFAULT_OUT = {
    "html": "arachnid-graph.html",
    "mermaid": "arachnid-graph.md",
    "json": "arachnid-graph.json",
    "dot": "arachnid-graph.dot",
}


# --------------------------------------------------------------------------- #
# parser construction
# --------------------------------------------------------------------------- #
def _add_target(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="directory or saved shortcut label (default: current directory)",
    )
    parser.add_argument(
        "-r",
        "--subpath",
        default=None,
        metavar="REL",
        help="relative path appended to the resolved target",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="quiet progress output")


def _add_graph_opts(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-x", "--exclude", action="append", default=[], metavar="GLOB",
        help="exclude paths matching GLOB (relative posix path or filename); repeatable",
    )
    parser.add_argument(
        "--venv", default=None, metavar="DIR",
        help="virtualenv of the target project (default: auto-detect .venv/venv)",
    )
    parser.add_argument(
        "--sys-path", action="append", default=[], metavar="DIR",
        help="extra directory for jedi's sys.path; repeatable",
    )
    parser.add_argument("--no-auto-src", action="store_true",
                        help="do not auto-add nested src-layout directories")
    parser.add_argument("--no-auto-venv", action="store_true",
                        help="do not auto-detect the project's virtualenv")
    parser.add_argument(
        "-g", "--granularity", choices=["module", "package"], default="module",
        help="node granularity: per file or per top-level directory",
    )
    parser.add_argument("-e", "--include-external", action="store_true",
                        help="add stdlib/third-party packages as graph nodes")
    parser.add_argument("-j", "--jobs", type=int, default=1,
                        help="parallel scan processes (default 1)")
    parser.add_argument("--top", type=int, default=10,
                        help="rows per report section (default 10)")
    parser.add_argument(
        "--package-root", default=None, metavar="NAME",
        help="treat imports under NAME as the project's own package (2.3); "
             "auto-detected from pyproject/setup.py when omitted",
    )
    parser.add_argument("--no-auto-package-root", action="store_true",
                        help="disable package-root auto-detection")
    parser.add_argument("--full", action="store_true", help="no truncation in the report")


def _add_audit_opts(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None, metavar="FILE",
                        help="repo standards config (default: ROOT/.repo-standards.json)")
    parser.add_argument("--print-issues", type=int, default=20, metavar="N",
                        help="max issue lines per severity in text output (default 20)")
    parser.add_argument("--fail-on-warning", action="store_true",
                        help="exit 1 on warnings too (2.9); default fails only on hard")
    parser.add_argument("--no-coverage", action="store_true",
                        help="skip the test-coverage heuristic (2.5)")
    parser.add_argument("--scan-events", action="store_true",
                        help="run the event producer/consumer scanner (2.6)")
    parser.add_argument("--scan-loops", action="store_true",
                        help="run the hot-loop redundancy scanner (2.7)")
    parser.add_argument("--scan-attrs", action="store_true",
                        help="run the attribute-ownership scanner (2.8)")
    parser.add_argument("--extra-scanner", default=None, metavar="FILE",
                        help="path to a user AST scanner defining visit() (2.10)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arachnid",
        description="Repository graphing, auditing, and docs snapshotting.",
    )
    parser.add_argument("--version", action="version", version=f"arachnid {__version__}")
    sub = parser.add_subparsers(dest="command")

    # scan ----------------------------------------------------------------- #
    p_scan = sub.add_parser("scan", help="graph + audit + docs snapshot")
    _add_target(p_scan)
    _add_graph_opts(p_scan)
    _add_audit_opts(p_scan)
    p_scan.add_argument("--out", default=None, metavar="DIR",
                        help="output directory (default: ROOT/.arachnid_scans/<repo>_<ts>)")
    p_scan.add_argument("--docs", default="docs", metavar="PATH",
                        help="docs directory to snapshot (default: ROOT/docs)")
    p_scan.add_argument("--fail-on-cycles", action="store_true",
                        help="exit 1 if circular dependencies exist")
    p_scan.add_argument("--no-graph", action="store_true", help="skip the graph")
    p_scan.add_argument("--no-audit", action="store_true", help="skip the audit")
    p_scan.add_argument("--no-snap", action="store_true", help="skip the snapshot")
    p_scan.add_argument("--format", choices=["json", "text"], default="json",
                        help="stdout summary format (default json; artifacts are always written)")

    # graph ---------------------------------------------------------------- #
    p_graph = sub.add_parser("graph", help="dependency graph only")
    _add_target(p_graph)
    _add_graph_opts(p_graph)
    p_graph.add_argument("-o", "--output",
                         choices=["report", "html", "mermaid", "json", "dot", "none"],
                         default="report",
                         help="export format; html is the interactive viewer (default: report)")
    p_graph.add_argument("--out", default=None, metavar="FILE",
                         help="write the export to FILE instead of stdout")
    p_graph.add_argument("-a", "--analyze", action="store_true",
                         help="also print the graph health report")
    p_graph.add_argument("--edge-labels", action="store_true",
                         help="label mermaid edges with imported names")
    p_graph.add_argument("--direction", choices=["LR", "RL", "TB", "BT"], default="LR",
                         help="mermaid flow direction (default LR)")
    p_graph.add_argument("--template", default=None, metavar="FILE",
                         help="custom Jinja2 template for mermaid output")
    p_graph.add_argument("--raw", action="store_true", help="omit the mermaid fence")
    p_graph.add_argument("--fail-on-cycles", action="store_true",
                         help="exit 1 if circular dependencies exist")

    # audit ---------------------------------------------------------------- #
    p_audit = sub.add_parser("audit", help="standards audit only")
    _add_target(p_audit)
    _add_audit_opts(p_audit)
    p_audit.add_argument("-x", "--exclude", action="append", default=[], metavar="GLOB",
                         help="exclude paths matching GLOB; repeatable")
    p_audit.add_argument("--out", default=None, metavar="DIR",
                         help="write the JSON report into DIR")
    p_audit.add_argument("--format", choices=["text", "json"], default="text",
                         help="stdout format (default text)")

    # snap ----------------------------------------------------------------- #
    p_snap = sub.add_parser("snap", help="docs snapshot only")
    _add_target(p_snap)
    p_snap.add_argument("--docs", default="docs", metavar="PATH",
                        help="docs directory to snapshot (default: ROOT/docs)")
    p_snap.add_argument("--out", default=None, metavar="FILE",
                        help="output file (default: ./<repo>_docs.txt; '-' for stdout)")

    # add / list / rm ------------------------------------------------------ #
    p_add = sub.add_parser("add", help="save a repository shortcut")
    p_add.add_argument("path", help="directory the shortcut points at")
    p_add.add_argument("label", help="shortcut name")

    sub.add_parser("list", aliases=["ls"], help="list saved shortcuts")

    p_rm = sub.add_parser("rm", aliases=["remove"], help="remove a shortcut")
    p_rm.add_argument("label", help="shortcut name to remove")

    return parser


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _progress_printer(quiet: bool):
    if quiet:
        return None
    stream = sys.stderr
    is_tty = stream.isatty()

    def cb(i: int, total: int, path: Path) -> None:
        if is_tty:
            stream.write(f"\rscanning {i}/{total}  {path.name[:48]:<48}")
            if i == total:
                stream.write("\n")
            stream.flush()
        elif i == total or i % 25 == 0:
            stream.write(f"scanning {i}/{total}\n")
            stream.flush()

    return cb


def _resolve(args: argparse.Namespace) -> Path:
    """Resolve the target (directory or shortcut) plus optional subpath."""
    return shortcuts.resolve_target(args.target, args.subpath)


def _shortcut_label(target: str) -> Optional[str]:
    """Return the shortcut label a target names, or None if it is a directory.

    The leading segment of an inline ``label/sub`` form counts as the label.
    Used only to stamp the report with where the scan came from.
    """
    if Path(target).expanduser().is_dir():
        return None
    head = target.split("/", 1)[0]
    return head if shortcuts.resolve(head) is not None else None


# --------------------------------------------------------------------------- #
# subcommand handlers
# --------------------------------------------------------------------------- #
def _cmd_scan(args: argparse.Namespace) -> int:
    from .orchestrator import run_scan

    root = _resolve(args)
    shortcut = _shortcut_label(args.target)

    result = run_scan(
        root,
        out_dir=Path(args.out) if args.out else None,
        do_graph=not args.no_graph,
        do_audit=not args.no_audit,
        do_snap=not args.no_snap,
        shortcut=shortcut,
        exclude=tuple(args.exclude),
        venv=Path(args.venv) if args.venv else None,
        sys_paths=[Path(p) for p in args.sys_path],
        no_auto_src=args.no_auto_src,
        no_auto_venv=args.no_auto_venv,
        granularity=args.granularity,
        include_external=args.include_external,
        package_root=args.package_root,
        auto_package_root=not args.no_auto_package_root,
        jobs=args.jobs,
        top=args.top,
        full_report=args.full,
        fail_on_cycles=args.fail_on_cycles,
        config_path=args.config,
        coverage=not args.no_coverage,
        events=args.scan_events,
        loops=args.scan_loops,
        attrs=args.scan_attrs,
        extra_scanner=Path(args.extra_scanner) if args.extra_scanner else None,
        fail_on_warning=args.fail_on_warning,
        docs_subdir=args.docs,
        quiet=args.quiet,
    )

    if args.format == "json":
        payload = {
            "out_dir": str(result.out_dir),
            "status": result.status,
            "artifacts": {k: str(v) for k, v in result.artifacts.items()},
        }
        if result.audit is not None:
            payload["audit_summary"] = result.audit["summary"]
        if result.graph is not None:
            payload["graph_summary"] = {
                "internal_nodes": result.graph.summary.get("internal_nodes"),
                "internal_edges": result.graph.summary.get("internal_edges"),
                "is_dag": result.graph.summary.get("is_dag"),
            }
        print(json.dumps(payload, indent=2, sort_keys=True))
    return result.status


def _cmd_graph(args: argparse.Namespace) -> int:
    from .graph import (
        render_report,
        render_unresolved,
        run_graph,
        to_dot,
        to_html,
        to_json,
        to_mermaid,
    )

    root = _resolve(args)
    output = args.output
    if output == "html" and args.granularity != "module":
        print("arachnid: html viewer uses module granularity", file=sys.stderr)
        args.granularity = "module"

    run = run_graph(
        root,
        exclude=tuple(args.exclude),
        sys_paths=[Path(p) for p in args.sys_path],
        venv=Path(args.venv) if args.venv else None,
        no_auto_src=args.no_auto_src,
        no_auto_venv=args.no_auto_venv,
        granularity=args.granularity,
        include_external=args.include_external,
        package_root=args.package_root,
        auto_package_root=not args.no_auto_package_root,
        jobs=args.jobs,
        top=args.top,
        progress=_progress_printer(args.quiet),
        quiet=args.quiet,
    )
    G, summary = run.G, run.summary

    export_text: Optional[str] = None
    if output == "html":
        export_text = to_html(
            G, summary, files_scanned=run.files_scanned,
            template_path=Path(args.template) if args.template else None,
        )
    elif output == "mermaid":
        if G.number_of_nodes() > MERMAID_NODE_WARN:
            print(f"arachnid: {G.number_of_nodes()} nodes is a lot for one mermaid "
                  f"diagram; consider --granularity package", file=sys.stderr)
        export_text = to_mermaid(
            G, direction=args.direction, fenced=not args.raw,
            edge_labels=args.edge_labels,
            template_path=Path(args.template) if args.template else None,
        )
    elif output == "json":
        export_text = to_json(G, summary)
    elif output == "dot":
        export_text = to_dot(G)

    out_target = args.out
    auto_named = False
    if export_text is not None and out_target is None and sys.stdout.isatty():
        out_target = _GRAPH_DEFAULT_OUT[output]
        auto_named = True

    export_to_stdout = export_text is not None and not out_target
    if export_text is not None:
        if out_target:
            out_path = Path(out_target).expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(export_text, encoding="utf-8")
            note = "  (pipe stdout or use --out FILE to choose)" if auto_named else ""
            print(f"arachnid: wrote {output} to {out_path}{note}", file=sys.stderr)
        else:
            sys.stdout.write(export_text)

    # A report-mode run, or -a alongside an export, prints the health report.
    if output == "report" or args.analyze:
        dest = sys.stderr if export_to_stdout else sys.stdout
        dest.write(render_report(summary, str(root), run.files_scanned,
                                 top=args.top, full=args.full))
        dest.write(render_unresolved(G.graph.get("unresolved", []), full=args.full))
        dest.flush()

    if args.fail_on_cycles and summary["sccs"]:
        if not args.quiet:
            print(f"arachnid: failing on {len(summary['sccs'])} circular dependency "
                  f"group(s)", file=sys.stderr)
        return 1
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    from . import audit as audit_pkg
    from .audit import render_audit_text, run_audit, should_fail, write_audit_report

    root = _resolve(args)
    shortcut = _shortcut_label(args.target)
    cfg, resolved_cfg = audit_pkg.prepare_config(root, args.config, tuple(args.exclude))

    report = run_audit(
        root, cfg,
        config_path=resolved_cfg,
        shortcut=shortcut,
        coverage=not args.no_coverage,
        events=args.scan_events,
        loops=args.scan_loops,
        attrs=args.scan_attrs,
        extra_scanner=Path(args.extra_scanner) if args.extra_scanner else None,
    )

    output_path = None
    if args.out:
        output_path = write_audit_report(root, args.out, report)
        print(f"arachnid: wrote audit report to {output_path}", file=sys.stderr)

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_audit_text(
            report,
            output_path=str(output_path) if output_path else None,
            issue_limit=args.print_issues,
            fail_on_warning=args.fail_on_warning,
        ))

    return 1 if should_fail(report, fail_on_warning=args.fail_on_warning) else 0


def _cmd_snap(args: argparse.Namespace) -> int:
    from .snapshot import build_snapshot, write_snapshot

    root = _resolve(args)
    result = build_snapshot(root, docs_subdir=args.docs)

    if args.out == "-":
        sys.stdout.write(result.text)
        return 0

    out_target = args.out or f"{root.name}_docs.txt"
    out_path = write_snapshot(result, Path(out_target))
    if not result.docs_exists:
        print(f"arachnid: no docs directory at {result.docs_dir}; wrote empty snapshot "
              f"to {out_path}", file=sys.stderr)
    else:
        print(f"arachnid: wrote {result.file_count} docs ({result.skipped_binary} "
              f"skipped) to {out_path}", file=sys.stderr)
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    try:
        resolved = shortcuts.add(args.label, args.path)
    except shortcuts.ShortcutError as exc:
        print(f"arachnid: {exc}", file=sys.stderr)
        return 2
    print(f"arachnid: shortcut '{args.label}' -> {resolved}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    rows = shortcuts.list_shortcuts()
    if not rows:
        print("No arachnid shortcuts saved.")
        return 0
    print("Saved arachnid shortcuts:")
    width = max(len(label) for label, _ in rows)
    for label, target in rows:
        print(f"  {label.ljust(width)}  {target}")
    return 0


def _cmd_rm(args: argparse.Namespace) -> int:
    if shortcuts.remove(args.label):
        print(f"arachnid: removed shortcut '{args.label}'")
        return 0
    print(f"arachnid: no shortcut named '{args.label}'", file=sys.stderr)
    return 2


_HANDLERS = {
    "scan": _cmd_scan,
    "graph": _cmd_graph,
    "audit": _cmd_audit,
    "snap": _cmd_snap,
    "add": _cmd_add,
    "list": _cmd_list,
    "ls": _cmd_list,
    "rm": _cmd_rm,
    "remove": _cmd_rm,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    handler = _HANDLERS.get(args.command)
    if handler is None:
        parser.print_help()
        return 2

    try:
        return handler(args)
    except shortcuts.ShortcutError as exc:
        print(f"arachnid: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"arachnid: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"arachnid: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
