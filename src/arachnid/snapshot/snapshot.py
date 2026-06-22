"""Section 4: documentation snapshot (docs-only, pure Python).

``arachnid snap`` flattens a project's ``docs/`` tree into one text file so a
reader or an LLM can absorb the project's intent without opening dozens of
files. The scope is deliberately tiny: an extension whitelist plus a UTF-8
read attempt. No gitignore parsing, no ``file`` command, no ripgrep, no
subprocess. It runs in milliseconds.

The output header uses a plain hyphen (no en-dash), matching the no-dash house
style and the original bash ``repo_snap`` header, which carried no dash either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List

# Text documentation extensions worth dumping. Everything else (images, PDFs,
# office docs, binaries) is skipped by suffix before any read is attempted.
DOC_EXTENSIONS = frozenset(
    {
        ".md",
        ".rst",
        ".txt",
        ".adoc",
        ".org",
        ".yml",
        ".yaml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
    }
)

_SEPARATOR = "=" * 42


@dataclass
class SnapshotResult:
    """Outcome of a snapshot run.

    ``docs_exists`` is False when the docs directory was absent; callers treat
    that as a warning and skip, never as an error (per the spec).
    """

    text: str
    root: Path
    docs_dir: Path
    docs_exists: bool
    file_count: int = 0
    skipped_binary: int = 0
    included: List[str] = field(default_factory=list)


def _iter_doc_files(docs_dir: Path) -> List[Path]:
    """Documentation files under ``docs_dir``, sorted for stable output."""
    files = [
        p
        for p in docs_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in DOC_EXTENSIONS
    ]
    return sorted(files)


def build_snapshot(root: Path, docs_subdir: str = "docs") -> SnapshotResult:
    """Build the docs snapshot text for ``root``.

    ``docs_subdir`` may be a name relative to ``root`` or an absolute path. A
    missing directory yields a short, valid snapshot with ``docs_exists`` set
    False so the caller can warn and move on.
    """
    root = Path(root).expanduser().resolve()
    docs_path = Path(docs_subdir).expanduser()
    docs_dir = docs_path if docs_path.is_absolute() else root / docs_path

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = [
        f"Repository Docs Snapshot - generated {stamp}",
        f"Root: {root}",
        _SEPARATOR,
    ]

    if not docs_dir.is_dir():
        header.append("")
        header.append(f"(no docs directory at {docs_dir})")
        return SnapshotResult(
            text="\n".join(header) + "\n",
            root=root,
            docs_dir=docs_dir,
            docs_exists=False,
        )

    blocks: List[str] = []
    included: List[str] = []
    skipped = 0
    for path in _iter_doc_files(docs_dir):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            blocks.append(f"\n--- FILE: {rel} ---\n[Skipped: binary or non-UTF8]")
            skipped += 1
            continue
        blocks.append(f"\n--- FILE: {rel} ---\n{content}")
        included.append(rel)

    text = "\n".join(header) + "\n" + "".join(blocks)
    if not text.endswith("\n"):
        text += "\n"
    return SnapshotResult(
        text=text,
        root=root,
        docs_dir=docs_dir,
        docs_exists=True,
        file_count=len(included),
        skipped_binary=skipped,
        included=included,
    )


def write_snapshot(result: SnapshotResult, output_path: Path) -> Path:
    """Write the snapshot text to ``output_path`` and return the resolved path."""
    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.text, encoding="utf-8")
    return out
