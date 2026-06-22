"""Shared file-discovery utilities.

This module owns the single source of truth for which directories every
scanner skips. Enhancement 2.2 (auto-exclude output directories) lives here:
the tool must never scan its own output, or it flags the reports it just
wrote. The graph indexer and the audit walker both pull their exclusion set
from here so the behavior cannot drift between the two.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Sequence

# Directories the tool itself writes. Scanning these is self-flagellation:
# the audit would flag its own JSON reports, the graph would index the docs
# snapshot. They are always skipped, in both the graph and the audit.
OUTPUT_DIRS = frozenset(
    {
        ".arachnid_scans",
        ".repo-audit-reports",
        ".repo-standards-reports",
    }
)

# Environment, cache, and build directories that are never project source.
# This is the union historically split between repo-graph (DEFAULT_EXCLUDED_DIRS)
# and repo-audit (always_ignore). Kept in one place so a directory added here
# is honored by every command.
TOOLING_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        ".direnv",
        "node_modules",
        "build",
        "dist",
        ".eggs",
        "site-packages",
    }
)

# What the graph indexer excludes by default: tooling, env, and output dirs.
DEFAULT_EXCLUDED_DIRS = frozenset(TOOLING_DIRS | OUTPUT_DIRS)

# Directory-form entries (trailing slash) for the audit's gitignore-style
# always_ignore list. Only the output directories need adding there; the
# audit already honors .git via the same list and prunes the rest through
# .gitignore / git ls-files. Listing the output dirs guarantees they are
# skipped even in a repo with no .gitignore and no git.
ALWAYS_IGNORE_DIRS = tuple(sorted(f"{name}/" for name in OUTPUT_DIRS | {".git"}))


def rel_posix(p: Path) -> str:
    """Relative path as a clean posix string, with any leading ``./`` removed."""
    s = p.as_posix()
    return s[2:] if s.startswith("./") else s


def glob_match(rel: str, globs: Sequence[str]) -> bool:
    """True if ``rel`` (or its bare filename) matches any of ``globs``.

    Patterns are matched against both the relative posix path and the bare
    filename so a glob like ``*.generated.py`` works regardless of depth and
    ``build/*`` works as a path anchor.
    """
    name = Path(rel).name
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(name, g) for g in globs)


def should_ignore_dir(
    name: str,
    rel: str,
    *,
    excluded_dirs: frozenset = DEFAULT_EXCLUDED_DIRS,
    exclude_globs: Sequence[str] = (),
) -> bool:
    """Decide whether a directory is pruned from a walk.

    A directory is skipped when its name is in ``excluded_dirs``, when it is
    dot-prefixed (hidden), or when its relative path matches an exclude glob.
    """
    if name in excluded_dirs:
        return True
    if name.startswith("."):
        return True
    if exclude_globs and glob_match(rel, exclude_globs):
        return True
    return False
