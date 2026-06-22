"""Saved repository shortcuts and target resolution.

Shortcuts live in a tab-separated file, ``label<TAB>/abs/path`` per line, under
the arachnid config directory. ``arachnid add/list/rm`` manage it; ``scan``,
``graph``, ``audit``, and ``snap`` resolve a target through it.

Config directory resolution, most specific first:
    * ``$ARACHNID_HOME``            (the config dir itself; used by tests)
    * ``$XDG_CONFIG_HOME/arachnid``
    * ``~/.config/arachnid``

Target resolution rule:
    * with a subpath: resolve the base (an existing directory, or a shortcut
      label) then append the subpath.
    * without a subpath: an existing directory is used as-is; otherwise the
      target is looked up as a shortcut label; an inline ``label/sub/path`` is
      also accepted. Anything else is an error.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class ShortcutError(Exception):
    """Raised for invalid labels, missing shortcuts, or unresolved targets."""


def config_dir() -> Path:
    """The arachnid config directory, honoring the env overrides above."""
    home = os.environ.get("ARACHNID_HOME")
    if home:
        return Path(home).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "arachnid"
    return Path.home() / ".config" / "arachnid"


def shortcuts_file() -> Path:
    """Path to the shortcuts TSV (parent created on demand)."""
    return config_dir() / "shortcuts.tsv"


def _ensure_file() -> Path:
    path = shortcuts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()
    return path


def load() -> Dict[str, str]:
    """Return the shortcuts as an ordered ``label -> path`` mapping."""
    path = shortcuts_file()
    if not path.exists():
        return {}
    result: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        label, _, target = line.partition("\t")
        if label and target:
            result[label] = target
    return result


def list_shortcuts() -> List[Tuple[str, str]]:
    """Shortcuts as a list of ``(label, path)`` pairs."""
    return list(load().items())


def _write(rows: Dict[str, str]) -> None:
    path = _ensure_file()
    lines = [f"{label}\t{target}" for label, target in rows.items()]
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def add(label: str, target: str) -> Path:
    """Save ``label`` pointing at ``target`` (must be an existing directory).

    Re-adding a label overwrites it. Returns the resolved absolute path.
    """
    if not LABEL_RE.match(label):
        raise ShortcutError(
            "label may only contain letters, numbers, dots, underscores, and hyphens."
        )
    resolved = Path(target).expanduser()
    if not resolved.is_dir():
        raise ShortcutError(f"path is not an existing directory: {target}")
    resolved = resolved.resolve()
    rows = load()
    rows[label] = str(resolved)
    _write(rows)
    return resolved


def remove(label: str) -> bool:
    """Remove ``label``. Returns True if it existed, False otherwise."""
    rows = load()
    if label not in rows:
        return False
    del rows[label]
    _write(rows)
    return True


def resolve(label: str) -> Optional[Path]:
    """Return the path for ``label`` if saved, else ``None``."""
    target = load().get(label)
    return Path(target) if target else None


def resolve_target(target: str, subpath: Optional[str] = None) -> Path:
    """Resolve a CLI target (directory or shortcut) to an absolute directory.

    Raises :class:`ShortcutError` with a precise message when the target cannot
    be resolved or the resolved path is not a directory.
    """
    direct = Path(target).expanduser()

    if subpath:
        if direct.is_dir():
            base = direct
        else:
            looked = resolve(target)
            if looked is None:
                raise ShortcutError(
                    f"target '{target}' is not a directory or a saved shortcut."
                )
            base = looked
        final = (base / subpath).expanduser()
        if not final.is_dir():
            raise ShortcutError(f"resolved path is not a directory: {final}")
        return final.resolve()

    if direct.is_dir():
        return direct.resolve()

    looked = resolve(target)
    if looked is not None:
        if not looked.is_dir():
            raise ShortcutError(f"shortcut '{target}' points at a missing directory: {looked}")
        return looked.resolve()

    # Inline ``label/sub/path`` form, matching the bash helper.
    if "/" in target:
        head, _, tail = target.partition("/")
        base = resolve(head)
        if base is not None:
            final = (base / tail).expanduser()
            if not final.is_dir():
                raise ShortcutError(f"resolved path is not a directory: {final}")
            return final.resolve()

    raise ShortcutError(
        f"target '{target}' is not a directory or a saved shortcut."
    )
