from __future__ import annotations

from typing import Any

from ..core.file_utils import ALWAYS_IGNORE_DIRS

DEFAULT_CONFIG: dict[str, Any] = {
    "root": None,
    "output_dir": ".repo-audit-reports",
    "scan": {
        "use_git_exclude_standard": True,
        # Output directories are always pruned so the audit never flags its
        # own reports (enhancement 2.2). Sourced from core.file_utils so the
        # graph and the audit agree on what to skip.
        "always_ignore": list(ALWAYS_IGNORE_DIRS),
        "include_extensions": [],
        "exclude_extensions": [],
        # Extra exclude globs (CLI --exclude appends here, enhancement 2.2).
        "exclude_globs": [],
    },
    "loc": {
        "warning": 250,
        "hard": 400,
        "router_hard": 300,
        "schema_model_requires_justification_above": 400,
        "schema_model_hard_with_justification": 500,
    },
    # Enhancement 2.1: per-extension LOC limits. ``default`` applies to any
    # extension without an override. Documentation and config get generous
    # ceilings so a long but legitimate README or lockfile is not a violation.
    "loc_limits": {
        "default": {"warning": 250, "hard": 400},
        "overrides": {
            ".md": {"warning": 1000, "hard": 2000},
            ".rst": {"warning": 1000, "hard": 2000},
            ".json": {"warning": 300, "hard": 500},
            ".yml": {"warning": 200, "hard": 400},
            ".yaml": {"warning": 200, "hard": 400},
            ".txt": {"warning": 500, "hard": 1000},
        },
    },
    "directories": {
        "warning_files": 10,
        "hard_files": 15,
        "leaf_warning_files": 15,
        "leaf_hard_files": 20,
    },
    "routers": {
        "enabled": True,
        # Text, documentation, and configuration files can contain router-like
        # names (for example, ``router.md``), but are never implementation routers.
        "non_code_extensions": [
            ".md",
            ".rst",
            ".txt",
            ".json",
            ".yml",
            ".yaml",
            ".toml",
            ".cfg",
            ".ini",
            ".csv",
            ".xml",
            ".html",
            ".css",
        ],
        "patterns": [
            "controller",
            "orchestrator",
            "router",
            "coordinator",
            "dispatcher",
            "hub",
            "bus",
        ],
        "logic_warning_lines": 50,
        "expect_sibling_folder_above_loc": 150,
    },
    "schema_models": {
        "patterns": [
            "schema",
            "schemas",
            "model",
            "models",
            "record",
            "records",
            "type",
            "types",
            "dto",
            "contract",
            "contracts",
            "constants",
        ],
        "justification_markers": [
            "SIZE_JUSTIFICATION:",
            "LOC_JUSTIFICATION:",
            "FILE_SIZE_JUSTIFICATION:",
        ],
        "justification_search_first_lines": 50,
    },
    # Enhancement 2.5: test-coverage heuristic. Source files above ``min_loc``
    # without a matching test file are flagged ``untested_module`` at info
    # severity (never fails the build on its own).
    "coverage": {
        "enabled": True,
        "min_loc": 200,
        "tests_dir": "tests",
    },
    # Enhancements 2.6 - 2.8: optional AST scanners. All opt-in via CLI flags.
    "checks": {
        # 2.6 bus / event-schema scanner.
        "event_files": [
            "bus",
            "events",
            "event_bus",
            "eventbus",
            "adc",
            "pubsub",
            "observation",
            "observations",
        ],
        "event_producers": ["publish", "emit", "post", "dispatch", "send"],
        "event_consumers": [
            "consume",
            "subscribe",
            "on",
            "handle",
            "update_from",
            "register",
        ],
        # 2.7 hot-loop redundancy check.
        "loop_file_globs": ["*loop*.py", "*main*.py"],
        "loop_redundant_pattern": "(count|scan|traverse|components|entropy|metrics)",
        # 2.8 attribute-ownership mismatch.
        "attr_files": ["state", "runtime", "loop"],
        "attr_pattern": "^_",
    },
}

TEXT_EXTENSIONS = {
    ".py",
    ".pyi",
    ".md",
    ".txt",
    ".rst",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
    ".html",
    ".xml",
    ".csv",
    ".sql",
    ".rs",
    ".go",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".lean",
    ".qbl",
    ".germ",
}
