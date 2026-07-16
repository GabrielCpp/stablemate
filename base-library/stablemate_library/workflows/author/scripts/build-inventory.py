#!/usr/bin/env python3
"""Report the surface set the coverage gate will check — ostler features + survey units.

Under the OKF model every feature doc under ``features_dir`` is itself a typed Concept
(``type: feature`` in its front-matter), and ostler reads the feature set directly from
those Concepts (``Ostler.list("feature")``). There is no derived feature
``inventory.json`` to (re)build anymore — the source IS the manifest for feature docs.

The manifest path (argv[2], ``cfg.surface_manifest``) now names the OTHER producer: a
**survey-produced unit manifest** (emitted by the surveyor workflow — same contract,
different producer, opt-in by presence). When it exists on disk its units join the
surface count so the run log shows exactly the set ``verify-surface-coverage.py`` will
gate on; this node still never writes anything.

Always flows on: with no feature Concepts and no unit manifest the count is 0 and the
coverage gate downstream is inert, exactly as before.

Reads the feature set through the in-process ``ostler`` Python API (``Ostler.list``).

Args:
    argv[1]  features_dir  : repo-relative feature-docs root (default docs/features; informational)
    argv[2]  manifest      : survey-produced unit manifest (read for the count when present)

Outputs JSON: {"inventory_built": "skip"|"manifest", "inventory_path": "<source>",
               "surface_count": <int>, "inventory_note": "<human note>"}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from ostler import Ostler


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def feature_count(okf: Ostler) -> int:
    """Count of typed feature Concepts ostler reads directly (0 when there are none)."""
    return len(okf.list("feature"))


def unit_count(root: Path, manifest_rel: str) -> int:
    """Units in a survey-produced manifest, or 0 when absent/unreadable (opt-in by presence)."""
    if not manifest_rel:
        return 0
    path = root / manifest_rel
    if not path.is_file():
        return 0
    try:
        units = json.loads(path.read_text(encoding="utf-8")).get("units")
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        return 0
    return len(units) if isinstance(units, list) else 0


def main() -> None:
    features_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/features"
    manifest_rel = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    root = find_repo_root()
    okf = Ostler(root)
    n = feature_count(okf)
    m = unit_count(root, manifest_rel)
    note = (
        f"feature set is read directly from {n} typed feature Concept(s) under {features_rel} "
        "(ostler feature Concepts) — no inventory.json is built under the OKF model"
    )
    if m:
        note += f"; plus {m} survey-produced unit(s) from {manifest_rel} (surveyor manifest)"
    print(json.dumps({
        "inventory_built": "manifest" if m else "skip",
        "inventory_path": manifest_rel if m else features_rel,
        "surface_count": n + m,
        "inventory_note": note,
    }))


if __name__ == "__main__":
    main()
