from __future__ import annotations

from pathlib import Path

from arachnid import shortcuts


def test_shortcuts_tsv_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ARACHNID_HOME", str(tmp_path / "config"))
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    saved = shortcuts.add("demo", repo)
    assert saved == repo.resolve()
    assert shortcuts.list_shortcuts() == [("demo", str(repo.resolve()))]
    assert shortcuts.resolve_target("demo", subpath="docs") == docs.resolve()
    assert shortcuts.remove("demo") is True
    assert shortcuts.list_shortcuts() == []
