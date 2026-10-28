"""Where a test's epics live: the per-test artifacts dir, never the repository."""

from __future__ import annotations

import os
from pathlib import Path


def epics_root() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve() / "epics"
