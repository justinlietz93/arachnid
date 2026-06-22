"""Docs-only snapshot: flatten a project's documentation into one text file."""

from __future__ import annotations

from .snapshot import (
    DOC_EXTENSIONS,
    SnapshotResult,
    build_snapshot,
    write_snapshot,
)

__all__ = [
    "DOC_EXTENSIONS",
    "SnapshotResult",
    "build_snapshot",
    "write_snapshot",
]
