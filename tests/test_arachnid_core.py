from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from arachnid.audit import prepare_config, run_audit
from arachnid.audit.defaults import DEFAULT_CONFIG
from arachnid.audit.scanner import classify_file
from arachnid.cli import build_parser
from arachnid.graph import run_graph, to_html, to_json, to_mermaid
from arachnid.snapshot import build_snapshot


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    root = tmp_path / "fixture"
    write(root / "pyproject.toml", '[project]\nname = "mypkg"\nversion = "0.1.0"\n')
    write(root / "src/mypkg/__init__.py", 'from .core import Engine\n__all__ = ["Engine"]\n')
    write(root / "src/mypkg/helpers.py", "def helper():\n    return 41\n")
    write(
        root / "src/mypkg/core.py",
        "import os\nimport json\nfrom mypkg.helpers import helper\n"
        "from mypkg.not_real import ghost\nimport nonexistent_third_party\n"
        "class Engine:\n    def run(self):\n        return helper() + os.getpid()\n",
    )
    write(
        root / "src/mypkg/sub/tool_cli.py",
        "import sys\ndef main():\n    return 0\nif __name__ == \"__main__\":\n    sys.exit(main())\n",
    )
    write(root / "src/mypkg/sub/dead_code.py", "VALUE = 1\n")
    lines = ["import math", ""]
    for i in range(65):
        lines += [f"def compute_{i}(x):", f"    y = x * {i} + math.sqrt({i} + 1)", "    return y", ""]
    write(root / "src/mypkg/bigmod.py", "\n".join(lines))
    write(
        root / "src/mypkg/bus.py",
        "class Bus:\n"
        "    def wire(self):\n"
        "        self.publish(\"tick\", 1)\n"
        "        self.publish(\"stop\", None)\n"
        "        self.subscribe(\"tick\", self._on_tick)\n"
        "        self.subscribe(\"ghost_event\", self._on_ghost)\n"
        "    def publish(self, name, payload): pass\n"
        "    def subscribe(self, name, cb): pass\n"
        "    def _on_tick(self, p): return p\n"
        "    def _on_ghost(self, p): return p\n",
    )
    write(
        root / "src/mypkg/mainloop.py",
        "def scan(items): return len(items)\n"
        "def run(items, n):\n"
        "    total = 0\n"
        "    for _ in range(n):\n"
        "        total += scan(items)\n"
        "        total += scan(items)\n"
        "    return total\n",
    )
    write(
        root / "src/mypkg/runtime_state.py",
        "class State:\n"
        "    def __init__(self, engine):\n"
        "        self.engine = engine\n"
        "        self._cache = {}\n"
        "    def store(self, k, v):\n"
        "        self._cache[k] = v\n"
        "    def fetch(self, k):\n"
        "        return self.engine._cache.get(k)\n",
    )
    write(root / "docs/overview.md", "# Overview\nText.\n")
    write(root / "docs/guide/usage.rst", "Usage\n=====\nRun it.\n")
    (root / "docs/bad.txt").write_bytes(b"\xff\xfe\x00\x80")
    write(root / "tests/test_core.py", "from mypkg.core import Engine\ndef test_engine(): assert Engine()\n")
    return root


def test_graph_package_root_orphans_and_exports(fixture_repo: Path) -> None:
    run = run_graph(fixture_repo, quiet=True)
    assert run.package_root == "mypkg"
    assert run.summary["unresolved_count"] == 1
    assert run.summary["unresolved_internal_count"] == 1
    assert run.summary["orphan_labels"]["src/mypkg/sub/tool_cli.py"] == "standalone_script"
    assert run.summary["orphan_labels"]["src/mypkg/sub/dead_code.py"] == "unused_module"
    payload = json.loads(to_json(run.G, run.summary))
    assert payload["schema"] == "arachnid-graph/1"
    assert "src/mypkg/core.py" in {n["id"] for n in payload["graph"]["nodes"]}
    assert to_mermaid(run.G, fenced=False).startswith("flowchart LR")
    assert "window.REPO_GRAPH_DATA" in to_html(run.G, run.summary, files_scanned=run.files_scanned)


