# Arachnid validation report

Completed validation against the assembled package in `src/arachnid`.

## Commands run

```bash
python -m compileall -q src
PYTHONPATH=src pytest -q
python -m pip install -e . --break-system-packages
arachnid --version
arachnid scan <fixture> --scan-events --scan-loops --scan-attrs -q
arachnid graph <fixture> -o html --out graph.html -q
arachnid graph <fixture> -o mermaid --raw -q
python -m pip wheel . -w /tmp/arachnid_wheel_test --no-deps
```

## Results

```text
compileall: PASS
pytest: 5 passed
editable install: PASS
version: arachnid 1.0.0
full scan fixture: PASS
HTML export: PASS
Mermaid export: PASS
wheel build: PASS
Python files <=500 LOC: PASS
```

## Feature checks covered

- Unified CLI subcommands: `scan`, `graph`, `audit`, `snap`, `add`, `list`, `rm`.
- TSV shortcuts with `ARACHNID_HOME` isolation and `-r/--subpath` resolution.
- Dependency graph import resolution and exports: JSON, HTML, Mermaid, DOT.
- Package-root internal unresolved import accounting.
- Orphan classification as standalone script vs unused module.
- Audit per-extension LOC limits.
- Auto-exclude of `.arachnid_scans` and related output directories.
- Coverage heuristic for large untested source files.
- Event scanner.
- Hot-loop redundancy scanner.
- Attribute ownership mismatch scanner.
- Info severity tier and `--fail-on-warning` behavior.
- Docs-only snapshot with binary/non-UTF8 skip marker.
- Editable install and wheel build.
