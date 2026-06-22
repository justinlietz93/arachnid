"""Dependency graph construction and analysis on networkx."""

from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import networkx as nx

from ..core.file_utils import DEFAULT_EXCLUDED_DIRS
from .indexer import FileScanResult, ResolvedImport, detect_src_roots
from .postprocess import tag_internal_unresolved

# Modules that are language directives, not dependencies.
EXTERNAL_IGNORE = frozenset({"__future__"})


def _remap_to_tree(target: Path, root: Path, src_roots) -> Optional[Path]:
    """Prefer the in-tree copy when a package exists both installed and
    vendored. An import resolved into site-packages whose module also
    exists under a detected src root (or the scan root) is remapped to the
    source file in the tree, so the graph reads the repository's own
    structure instead of the installed shadow."""
    parts = target.parts
    if "site-packages" not in parts:
        return None
    sub = Path(*parts[parts.index("site-packages") + 1 :])
    candidates = [Path(sr) / sub for sr in src_roots] + [root / sub]
    for cand in candidates:
        if cand.suffix == ".pyi":
            cand = cand.with_suffix(".py")
        if not cand.exists():
            continue
        try:
            rel = cand.resolve().relative_to(root)
        except ValueError:
            continue
        if any(p in DEFAULT_EXCLUDED_DIRS for p in rel.parts):
            continue
        return cand.resolve()
    return None


def _classify(imp: ResolvedImport, root: Path) -> Tuple[str, Optional[str]]:
    """Classify one resolved import.

    Returns (kind, ident):
      ("internal", "rel/path.py")   target file is project code under root
      ("external", "package")       stdlib or third party, top-level name
      ("unresolved", None)          jedi could not resolve it statically

    A target physically under root but inside an excluded directory
    (.venv, site-packages, build, ...) is NOT internal. Installed
    packages are externals no matter where they live on disk.
    """
    target = Path(imp.target).resolve() if imp.target else None
    if target is not None:
        try:
            rel = target.relative_to(root)
        except ValueError:
            rel = None
        if rel is not None:
            if any(part in DEFAULT_EXCLUDED_DIRS for part in rel.parts):
                rel = None  # physically under root, not project code
            else:
                return "internal", rel.as_posix()
    if imp.full_name:
        top = imp.full_name.split(".")[0]
        # jedi deep-resolves some stdlib imports into private accelerator
        # modules (datetime -> _datetime). For external usage the public
        # name the code actually wrote is the right identity.
        if top.startswith("_") and imp.raw_path and not imp.raw_path.startswith("."):
            written = imp.raw_path.split(".")[0]
            if written and not written.startswith("_"):
                top = written
        return "external", top
    if target is not None:
        parts = target.parts
        if "site-packages" in parts:
            idx = parts.index("site-packages")
            if idx + 1 < len(parts):
                return "external", parts[idx + 1].split(".")[0]
        return "external", target.stem
    return "unresolved", None


def _collapse(rel_posix: str, granularity: str) -> str:
    if granularity == "package":
        head, _, tail = rel_posix.partition("/")
        return head if tail else rel_posix
    return rel_posix


def build_graph(
    root: Path,
    results: Iterable[FileScanResult],
    *,
    include_external: bool = False,
    granularity: str = "module",
    src_roots=None,
    package_root: Optional[str] = None,
) -> nx.DiGraph:
    """Build a directed dependency graph from scan results.

    ``src_roots`` are nested import roots used to remap imports that
    resolved into an installed copy back to the vendored source in the
    tree; ``None`` auto-detects them, ``()`` disables the remap.

    ``package_root`` is the import name of the project's own package. When
    given, unresolved imports of that package are marked internal so they can
    be excluded from the headline unresolved count (enhancement 2.3). They
    remain in the full unresolved log either way.

    Nodes:
      internal  one per file (granularity="module") or per top-level
                directory (granularity="package"), id = posix path
                relative to root
      external  top-level package name, attr kind="external"
                (only when include_external is True)

    Edge attributes:
      names       sorted list of names imported across all statements
      statements  number of import statements behind the edge

    Edges point at the file where the imported object is actually
    defined. ``from pkg import Thing`` re-exported by ``pkg/__init__.py``
    produces an edge to the defining module, not to ``__init__.py``.

    Graph attributes carry the audit trail: ``unresolved`` (imports jedi
    could not resolve), ``scan_errors``, and ``external_usage`` (a count
    per external package, tallied even when externals are not graphed).
    """
    root = Path(root).resolve()
    if src_roots is None:
        src_roots = detect_src_roots(root)
    G = nx.DiGraph()
    G.graph["root"] = str(root)
    G.graph["granularity"] = granularity
    G.graph["package_root"] = package_root

    unresolved: List[dict] = []
    scan_errors: List[dict] = []
    ext_usage: Counter = Counter()

    rel_of: Dict[Path, str] = {}
    for r in results:
        try:
            rel_of[r.path] = r.path.resolve().relative_to(root).as_posix()
        except ValueError:
            continue  # symlinked outside the root; not part of this graph

    # Seed every scanned file as a node so orphans are visible.
    for r in results:
        rel = rel_of.get(r.path)
        if rel is None:
            continue
        node = _collapse(rel, granularity)
        if node not in G:
            G.add_node(node, kind="internal", files=0)
        G.nodes[node]["files"] += 1
        if r.error:
            scan_errors.append({"file": rel, "error": r.error})

    for r in results:
        rel = rel_of.get(r.path)
        if rel is None:
            continue
        src = _collapse(rel, granularity)
        for imp in r.imports:
            if imp.target is not None and src_roots is not None:
                remapped = _remap_to_tree(Path(imp.target).resolve(), root, src_roots)
                if remapped is not None:
                    imp = replace(imp, target=remapped)
            kind, ident = _classify(imp, root)
            if kind == "unresolved":
                unresolved.append(
                    {
                        "source": rel,
                        "import": imp.raw_path,
                        "name": imp.name,
                        "line": imp.line,
                    }
                )
                continue
            if kind == "external":
                assert ident is not None
                if ident in EXTERNAL_IGNORE:
                    continue
                ext_usage[ident] += 1
                if not include_external:
                    continue
                dst = ident
                if dst not in G:
                    G.add_node(dst, kind="external")
            else:
                assert ident is not None
                dst = _collapse(ident, granularity)
                if dst not in G:
                    # Target resolved inside root but outside the scanned
                    # set (e.g. an excluded file). Keep it; mark it.
                    G.add_node(dst, kind="internal", files=0, scanned=False)
            if src == dst:
                continue
            if G.has_edge(src, dst):
                data = G.edges[src, dst]
                data["statements"] += 1
                if imp.name not in data["names"]:
                    data["names"].append(imp.name)
            else:
                G.add_edge(src, dst, names=[imp.name], statements=1)

    for _, _, data in G.edges(data=True):
        data["names"] = sorted(data["names"])

    # Enhancement 2.3: tag (do not drop) unresolved imports of the project's
    # own package so the count can exclude them while the log keeps them.
    tag_internal_unresolved(unresolved, package_root)

    G.graph["unresolved"] = unresolved
    G.graph["scan_errors"] = scan_errors
    G.graph["external_usage"] = dict(ext_usage.most_common())
    return G