def test_audit_enhancements(fixture_repo: Path) -> None:
    cfg, resolved = prepare_config(fixture_repo)
    report = run_audit(fixture_repo, cfg, config_path=resolved, events=True, loops=True, attrs=True)
    rules = {x["rule"] for x in report["file_issues"] + report["extra_issues"]}
    assert "file_over_warning" in rules
    assert "untested_module" in rules
    assert "event_produced_never_consumed" in rules
    assert "event_consumed_never_produced" in rules
    assert "redundant_call_in_loop" in rules
    assert "attr_ownership_mismatch" in rules
    assert report["summary"]["hard_issue_count"] == 0
    assert report["summary"]["info_issue_count"] >= 3


@pytest.mark.parametrize(
    "extension", sorted(DEFAULT_CONFIG["routers"]["non_code_extensions"])
)
def test_non_code_router_names_are_not_classified_as_routers(
    fixture_repo: Path, extension: str
) -> None:
    item = f"docs/router{extension}"
    write(fixture_repo / item, "# Router documentation\n")
    cfg, _ = prepare_config(fixture_repo)

    report = classify_file(fixture_repo, item, cfg)

    assert report["is_router_file"] is False
    assert report["router_report"] is None


def test_router_non_code_extensions_can_be_overridden(fixture_repo: Path) -> None:
    item = "docs/router.md"
    write(fixture_repo / item, "# Router documentation\n")
    cfg, _ = prepare_config(fixture_repo)
    cfg["routers"]["non_code_extensions"] = []

    report = classify_file(fixture_repo, item, cfg)

    assert report["is_router_file"] is True
    assert report["router_report"] is not None


def test_snapshot_docs_and_repository_documents(fixture_repo: Path) -> None:
    write(fixture_repo / "README.md", "# Repository overview\n")
    write(fixture_repo / "AGENTS.md", "# Repository instructions\n")
    write(fixture_repo / "src/mypkg/README.rst", "Package notes\n=============\n")
    snap = build_snapshot(fixture_repo)
    assert snap.docs_exists is True
    assert "Repository Docs Snapshot - generated" in snap.text
    assert "--- FILE: docs/overview.md ---" in snap.text
    assert "--- FILE: README.md ---" in snap.text
    assert "--- FILE: AGENTS.md ---" in snap.text
    assert "--- FILE: src/mypkg/README.rst ---" in snap.text
    assert "[Skipped: binary or non-UTF8]" in snap.text
    assert "pyproject.toml" not in snap.text
    assert "src/mypkg/core.py" not in snap.text


def test_snapshot_keeps_repository_documents_when_docs_dir_is_missing(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "# Repository overview\n")
    write(tmp_path / "AGENTS.md", "# Repository instructions\n")
    snap = build_snapshot(tmp_path)
    assert snap.docs_exists is False
    assert snap.included == ["AGENTS.md", "README.md"]


def test_cli_scan_and_fail_on_warning(fixture_repo: Path) -> None:
    env = {"PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "arachnid.cli", "scan", str(fixture_repo), "--scan-loops", "-q", "--format", "json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert Path(payload["artifacts"]["graph_json"]).exists()
    warn = subprocess.run(
        [sys.executable, "-m", "arachnid.cli", "audit", str(fixture_repo), "--scan-loops", "--fail-on-warning", "-q"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert warn.returncode == 1


@pytest.mark.parametrize("command", ["scan", "audit"])
def test_cli_help_lists_all_audit_scanner_flags(command: str) -> None:
    env = {"PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "arachnid.cli", command, "--help"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    for flag in (
        "--config",
        "--print-issues",
        "--fail-on-warning",
        "--no-coverage",
        "--scan-events",
        "--scan-loops",
        "--scan-attrs",
        "--extra-scanner",
        "--scan-all",
    ):
        assert flag in proc.stdout


def test_root_cli_help_lists_every_subcommand_flag() -> None:
    env = {"PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "arachnid.cli", "--help"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    subparsers = next(
        action
        for action in build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    for command_parser in subparsers.choices.values():
        for action in command_parser._actions:
            for flag in action.option_strings:
                assert flag in proc.stdout


def test_cli_audit_scan_all_runs_every_builtin_scanner(fixture_repo: Path) -> None:
    env = {"PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "arachnid.cli",
            "audit",
            str(fixture_repo),
            "--scan-all",
            "--format",
            "json",
            "-q",
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0, proc.stderr
    rules = {issue["rule"] for issue in json.loads(proc.stdout)["extra_issues"]}
    assert {
        "event_produced_never_consumed",
        "redundant_call_in_loop",
        "attr_ownership_mismatch",
    } <= rules
