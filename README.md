![Arachnid repository analysis engine](/assets/arachnid_banner.png)

# CLI for fast, lightweight analysis

Arachnid is a unified Python package for repository dependency graphing, standards auditing, and documentation snapshotting.

It bundles repository graphing, standards auditing, and documentation
snapshotting into one installable CLI:

```bash
arachnid scan [target] [options]
arachnid graph [target] [options]
arachnid audit [target] [options]
arachnid snap [target] [options]
arachnid add <path> <label>
arachnid list
arachnid rm <label>
```

## Install

To install this local checkout as a command available from any directory:

```bash
pipx install --editable .
arachnid --help
```

`pipx` creates an isolated environment for the package and exposes its
`arachnid` entry point through `~/.local/bin` (which must be on `PATH`). The
editable install keeps the command pointed at this checkout while developing.

For development-only use inside the repository virtualenv:

```bash
python -m pip install -e .
```

Dependencies are limited to:

```text
jedi
networkx
jinja2
```

## Shortcut storage

Arachnid stores shortcuts in:

```text
~/.config/arachnid/shortcuts.tsv
```

Format:

```text
label<TAB>/absolute/path/to/repo
```

Example:

```bash
arachnid add /media/justin/git/Axia axia
arachnid list
arachnid scan axia
arachnid scan axia -r docs
arachnid rm axia
```

`ARACHNID_HOME` can override the config directory for tests or isolated installs. If `ARACHNID_HOME` is not set, `XDG_CONFIG_HOME/arachnid` is used when available, otherwise `~/.config/arachnid`.

## Commands

### `arachnid scan`

Runs graph, audit, and docs snapshot together.

Default output directory:

```text
ROOT/.arachnid_scans/<repo>_<YYYYMMDDTHHMMSS>/
```

Artifacts:

```text
repo_graph.json
repo_graph_report.txt
repo_graph.html
repo_graph.mmd
repo_audit/
<repo>_docs.txt
summary.txt
MANIFEST.txt
```

The HTML artifact is self-contained and can be opened directly in a browser.
The Mermaid artifact is raw flowchart source suitable for Mermaid tooling.

Example:

```bash
arachnid scan . --scan-events --scan-loops --scan-attrs
```

### `arachnid graph`

Runs only the semantic dependency graph.

```bash
arachnid graph .
arachnid graph . -o json --out graph.json
arachnid graph . -o html --out graph.html
arachnid graph . -o mermaid --raw
arachnid graph . --package-root mypkg
```

The graph scanner preserves the original `repo-graph` behavior:

- Jedi import resolution.
- Auto `src` layout detection.
- Virtualenv detection.
- Module or package granularity.
- JSON, Mermaid, DOT, and HTML viewer exports.
- Cycle detection and centrality analysis.

Enhancements:

- Internal unresolved imports under `--package-root` are marked internal and excluded from the headline unresolved count.
- Orphans are labeled as `[standalone_script]` when a `__main__` guard appears in the first 20 lines, otherwise `[unused_module]`.
- Output directories such as `.arachnid_scans/` are always skipped.
- The HTML viewer uses a deterministic top-down architectural layout:
  dependency depth forms rows, folder branches remain grouped, and a minimal
  dependency backbone is shown by default. Use `all links` to reveal the
  complete graph or select a module to reveal all of its direct links.

### `arachnid audit`

Runs only the standards audit.

```bash
arachnid audit .
arachnid audit . --format json
arachnid audit . --scan-events --scan-loops --scan-attrs
arachnid audit . --fail-on-warning
```

The audit preserves the original `repo-audit` rules:

- File LOC limits.
- Directory direct-file limits.
- Router file checks.
- Schema/model size exceptions.
- JSON report output.

Enhancements:

- Per-extension LOC limits through `loc_limits` config.
- Auto-exclusion of Arachnid output directories.
- Info tier for non-failing suggestions.
- Test coverage heuristic for source files over 200 LOC without a matching test.
- Optional AST event producer/consumer scanner.
- Optional hot-loop redundancy scanner.
- Optional attribute ownership mismatch scanner.
- Optional `--extra-scanner <script.py>` plugin hook.
- Oversize files beneath `template/` or `templates/` are reported as info,
  rather than LOC failures. Override the directory names with
  `loc_limits.template_directories`.

### `arachnid snap`

Creates a docs-only snapshot from `ROOT/docs` by default, plus recognized
repository docs such as `README.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`ARCHITECTURE.md`, `CHANGELOG.md`, `LICENSE`, and `SECURITY.md` wherever they
occur outside generated or dependency directories, together with conventionally
named project documents such as `NOTES.md`, `TODO.md`, and `VALIDATION.md`.

```bash
arachnid snap .
arachnid snap . --docs docs/architecture --out architecture_docs.txt
arachnid snap . --out -
```

All documentation/config files under the selected docs tree are included. Away
from that tree, Arachnid includes only recognized documentation filenames:

```text
.md .rst .txt .adoc .org .yml .yaml .json .toml .ini .cfg
```

Source code and arbitrary repository files are not included.

Binary or non-UTF8 files are represented as:

```text
[Skipped: binary or non-UTF8]
```

No `ripgrep`, `file`, shell commands, or subprocess calls are used for snapshotting.

## Config

Arachnid uses `.repo-standards.json` when present. Defaults include:

```json
{
  "loc_limits": {
    "default": { "warning": 250, "hard": 400 },
    "template_directories": ["template", "templates"],
    "overrides": {
      ".md": { "warning": 1000, "hard": 2000 },
      ".json": { "warning": 300, "hard": 500 },
      ".yml": { "warning": 200, "hard": 400 },
      ".txt": { "warning": 500, "hard": 1000 }
    }
  }
}
```

CLI `--exclude GLOB` works in both graph and audit commands.

## Extra scanner hook

`--extra-scanner script.py` loads a Python file that defines `visit`.

Supported signatures:

```python
def visit(tree):
    return [{"rule": "custom", "message": "finding"}]
```

or:

```python
def visit(tree, path, root):
    return [{"severity": "info", "rule": "custom", "message": "finding"}]
```

Findings are merged into the audit `extra_issues` list.

## Exit behavior

- Hard issues fail.
- Warnings do not fail by default.
- `--fail-on-warning` makes warnings fail.
- Info findings never fail.
