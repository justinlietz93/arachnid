"""Section 4: documentation snapshot (docs-only, pure Python).

``arachnid snap`` flattens a project's selected docs tree and its recognized
repository documentation into one text file. This preserves the docs-only
scope while capturing load-bearing files such as ``README.md`` and
``AGENTS.md`` that normally live outside ``docs/``. No gitignore parsing, no
``file`` command, no ripgrep, and no subprocess are used.

The output header uses a plain hyphen (no en-dash), matching the no-dash house
style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
from typing import List, Set

from ..core.file_utils import DEFAULT_EXCLUDED_DIRS

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

# Documentation that often lives at the repository root, or next to a package
# it governs. Files are recognized by stem so README.rst and AGENTS.txt work
# too, while arbitrary Markdown outside the selected docs tree stays out.
REPOSITORY_DOC_STEMS = frozenset(
    {
        "agents",
        "architecture",
        "authors",
        "changelog",
        "changes",
        "code_of_conduct",
        "contributing",
        "contributors",
        "decisions",
        "design",
        "development",
        "developing",
        "faq",
        "governance",
        "history",
        "install",
        "license",
        "licence",
        "maintainers",
        "migration",
        "notice",
        "notes",
        "overview",
        "readme",
        "roadmap",
        "requirements",
        "security",
        "spec",
        "specification",
        "status",
        "support",
        "todo",
        "validation",
    }
)

# Documentation discovery must not descend into vendored or generated trees
# merely to find their README files.
_DISCOVERY_EXCLUDED_DIRS = frozenset(
    set(DEFAULT_EXCLUDED_DIRS)
    | {
        "vendor",
        "bower_components",
        ".pnpm-store",
        ".yarn",
        "target",
        "coverage",
        "htmlcov",
        ".hypothesis",
    }
)


@dataclass
class SnapshotResult:
    """Outcome of a snapshot run.

    ``docs_exists`` is False when the selected docs directory was absent.
    Recognized repository documentation may still be present in that case.
    """

    text: str
    root: Path
    docs_dir: Path
    docs_exists: bool
    file_count: int = 0
    skipped_binary: int = 0
    included: List[str] = field(default_factory=list)


def _is_repository_doc(path: Path) -> bool:
    """Whether a file outside ``docs_dir`` is a recognized docs artifact."""
    stem = path.name.split(".", 1)[0].casefold()
    return stem in REPOSITORY_DOC_STEMS and (
        not path.suffix or path.suffix.lower() in DOC_EXTENSIONS
    )


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_doc_files(root: Path, docs_dir: Path) -> List[Path]:
    """Return selected docs plus recognized repository docs, stably sorted."""
    files: Set[Path] = set()
    if docs_dir.is_dir():
        files.update(
            path
            for path in docs_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in DOC_EXTENSIONS
        )

    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            directory
            for directory in directories
            if directory not in _DISCOVERY_EXCLUDED_DIRS
            and not (current_path / directory).is_symlink()
        ]
        for filename in filenames:
            path = current_path / filename
            if path.is_file() and not path.is_symlink() and _is_repository_doc(path):
                files.add(path)

    return sorted(files, key=lambda path: _display_path(path, root))


def build_snapshot(root: Path, docs_subdir: str = "docs") -> SnapshotResult:
    """Build the docs snapshot text for ``root``.

    ``docs_subdir`` may be a name relative to ``root`` or an absolute path. A
    missing directory still yields recognized repository docs, with
    ``docs_exists`` set False so the caller can warn and move on.
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

    docs_exists = docs_dir.is_dir()
    if not docs_exists:
        header.append("")
        header.append(f"(no docs directory at {docs_dir})")

    blocks: List[str] = []
    included: List[str] = []
    skipped = 0
    for path in _iter_doc_files(root, docs_dir):
        rel = _display_path(path, root)
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
        docs_exists=docs_exists,
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
