"""arachnid: repository graphing, auditing, and documentation snapshotting.

One package, one CLI. The three subsystems are independent and importable on
their own:

    from arachnid.graph import run_graph
    from arachnid.audit import run_audit
    from arachnid.snapshot import build_snapshot

or driven together through the orchestrator:

    from arachnid import run_scan
"""

from __future__ import annotations

from ._version import __version__
from .orchestrator import ScanResult, run_scan

__all__ = [
    "__version__",
    "ScanResult",
    "run_scan",
]
