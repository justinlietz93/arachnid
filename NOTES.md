# Arachnid build notes

## Goal
Merge repo_graph + repo_audit + bash (leap/repo_snap/arachnid) into one installable
package `arachnid` with unified CLI. Implement ALL of ARACHNID_TOOL_ENHANCEMENTS.md.

## Source facts (read, confirmed)
- repo_graph: indexer.py (jedi/parso discovery+resolve), grapher.py (nx build+analyze),
  exporters.py (mermaid/json/dot/html), report.py (text), cli.py, templates/{viewer.html,
  mermaid.j2,logic_map.json}. viewer.html placeholders: __REPO_GRAPH_TITLE__, __REPO_GRAPH_DATA__.
- repo_audit: scanner.py (LOC/dir/router/schema audit), defaults.py (DEFAULT_CONFIG,
  TEXT_EXTENSIONS), config_store.py (json shortcuts), cli.py.
- bash arachnid: out dir ROOT/.arachnid_scans/<repo>_<ts>/, artifacts repo_graph.json,
  repo_graph_report.txt, repo_audit/, <repo>_docs.txt, summary.txt, MANIFEST.txt.
- bash shortcuts TSV: ~/.config/arachnid/shortcuts.tsv  (label\t/abs/path).
- arachnid.txt = snapshot dump of same sources (ignore). build/ = stale (ignore).

## Target package layout
arachnid/
  __init__.py, _version.py, cli.py, shortcuts.py, orchestrator.py
  core/file_utils.py        # P0-2.2 OUTPUT_DIRS, merged excludes, should_ignore
  graph/{indexer,grapher,exporters,report,postprocess}.py + templates/
  audit/{defaults,standards,scanner,coverage,formatter}.py
  checks/{__init__,event_scanner,loop_scanner,attr_scanner,plugin_loader}.py
  snapshot/snapshot.py

## Enhancement map (DONE = implemented+tested)
- [ ] 2.1 per-ext LOC limits -> audit/standards.resolve_loc_limits + defaults.loc_limits
- [ ] 2.2 auto-exclude output dirs -> core/file_utils OUTPUT_DIRS into graph+audit
- [ ] 2.3 package-root resolution -> graph/postprocess.detect_package_root + tag unresolved
- [ ] 2.4 orphan classification -> graph/report standalone_script vs unused_module
- [ ] 2.5 test-coverage heuristic -> audit/coverage untested_module (info)
- [ ] 2.6 event scanner --scan-events (info)
- [ ] 2.7 hot-loop redundancy --scan-loops (warning)
- [ ] 2.8 attr ownership --scan-attrs (info)
- [ ] 2.9 info tier -> formatter + summary info_issue_count; fail only on hard unless --fail-on-warning
- [ ] 2.10 pluggable scanners --extra-scanner (importlib visit())
- [ ] snap: docs-only pure python, header "Repository Docs Snapshot - generated YYYY-MM-DD HH:MM"
       (hyphen not en-dash; Justin: no em/en dashes)

## CLI
scan/graph/audit/snap/add/list/rm. Common: --venv --exclude --out --config --format{json,text}
-r/--subpath. graph also: -o{report,json,mermaid,dot,html} + graph opts. Target resolve:
subpath first, then existing dir, then shortcut label, else error. Default target ".".

## Decisions
- --out: scan=dir, graph=file, audit=dir, snap=file (context-appropriate; documented).
- Keep build_graph/analyze_graph back-compatible (package_root kw defaults None = old behavior).
- Preserve repo-graph tests behavior (HTML viewer reachable, exporters intact).
- Honor ARACHNID_HOME / XDG_CONFIG_HOME for shortcut store (testable); default ~/.config/arachnid.

## Completion update

Status: completed and validated.

Implemented:
- 2.1 per-extension LOC limits through audit/standards.py and audit/defaults.py.
- 2.2 auto-excluded output directories through core/file_utils.py, graph indexer, and audit discovery.
- 2.3 package-root unresolved import tagging and auto-detection.
- 2.4 orphan classification in graph/report.py.
- 2.5 test coverage heuristic in audit/coverage.py.
- 2.6 event producer/consumer scanner in checks/event_scanner.py.
- 2.7 hot-loop redundancy scanner in checks/loop_scanner.py.
- 2.8 attribute ownership mismatch scanner in checks/attr_scanner.py.
- 2.9 info severity tier and warning-gate behavior in audit/formatter.py.
- 2.10 pluggable scanner hook in checks/plugin_loader.py.
- Docs-only pure Python snapshot in snapshot/snapshot.py.
- TSV shortcut store at ~/.config/arachnid/shortcuts.tsv with -r/--subpath resolution.
- Unified CLI: scan, graph, audit, snap, add, list/ls, rm/remove.
- Source-layout pyproject with arachnid console script.

Validation:
- python -m compileall -q src: PASS
- PYTHONPATH=src pytest -q: 5 passed
- python -m pip install -e . --break-system-packages: PASS
- arachnid --version: arachnid 1.0.0
- arachnid scan fixture --scan-events --scan-loops --scan-attrs -q: PASS
- arachnid graph fixture -o html/mermaid/json/dot: PASS
- python -m pip wheel . --no-deps: PASS
- Python files <=500 LOC: PASS
