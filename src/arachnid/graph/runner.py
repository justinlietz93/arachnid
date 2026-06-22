"""High-level graph driver shared by the CLI and the scan orchestrator.

Keeps the multi-step pipeline (detect roots and environment, scan, build,
analyze, classify orphans) in one place so the ``graph`` subcommand and the
``scan`` orchestrator behave identically and neither duplicates the wiring.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import networkx as nx

from .grapher import analyze_graph, build_graph
from .indexer import detect_environment, detect_src_roots, scan_project
from .postprocess import detect_package_root
from .report import classify_orphans


@dataclass
class GraphRun:
    """Everything a caller needs to export or report the graph."""

    root: Path
    G: nx.DiGraph
    summary: dict
    files_scanned: int
    src_roots: List[Path] = field(default_factory=list)
    env_path: Optional[Path] = None
    package_root: Optional[str] = None


def run_graph(
    root: Path,
    *,
    exclude: Sequence[str] = (),
    sys_paths: Sequence[Path] = (),
    venv: Optional[Path] = None,
    no_auto_src: bool = False,
    no_auto_venv: bool = False,
    granularity: str = "module",
    include_external: bool = False,
    package_root: Optional[str] = None,
    auto_package_root: bool = True,
    jobs: int = 1,
    top: int = 10,
    progress: Optional[Callable[[int, int, Path], None]] = None,
    log=sys.stderr,
    quiet: bool = False,
) -> GraphRun:
    """Scan ``root``, build the dependency graph, and analyze it.

    ``package_root`` (or auto-detection when ``auto_package_root`` is set and
    no value is given) drives enhancement 2.3: unresolved imports of the
    project's own package are tagged internal and excluded from the headline
    unresolved count. Orphans are classified (enhancement 2.4) and the labels
    are attached to ``summary['orphan_labels']``.
    """
    root = Path(root).expanduser().resolve()

    auto_src = not no_auto_src
    src_roots = detect_src_roots(root, exclude_globs=tuple(exclude)) if auto_src else []
    if not quiet:
        for src in src_roots:
            print(f"arachnid: import root: {src.relative_to(root)}", file=log)

    env_path = Path(venv).expanduser() if venv else None
    if env_path is None and not no_auto_venv:
        env_path = detect_environment(root)
        if env_path and not quiet:
            print(f"arachnid: using environment: {env_path}", file=log)

    pkg_root = package_root
    if pkg_root is None and auto_package_root:
        pkg_root = detect_package_root(root)
        if pkg_root and not quiet:
            print(f"arachnid: package root: {pkg_root}", file=log)

    results = scan_project(
        root,
        exclude_globs=tuple(exclude),
        sys_paths=[Path(p) for p in sys_paths] + src_roots,
        environment_path=env_path,
        auto_src=False,  # roots already detected and passed above
        jobs=max(jobs, 1),
        progress=progress,
    )

    G = build_graph(
        root,
        results,
        include_external=include_external,
        granularity=granularity,
        src_roots=src_roots,
        package_root=pkg_root,
    )
    summary = analyze_graph(G, top=top)
    summary["orphan_labels"] = classify_orphans(root, summary["orphans"])
    G.graph["summary"] = {
        k: v for k, v in summary.items() if k not in ("cycles_sample",)
    }

    return GraphRun(
        root=root,
        G=G,
        summary=summary,
        files_scanned=len(results),
        src_roots=src_roots,
        env_path=env_path,
        package_root=pkg_root,
    )
