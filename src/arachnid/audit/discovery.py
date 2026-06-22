from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Any

from .defaults import TEXT_EXTENSIONS

def normalize_path(path: Path | str) -> str:
    return Path(path).as_posix().strip("/")


def always_ignored(path: str, is_dir: bool, cfg: dict[str, Any]) -> bool:
    path = normalize_path(path)
    for raw in cfg["scan"].get("always_ignore", []):
        pattern = str(raw).strip()
        if not pattern:
            continue
        directory_only = pattern.endswith("/")
        clean = normalize_path(pattern.rstrip("/"))
        if directory_only and not is_dir and not path.startswith(clean + "/"):
            continue
        if path == clean or path.startswith(clean + "/") or fnmatch.fnmatch(path, clean):
            return True
    return False


def git_files(root: Path, cfg: dict[str, Any]) -> list[str] | None:
    if not cfg["scan"].get("use_git_exclude_standard", True):
        return None
    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        listed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
            check=False,
        )
        if listed.returncode != 0:
            return None
        return sorted(
            x.decode("utf-8", "replace") for x in listed.stdout.split(b"\0") if x
        )
    except OSError:
        return None


def gitignore_rules(root: Path) -> list[tuple[str, bool, bool, bool]]:
    path = root / ".gitignore"
    if not path.exists():
        return []
    rules: list[tuple[str, bool, bool, bool]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        line = line[1:].strip() if negated else line
        directory_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = line.startswith("/")
        line = line.lstrip("/")
        if line:
            rules.append((line, negated, directory_only, anchored))
    return rules


def rule_matches(path: str, is_dir: bool, rule: tuple[str, bool, bool, bool]) -> bool:
    pattern, _, directory_only, anchored = rule
    if directory_only and not is_dir:
        return False
    choices = [path] if anchored or "/" in pattern else [Path(path).name, path]
    for choice in choices:
        if fnmatch.fnmatch(choice, pattern):
            return True
        if not anchored and "/" not in pattern:
            if any(fnmatch.fnmatch(part, pattern) for part in path.split("/")):
                return True
    return False


def ignored_by_gitignore(
    path: str, is_dir: bool, rules: list[tuple[str, bool, bool, bool]]
) -> bool:
    ignored = False
    for rule in rules:
        if rule_matches(path, is_dir, rule):
            ignored = not rule[1]
    return ignored


def manual_files(root: Path, cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    rules = gitignore_rules(root)
    kept: list[str] = []
    ignored: list[str] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        next_dirs: list[str] = []
        for name in dirs:
            item = normalize_path((current_path / name).relative_to(root))
            if always_ignored(item, True, cfg) or ignored_by_gitignore(item, True, rules):
                ignored.append(item + "/")
            else:
                next_dirs.append(name)
        dirs[:] = next_dirs
        for name in files:
            item = normalize_path((current_path / name).relative_to(root))
            if always_ignored(item, False, cfg) or ignored_by_gitignore(
                item, False, rules
            ):
                ignored.append(item)
            else:
                kept.append(item)
    return sorted(kept), sorted(ignored)


def file_list(root: Path, cfg: dict[str, Any]) -> tuple[list[str], str, list[str]]:
    found = git_files(root, cfg)
    if found is not None:
        ignored = [x for x in found if always_ignored(x, False, cfg)]
        kept = [x for x in found if not always_ignored(x, False, cfg)]
        return kept, "git ls-files --exclude-standard", ignored
    kept, ignored = manual_files(root, cfg)
    return kept, "manual .gitignore parser", ignored


def is_text_file(path: Path, cfg: dict[str, Any]) -> bool:
    suffix = path.suffix.lower()
    include = set(cfg["scan"].get("include_extensions", []))
    exclude = set(cfg["scan"].get("exclude_extensions", []))
    if suffix in exclude or (include and suffix not in include):
        return False
    if suffix in TEXT_EXTENSIONS:
        return True
    try:
        chunk = path.read_bytes()[:4096]
        if b"\0" in chunk:
            return False
        chunk.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def path_tokens(path: str) -> set[str]:
    out: set[str] = set()
    p = Path(path)
    for part in p.parts + (p.stem,):
        lowered = part.lower().replace("-", "_")
        out.add(lowered)
        out.update(x for x in lowered.split("_") if x)
    return out


def matches(path: str, patterns: list[str]) -> bool:
    lowered = normalize_path(path).lower()
    tokens = path_tokens(path)
    for raw in patterns:
        pattern = str(raw).lower().strip()
        if not pattern:
            continue
        if pattern in tokens or fnmatch.fnmatch(lowered, pattern):
            return True
    return False