def analyze_graph(G: nx.DiGraph, top: int = 10, max_cycles: int = 25) -> dict:
    """Compute graph health metrics and write them back onto nodes.

    Betweenness centrality flags the bottleneck modules: the files most
    import chains must pass through, the ones to treat carefully during a
    refactor. Fan-in (in-degree) flags the most depended-on modules.
    Strongly connected components of size > 1 are circular dependencies.

    The unresolved count excludes imports tagged internal (project's own
    package, enhancement 2.3); ``unresolved_internal_count`` reports how
    many were set aside, and the full list stays on ``G.graph['unresolved']``.
    """
    internal = [n for n, d in G.nodes(data=True) if d.get("kind") == "internal"]
    H = G.subgraph(internal)

    sccs = sorted(
        (sorted(c) for c in nx.strongly_connected_components(H) if len(c) > 1),
        key=len,
        reverse=True,
    )
    cycle_nodes = set(itertools.chain.from_iterable(sccs))
    cycles_sample = (
        list(itertools.islice(nx.simple_cycles(H), max_cycles)) if sccs else []
    )

    if len(H) > 2:
        bc = nx.betweenness_centrality(H)
    else:
        bc = {n: 0.0 for n in H}
    in_deg = dict(H.in_degree())
    out_deg = dict(H.out_degree())

    is_dag = not sccs
    depth = None
    longest_chain: List[str] = []
    if is_dag and len(H) > 0:
        longest_chain = nx.dag_longest_path(H)
        depth = max(len(longest_chain) - 1, 0)

    orphans = sorted(n for n in H if in_deg[n] == 0 and out_deg[n] == 0)

    for n in H:
        G.nodes[n]["betweenness"] = round(bc[n], 6)
        G.nodes[n]["in_degree"] = in_deg[n]
        G.nodes[n]["out_degree"] = out_deg[n]
        G.nodes[n]["in_cycle"] = n in cycle_nodes

    def _top(d: dict, reverse: bool = True) -> List[Tuple[str, float]]:
        ranked = sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(n, v) for n, v in ranked[:top] if v > 0]

    all_unresolved = G.graph.get("unresolved", [])
    external_unresolved = [u for u in all_unresolved if not u.get("internal")]
    internal_unresolved = [u for u in all_unresolved if u.get("internal")]

    summary = {
        "internal_nodes": len(H),
        "internal_edges": H.number_of_edges(),
        "external_packages": len(G.graph.get("external_usage", {})),
        "unresolved_count": len(external_unresolved),
        "unresolved_internal_count": len(internal_unresolved),
        "scan_error_count": len(G.graph.get("scan_errors", [])),
        "is_dag": is_dag,
        "dependency_depth": depth,
        "longest_chain": longest_chain,
        "sccs": sccs,
        "cycles_sample": cycles_sample,
        "orphans": orphans,
        "top_betweenness": _top(bc),
        "top_in_degree": _top(in_deg),
        "top_out_degree": _top(out_deg),
        "external_usage": list(G.graph.get("external_usage", {}).items())[:top],
    }
    G.graph["summary"] = {
        k: v for k, v in summary.items() if k not in ("cycles_sample",)
    }
    return summary
