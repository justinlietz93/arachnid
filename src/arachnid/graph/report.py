"""Plain-text health report for the graph layer.

Enhancement 2.4 (orphan classification) lives in :func:`classify_orphan`: an
isolated file with an ``if __name__ == "__main__":`` guard is a deliberate
standalone script, not dead code, so the report labels the two cases
differently instead of lumping every orphan together.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from .._version import __version__

_WIDTH = 66

# First lines of an orphan are scanned for the main-guard. A regex over the
# file head is enough and far cheaper than parsing; matches single or double
# quotes and any internal spacing.
_MAIN_GUARD = re.compile(r"""^\s*if\s+__name__\s*==\s*['"]__main__['"]\s*:""")
_ORPHAN_SCAN_LINES = 20


def _rule(title: str = "") -> str:
    if not title:
        return "=" * _WIDTH
    pad = "-" * max(_WIDTH - len(title) - 4, 0)
    return f"-- {title} {pad}"


def _chain(nodes: List[str], cap: int = 8) -> str:
    shown = nodes[:cap]
    tail = f" -> ... ({len(nodes) - cap} more)" if len(nodes) > cap else ""
    return " -> ".join(shown) + tail


def classify_orphan(root: Path, rel: str) -> Optional[str]:
    """Label an orphan node as a standalone script or an unused module.

    Returns ``"standalone_script"`` when the file's first lines contain a
    ``__main__`` guard, ``"unused_module"`` for any other readable ``.py``
    file, and ``None`` when the node is not a single source file (e.g. a
    package-granularity directory) or cannot be read.
    """
    if not rel.endswith(".py"):
        return None
    path = Path(root) / rel
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(_ORPHAN_SCAN_LINES), fh):
                if _MAIN_GUARD.match(line):
                    return "standalone_script"
    except OSError:
        return None
    return "unused_module"


def classify_orphans(root: Path, orphans: List[str]) -> Dict[str, str]:
    """Classify each orphan, dropping nodes that are not source files."""
    labels: Dict[str, str] = {}
    for rel in orphans:
        label = classify_orphan(root, rel)
        if label is not None:
            labels[rel] = label
    return labels


def render_report(
    summary: dict, root: str, files_scanned: int, top: int = 10, full: bool = False
) -> str:
    s = summary
    if full:
        top = 10**9
    out: List[str] = []
    w = out.append

    w(_rule())
    w(f" arachnid graph {__version__} :: {root}")
    w(_rule())
    w(f" files scanned            {files_scanned}")
    w(f" internal nodes           {s['internal_nodes']}")
    w(f" internal import edges    {s['internal_edges']}")
    w(f" external packages used   {s['external_packages']}")
    w(f" unresolved imports       {s['unresolved_count']}")
    internal_unresolved = s.get("unresolved_internal_count", 0)
    if internal_unresolved:
        w(f"   (+{internal_unresolved} internal to the package, set aside)")
    w(f" files with scan errors   {s['scan_error_count']}")
    if s["is_dag"]:
        w(" import graph is a DAG    yes")
        if s["dependency_depth"] is not None:
            w(f" dependency depth         {s['dependency_depth']}")
            if s["longest_chain"]:
                w(f"   longest chain: {_chain(s['longest_chain'])}")
    else:
        w(f" import graph is a DAG    NO ({len(s['sccs'])} circular group(s))")

    if s["sccs"]:
        w("")
        w(_rule("circular dependencies"))
        for i, comp in enumerate(s["sccs"][: (10**9 if full else 10)], 1):
            cap = 10**9 if full else 12
            members = ", ".join(comp[:cap])
            extra = f" (+{len(comp) - cap} more)" if len(comp) > cap else ""
            w(f" group {i} ({len(comp)} modules): {members}{extra}")
        for cyc in s["cycles_sample"][: (10**9 if full else 5)]:
            w(f"   cycle: {_chain(cyc + [cyc[0]])}")

    if s["top_betweenness"]:
        w("")
        w(_rule("bottlenecks (betweenness centrality)"))
        w(" import chains pass through these; refactor with care")
        for node, score in s["top_betweenness"][:top]:
            w(f"   {score:8.4f}  {node}")

    if s["top_in_degree"]:
        w("")
        w(_rule("most depended on (fan-in)"))
        for node, deg in s["top_in_degree"][:top]:
            w(f"   {int(deg):4d}  {node}")

    if s["top_out_degree"]:
        w("")
        w(_rule("heaviest importers (fan-out)"))
        for node, deg in s["top_out_degree"][:top]:
            w(f"   {int(deg):4d}  {node}")

    if s["external_usage"]:
        w("")
        w(_rule("external dependencies (import statements)"))
        for pkg, count in s["external_usage"][:top]:
            w(f"   {int(count):4d}  {pkg}")

    if s["orphans"]:
        w("")
        w(_rule("orphans (no internal imports either way)"))
        labels = s.get("orphan_labels") or {}
        for node in s["orphans"][:top]:
            tag = labels.get(node)
            suffix = f"  [{tag}]" if tag else ""
            w(f"   {node}{suffix}")
        if len(s["orphans"]) > top:
            w(f"   ... {len(s['orphans']) - top} more")
        if labels:
            scripts = sum(1 for v in labels.values() if v == "standalone_script")
            dead = sum(1 for v in labels.values() if v == "unused_module")
            w(f"   ({scripts} standalone script(s), {dead} unused module(s))")

    if not full:
        w("")
        w(" lists are capped; --full prints everything, the JSON export")
        w(" carries every node, edge, and unresolved entry")
    return "\n".join(out) + "\n"


def render_unresolved(
    unresolved: List[dict], cap: int = 10, full: bool = False
) -> str:
    if full:
        cap = 10**9
    if not unresolved:
        return ""
    out = ["", _rule("unresolved (jedi could not resolve statically)")]
    by_name = Counter(
        u["import"].lstrip(".").split(".")[0] or "." for u in unresolved
    )
    grouped = ", ".join(
        f"{name} ({n})" for name, n in by_name.most_common(10**9 if full else 8)
    )
    more = f", +{len(by_name) - 8} more names" if (len(by_name) > 8 and not full) else ""
    out.append(f" by name: {grouped}{more}")
    for u in unresolved[:cap]:
        internal = "  [internal]" if u.get("internal") else ""
        out.append(f"   {u['source']}:{u['line']}  {u['import']}{internal}")
    if len(unresolved) > cap:
        out.append(f"   ... {len(unresolved) - cap} more")
    return "\n".join(out) + "\n"
