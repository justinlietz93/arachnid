"""Semantic import indexing built on jedi.

Division of labor:

* parso (jedi's own error-tolerant parser) locates every import statement,
  including imports nested in ``if`` blocks, ``try`` blocks, functions and
  methods. Error recovery means a file with broken syntax still yields its
  intact imports.
* jedi resolves each imported name to the file where it is actually defined,
  following aliases, relative imports, ``sys.path`` logic, virtualenvs, and
  re-exports through ``__init__.py``.

No regex. No stdlib ``ast``.

The directory-exclusion set lives in :mod:`arachnid.core.file_utils` so the
graph and the audit skip exactly the same directories, including the tool's
own output (enhancement 2.2).
"""

from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Sequence

import jedi
import parso

from ..core.file_utils import (
    DEFAULT_EXCLUDED_DIRS,
    glob_match as _glob_match,
    rel_posix as _rel_posix,
)

__all__ = [
    "DEFAULT_EXCLUDED_DIRS",
    "ResolvedImport",
    "FileScanResult",
    "iter_python_files",
    "detect_src_roots",
    "detect_environment",
    "scan_file",
    "scan_project",
]


@dataclass(frozen=True)
class ResolvedImport:
    """One imported name, resolved by jedi to its defining file."""

    source: Path  # file containing the import statement
    raw_path: str  # dotted path as written, e.g. "..engine.Engine"
    name: str  # final name in the path, e.g. "Engine"
    line: int  # line of the import in the source file
    is_relative: bool
    target: Optional[Path]  # defining file; None if unresolved or builtin
    full_name: Optional[str]  # jedi full name, e.g. "transcribe.engine.Engine"
    target_type: Optional[str]  # jedi type: module / class / function / ...
    via_module: bool = False  # name untraceable; resolved to its module instead


@dataclass
class FileScanResult:
    """All resolved imports for one source file."""

    path: Path
    imports: List[ResolvedImport] = field(default_factory=list)
    error: Optional[str] = None


def iter_python_files(
    root: Path,
    excluded_dirs: frozenset = DEFAULT_EXCLUDED_DIRS,
    exclude_globs: Sequence[str] = (),
) -> Iterator[Path]:
    """Yield every .py file under ``root``, honoring exclusions.

    Hidden directories (dot-prefixed) and the default tool/venv/output
    directories are skipped. ``exclude_globs`` are matched against the path
    relative to ``root`` (posix form) and against the bare filename.
    """
    root = Path(root).resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in excluded_dirs
            and not d.startswith(".")
            and not _glob_match(_rel_posix(rel_dir / d), exclude_globs)
        )
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            rel = _rel_posix(rel_dir / fn)
            if _glob_match(rel, exclude_globs):
                continue
            yield Path(dirpath) / fn


def detect_src_roots(
    root: Path,
    excluded_dirs: frozenset = DEFAULT_EXCLUDED_DIRS,
    exclude_globs: Sequence[str] = (),
) -> List[Path]:
    """Find nested src-layout import roots under ``root``.

    A directory named ``src`` whose immediate children include a package
    (a directory with ``__init__.py``) or a module is a sys.path root in
    src-layout projects. Vendored repos bury these below the scan root,
    where jedi's own per-file heuristics cannot help code that imports the
    package from outside it. Without these roots on the path, every
    absolute import of the vendored package is unresolvable.
    """
    root = Path(root).resolve()
    found: List[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in excluded_dirs
            and not d.startswith(".")
            and not _glob_match(_rel_posix(rel_dir / d), exclude_globs)
        )
        here = Path(dirpath)
        if here.name != "src" or here == root:
            continue
        try:
            children = list(here.iterdir())
        except OSError:
            continue
        if any(
            (c.is_dir() and (c / "__init__.py").exists()) or c.suffix == ".py"
            for c in children
        ):
            found.append(here)
    return found


def detect_environment(root: Path) -> Optional[Path]:
    """Find the project's own virtualenv at ``root/.venv`` or ``root/venv``.

    Third-party imports resolve only against an environment where those
    packages are installed. When arachnid itself runs from an isolated
    install (pipx), its default environment knows nothing beyond the
    stdlib, so the scanned project's venv is the right one to ask.
    """
    root = Path(root).resolve()
    for name in (".venv", "venv"):
        candidate = root / name
        if (candidate / "bin" / "python").exists() or (
            candidate / "Scripts" / "python.exe"
        ).exists():
            return candidate
    return None


def _iter_all_imports(scope) -> Iterator:
    """Recursively yield import nodes from a parso scope.

    ``Scope.iter_imports`` covers the scope body including flow blocks
    (if / try / while) but not nested function or class scopes, so we
    descend into those explicitly. This is what captures lazy in-function
    imports.
    """
    yield from scope.iter_imports()
    for func in scope.iter_funcdefs():
        yield from _iter_all_imports(func)
    for cls in scope.iter_classdefs():
        yield from _iter_all_imports(cls)


