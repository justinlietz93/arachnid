"""Package-root resolution for the dependency graph (enhancement 2.3).

Unresolved imports of the project's own package (``vdm_rt.*`` when the code
lives under ``vdm_rt/`` but jedi could not statically follow a dynamic
re-export) inflate the unresolved count until it carries no signal. The
remedy: name the package root, mark those entries internal, and exclude them
from the headline unresolved statistic. They stay in the full unresolved log,
so nothing is hidden, the count just stops drowning in the project's own names.

The package name is detected from ``pyproject.toml`` or ``setup.py`` when not
supplied. Detection is best-effort and never raises; an unreadable manifest
simply yields ``None`` and the unresolved count behaves as it did before.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - 3.9 / 3.10
    _toml = None


def _normalize(name: str) -> str:
    """Distribution names use hyphens; import names use underscores."""
    return name.strip().strip("\"'").replace("-", "_")


def _toml_project_name(text: str) -> Optional[str]:
    """Read ``[project].name`` (or ``[tool.poetry].name``) without a TOML lib.

    Used on 3.9/3.10 where ``tomllib`` is absent. Scans for the first ``name =``
    assignment inside a ``[project]`` or ``[tool.poetry]`` table. Good enough for
    a manifest; the full parser is used whenever it is available.
    """
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section in ("project", "tool.poetry"):
            m = re.match(r"name\s*=\s*(.+)$", line)
            if m:
                return _normalize(m.group(1))
    return None


def detect_package_root(root: Path) -> Optional[str]:
    """Best-effort import name of the project's own top-level package.

    Order of evidence:
      1. ``pyproject.toml`` ``[project].name`` / ``[tool.poetry].name``.
      2. ``setup.py`` ``name=`` argument.
      3. A single obvious top-level package directory (one ``__init__.py``
         dir that is not ``tests`` / ``docs`` / ``examples``).
    Returns the import-normalized name, or ``None`` if nothing is conclusive.
    """
    root = Path(root).resolve()

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            if _toml is not None:
                data = _toml.loads(text)
                name = data.get("project", {}).get("name") or (
                    data.get("tool", {}).get("poetry", {}).get("name")
                )
                if name:
                    return _normalize(name)
            else:
                name = _toml_project_name(text)
                if name:
                    return name
        except Exception:
            pass

    setup_py = root / "setup.py"
    if setup_py.is_file():
        try:
            text = setup_py.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", text)
            if m:
                return _normalize(m.group(1))
        except Exception:
            pass

    candidates: List[str] = []
    skip = {"tests", "test", "docs", "doc", "examples", "example", "src"}
    try:
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if child.name in skip:
                continue
            if (child / "__init__.py").exists() and child.name.isidentifier():
                candidates.append(child.name)
    except OSError:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


def _import_head(raw_import: str) -> str:
    """Top-level dotted name of an import, ignoring leading relative dots."""
    return raw_import.lstrip(".").split(".")[0]


def tag_internal_unresolved(
    unresolved: List[dict], package_root: Optional[str]
) -> None:
    """Mark each unresolved entry whose top-level name is the package root.

    Mutates entries in place, adding ``internal: bool``. When ``package_root``
    is ``None`` every entry is marked external, which preserves the original
    unresolved count exactly.
    """
    pkg = _normalize(package_root) if package_root else None
    for entry in unresolved:
        head = _import_head(str(entry.get("import", "")))
        entry["internal"] = bool(pkg) and head == pkg
