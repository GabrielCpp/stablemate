#!/usr/bin/env python3
"""Remove stale QA evidence before context generation and planning.

Both pipeline and standalone QA use this node before context generation:

1. ``spec_dir`` must exist so context generation and planning can write inputs.
2. The disposable ``qa/`` output directory is removed in full.
3. The stale root ``qa-evidence.json`` verdict is removed as well.

The Ostler runner recreates ``qa/`` and owns its log, manifest, and evidence.
This script deliberately does not recreate or author any runner output.

Args: <spec_dir_abs>
Outputs JSON: {"qa_cleared": "yes"}
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    spec_dir = (
        Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and sys.argv[1] else None
    )
    if spec_dir:
        spec_dir.mkdir(parents=True, exist_ok=True)
        qa_dir = spec_dir / "qa"
        if qa_dir.exists():
            shutil.rmtree(qa_dir)
        evidence_path = spec_dir / "qa-evidence.json"
        if evidence_path.exists():
            evidence_path.unlink()

    print(json.dumps({"qa_cleared": "yes"}))


if __name__ == "__main__":
    main()