def scan_file(file_path: Path, project: jedi.Project) -> FileScanResult:
    """Resolve every import in one file against the project workspace."""
    result = FileScanResult(path=file_path)
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.error = f"unreadable: {exc}"
        return result

    try:
        script = jedi.Script(code=source, path=str(file_path), project=project)
        module = parso.parse(source)  # error recovery is on by default
    except Exception as exc:  # pragma: no cover - jedi/parso internal failure
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    for import_node in _iter_all_imports(module):
        level = getattr(import_node, "level", 0) or 0
        try:
            paths = import_node.get_paths()
        except Exception:
            continue
        for chain in paths:
            if not chain:
                continue
            leaf = chain[-1]
            raw = "." * level + ".".join(n.value for n in chain)
            resolved = _resolve_leaf(script, leaf)
            via_module = False
            if resolved is None and len(chain) >= 2:
                # The name itself is untraceable (commonly a lazy
                # __getattr__ re-export). The module it was imported from
                # still resolves; an edge to the module is true and beats
                # reporting nothing.
                resolved = _resolve_leaf(script, chain[-2])
                via_module = resolved is not None
            result.imports.append(
                ResolvedImport(
                    source=file_path,
                    raw_path=raw,
                    name=leaf.value,
                    line=leaf.line,
                    is_relative=level > 0,
                    target=resolved.module_path if resolved else None,
                    full_name=resolved.full_name if resolved else None,
                    target_type=resolved.type if resolved else None,
                    via_module=via_module,
                )
            )
    return result


def _resolve_leaf(script: jedi.Script, leaf):
    """jedi ``goto`` with import following; returns the best Name or None."""
    try:
        defs = script.goto(
            leaf.line,
            leaf.column,
            follow_imports=True,
            follow_builtin_imports=True,
        )
    except Exception:
        return None
    if not defs:
        return None
    for d in defs:
        if d.module_path is not None:
            return d
    return defs[0]


# --------------------------------------------------------------------------
# Project-level driver (sequential or multiprocess)
# --------------------------------------------------------------------------

_WORKER_PROJECT: Optional[jedi.Project] = None


def _init_worker(project_kwargs: dict) -> None:
    global _WORKER_PROJECT
    _WORKER_PROJECT = jedi.Project(**project_kwargs)


def _scan_worker(file_path: str) -> FileScanResult:
    assert _WORKER_PROJECT is not None
    return scan_file(Path(file_path), _WORKER_PROJECT)


def scan_project(
    root: Path,
    *,
    exclude_globs: Sequence[str] = (),
    excluded_dirs: frozenset = DEFAULT_EXCLUDED_DIRS,
    sys_paths: Sequence[Path] = (),
    environment_path: Optional[Path] = None,
    auto_src: bool = True,
    jobs: int = 1,
    progress: Optional[Callable[[int, int, Path], None]] = None,
) -> List[FileScanResult]:
    """Scan every Python file under ``root`` and resolve its imports.

    ``root`` is always added to jedi's sys.path so absolute imports of
    top-level packages in the repo resolve without configuration. With
    ``auto_src`` (default), nested src-layout roots found by
    ``detect_src_roots`` are added too. Explicit ``sys_paths`` come first
    and win name conflicts. ``environment_path`` points jedi at a
    virtualenv so third-party imports resolve against the environment the
    code actually runs in.
    """
    root = Path(root).resolve()
    files = list(iter_python_files(root, excluded_dirs, exclude_globs))
    path_list: List[str] = [str(root)]
    for p in sys_paths:
        s = str(Path(p).resolve())
        if s not in path_list:
            path_list.append(s)
    if auto_src:
        for src in detect_src_roots(root, excluded_dirs, exclude_globs):
            s = str(src)
            if s not in path_list:
                path_list.append(s)
    project_kwargs: dict = {"path": str(root), "added_sys_path": path_list}
    if environment_path:
        project_kwargs["environment_path"] = str(Path(environment_path).resolve())

    results: List[FileScanResult] = []
    total = len(files)
    if jobs <= 1:
        project = jedi.Project(**project_kwargs)
        for i, f in enumerate(files, 1):
            results.append(scan_file(f, project))
            if progress:
                progress(i, total, f)
    else:
        # spawn, not fork: forked workers would inherit the parent's jedi
        # compiled-subprocess pipe and cross-talk on it, corrupting results.
        ctx = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=jobs,
            mp_context=ctx,
            initializer=_init_worker,
            initargs=(project_kwargs,),
        ) as pool:
            for i, res in enumerate(
                pool.map(_scan_worker, [str(f) for f in files], chunksize=4), 1
            ):
                results.append(res)
                if progress:
                    progress(i, total, res.path)
    return results
