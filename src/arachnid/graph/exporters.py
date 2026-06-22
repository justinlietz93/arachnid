"""Exporters: Mermaid (Jinja2 template), JSON (node_link_data), DOT, HTML viewer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import List, Optional

import jedi
import networkx as nx
from jinja2 import Template

from .._version import __version__

HUB_COUNT = 5  # top-betweenness nodes highlighted in mermaid output


def _default_template() -> str:
    return (
        resources.files("arachnid.graph")
        .joinpath("templates")
        .joinpath("mermaid.j2")
        .read_text(encoding="utf-8")
    )


def to_mermaid(
    G: nx.DiGraph,
    *,
    direction: str = "LR",
    fenced: bool = True,
    edge_labels: bool = False,
    template_path: Optional[Path] = None,
) -> str:
    """Render the graph as a Mermaid flowchart, ready to paste in Markdown.

    Internal files are grouped into subgraphs by top-level directory.
    External packages are dashed. Edges inside a circular dependency are
    drawn red. The top betweenness-centrality nodes get a thick orange
    border so the bottlenecks are visible at a glance.
    """
    tpl_src = (
        Path(template_path).read_text(encoding="utf-8")
        if template_path
        else _default_template()
    )
    tpl = Template(tpl_src, trim_blocks=True, lstrip_blocks=True)

    nodes = list(G.nodes(data=True))
    ids = {n: f"n{i}" for i, (n, _) in enumerate(nodes)}

    groups: dict = {}
    ungrouped: List[dict] = []
    externals: List[dict] = []
    for n, d in nodes:
        entry = {"id": ids[n], "label": str(n).replace('"', "'")}
        if d.get("kind") == "external":
            externals.append(entry)
        elif G.graph.get("granularity") == "module" and "/" in n:
            top = n.split("/", 1)[0]
            groups.setdefault(top, []).append(entry)
        else:
            ungrouped.append(entry)
    group_list = [
        {"id": f"g{i}", "label": name, "nodes": members}
        for i, (name, members) in enumerate(sorted(groups.items()))
    ]
    if externals:
        group_list.append(
            {"id": "gext", "label": "external", "nodes": externals}
        )

    # SCC membership decides which edges are part of a cycle.
    internal = [n for n, d in nodes if d.get("kind") == "internal"]
    comp_of: dict = {}
    for i, comp in enumerate(nx.strongly_connected_components(G.subgraph(internal))):
        if len(comp) > 1:
            for n in comp:
                comp_of[n] = i

    edge_lines: List[str] = []
    link_styles: List[str] = []
    for idx, (u, v, d) in enumerate(G.edges(data=True)):
        external_edge = G.nodes[v].get("kind") == "external"
        arrow = "-.->" if external_edge else "-->"
        label = ""
        if edge_labels:
            names = d.get("names", [])
            shown = ", ".join(names[:4]) + (
                f" +{len(names) - 4}" if len(names) > 4 else ""
            )
            label = f"|{shown}|"
        edge_lines.append(f"{ids[u]} {arrow}{label} {ids[v]}")
        if u in comp_of and comp_of.get(u) == comp_of.get(v):
            link_styles.append(f"linkStyle {idx} stroke:#d33,stroke-width:2px")

    class_defs: List[str] = []
    class_assignments: List[str] = []
    if externals:
        class_defs.append("classDef external stroke-dasharray: 5 5,opacity:0.85")
        class_assignments.append(
            "class " + ",".join(e["id"] for e in externals) + " external"
        )
    hubs = sorted(
        (n for n in internal if G.nodes[n].get("betweenness", 0) > 0),
        key=lambda n: -G.nodes[n]["betweenness"],
    )[:HUB_COUNT]
    if hubs:
        class_defs.append("classDef hub stroke:#e67e22,stroke-width:3px")
        class_assignments.append(
            "class " + ",".join(ids[n] for n in hubs) + " hub"
        )
    cyc_nodes = [n for n in internal if G.nodes[n].get("in_cycle")]
    if cyc_nodes:
        class_defs.append("classDef cyc stroke:#d33,stroke-width:2px")
        class_assignments.append(
            "class " + ",".join(ids[n] for n in cyc_nodes) + " cyc"
        )

    body = tpl.render(
        direction=direction,
        groups=group_list,
        ungrouped=ungrouped,
        edges=edge_lines,
        class_defs=class_defs,
        class_assignments=class_assignments,
        link_styles=link_styles,
    ).strip()
    if fenced:
        return f"```mermaid\n{body}\n```\n"
    return body + "\n"


def to_json(G: nx.DiGraph, summary: dict, *, indent: int = 2) -> str:
    """Machine-readable artifact: metadata envelope + node_link graph."""
    try:
        graph_data = nx.node_link_data(G, edges="links")
    except TypeError:  # networkx < 3.4 has no `edges` kwarg
        graph_data = nx.node_link_data(G)
    payload = {
        "schema": "arachnid-graph/1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": G.graph.get("root"),
        "tool": {
            "name": "arachnid",
            "version": __version__,
            "jedi": jedi.__version__,
            "networkx": nx.__version__,
        },
        "summary": summary,
        "graph": graph_data,
    }
    return json.dumps(payload, indent=indent, default=str)


HTML_HUB_COUNT = 5


def _viewer_template() -> str:
    return (
        resources.files("arachnid.graph")
        .joinpath("templates")
        .joinpath("viewer.html")
        .read_text(encoding="utf-8")
    )


def to_html(
    G: nx.DiGraph,
    summary: dict,
    *,
    files_scanned: Optional[int] = None,
    unresolved_by_name: Optional[list] = None,
    template_path: Optional[Path] = None,
) -> str:
    """Render a self-contained interactive HTML viewer.

    One file, zero network dependencies, works from file://. Directory
    nodes expand on click, hull labels collapse them, files open a details
    panel; pan, zoom, drag, search, externals toggle, cycle and bottleneck
    highlighting. Expects the module-granularity graph; the viewer does
    its own collapsing.
    """
    internal = [n for n, d in G.nodes(data=True) if d.get("kind") == "internal"]
    comp_of: dict = {}
    for i, comp in enumerate(nx.strongly_connected_components(G.subgraph(internal))):
        if len(comp) > 1:
            for n in comp:
                comp_of[n] = i
    hubs = set(
        sorted(
            (n for n in internal if G.nodes[n].get("betweenness", 0) > 0),
            key=lambda n: -G.nodes[n]["betweenness"],
        )[:HTML_HUB_COUNT]
    )

    nodes = []
    for n, d in G.nodes(data=True):
        nodes.append(
            {
                "id": n,
                "kind": d.get("kind", "internal"),
                "in_degree": d.get("in_degree"),
                "out_degree": d.get("out_degree"),
                "betweenness": d.get("betweenness"),
                "in_cycle": bool(d.get("in_cycle")),
                "hub": n in hubs,
                "scanned": d.get("scanned", True),
                "files": d.get("files"),
            }
        )
    edges = []
    for u, v, d in G.edges(data=True):
        edges.append(
            {
                "source": u,
                "target": v,
                "names": d.get("names", []),
                "statements": d.get("statements", 1),
                "external": G.nodes[v].get("kind") == "external",
                "cyclic": u in comp_of and comp_of.get(u) == comp_of.get(v),
            }
        )

    unresolved = G.graph.get("unresolved", [])
    if unresolved_by_name is None:
        counts: dict = {}
        for u in unresolved:
            top = u["import"].lstrip(".").split(".")[0] or "."
            counts[top] = counts.get(top, 0) + 1
        unresolved_by_name = sorted(counts.items(), key=lambda kv: -kv[1])

    root = G.graph.get("root", "")
    payload = {
        "root": root,
        "root_label": Path(root).name or root or "repository",
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": __version__,
        "files_scanned": files_scanned
        if files_scanned is not None
        else sum(1 for n in nodes if n["kind"] == "internal"),
        "summary": {
            k: v for k, v in summary.items() if k not in ("cycles_sample",)
        },
        "unresolved_by_name": unresolved_by_name,
        "nodes": nodes,
        "edges": edges,
    }
    data_js = json.dumps(payload, default=str).replace("</", "<\\/")
    tpl = (
        Path(template_path).read_text(encoding="utf-8")
        if template_path
        else _viewer_template()
    )
    title = f"arachnid :: {payload['root_label']}"
    return tpl.replace("__REPO_GRAPH_TITLE__", title).replace(
        "__REPO_GRAPH_DATA__", data_js
    )


def to_dot(G: nx.DiGraph) -> str:
    """Graphviz DOT, no extra dependencies."""

    def q(s: str) -> str:
        return '"' + str(s).replace('"', r"\"") + '"'

    lines = [
        "digraph arachnid_graph {",
        "  rankdir=LR;",
        '  node [shape=box, fontname="Helvetica", fontsize=10];',
    ]
    for n, d in G.nodes(data=True):
        attrs = []
        if d.get("kind") == "external":
            attrs.append("style=dashed")
        if d.get("in_cycle"):
            attrs.append("color=red")
        suffix = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f"  {q(n)}{suffix};")
    for u, v, d in G.edges(data=True):
        style = " [style=dashed]" if G.nodes[v].get("kind") == "external" else ""
        lines.append(f"  {q(u)} -> {q(v)}{style};")
    lines.append("}")
    return "\n".join(lines) + "\n"
