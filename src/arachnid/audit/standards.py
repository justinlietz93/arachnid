"""Standards resolution helpers for the audit (enhancement 2.1).

Per-extension LOC limits let documentation and config carry generous ceilings
while source stays tight. The resolver reads the ``loc_limits`` block when it
exists and falls back to the flat ``loc`` block otherwise, so an old config
with no ``loc_limits`` behaves exactly as before.
"""

from __future__ import annotations

from typing import Any, Tuple


def resolve_loc_limits(ext: str, cfg: dict[str, Any]) -> Tuple[int, int]:
    """Return ``(warning, hard)`` LOC limits for a file extension.

    Resolution order:
      1. ``loc_limits.overrides[ext]`` when present.
      2. ``loc_limits.default`` otherwise.
      3. The flat ``loc.warning`` / ``loc.hard`` when ``loc_limits`` is absent.

    The extension is matched case-insensitively and must include the dot
    (``".md"``). A file with no extension uses the default.
    """
    flat_warning = int(cfg["loc"]["warning"])
    flat_hard = int(cfg["loc"]["hard"])

    limits = cfg.get("loc_limits")
    if not isinstance(limits, dict):
        return flat_warning, flat_hard

    overrides = limits.get("overrides") or {}
    default = limits.get("default") or {}

    entry = overrides.get(ext.lower())
    if not isinstance(entry, dict):
        entry = default if isinstance(default, dict) else {}

    warning = int(entry.get("warning", default.get("warning", flat_warning)))
    hard = int(entry.get("hard", default.get("hard", flat_hard)))
    return warning, hard
