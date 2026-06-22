"""Semantic dependency graphs for Python codebases.

jedi resolves every import to the file where the object is actually defined
(through aliases, relative imports, and __init__.py re-exports); networkx
scores the graph; exporters emit Mermaid, JSON, DOT, and a self-contained
HTML viewer.
"""

from ..core.file_utils import DEFAULT_EXCLUDED_DIRS
from .exporters import to_dot, to_html, to_json, to_mermaid
from .grapher import analyze_graph, build_graph
from .indexer import (
    FileScanResult,
    ResolvedImport,
    detect_environment,
    detect_src_roots,
    iter_python_files,
    scan_file,
    scan_project,
)
from .postprocess import detect_package_root, tag_internal_unresolved
from .report import (
    classify_orphan,
    classify_orphans,
    render_report,
    render_unresolved,
)
from .runner import GraphRun, run_graph

__all__ = [
    "DEFAULT_EXCLUDED_DIRS",
    "FileScanResult",
    "ResolvedImport",
    "detect_environment",
    "detect_src_roots",
    "iter_python_files",
    "scan_file",
    "scan_project",
    "build_graph",
    "analyze_graph",
    "detect_package_root",
    "tag_internal_unresolved",
    "to_mermaid",
    "to_html",
    "to_json",
    "to_dot",
    "render_report",
    "render_unresolved",
    "classify_orphan",
    "classify_orphans",
    "GraphRun",
    "run_graph",
]
