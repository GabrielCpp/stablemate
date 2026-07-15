#!/usr/bin/env python3
"""okf-builder: the deterministic convergence gate, run when the drain is dry.

Auto-canonicalizes (``ostler fmt`` write) then runs ``ostler doctor``. A dirty
doctor is turned into a single ``fixup`` worklist item carrying the finding text,
so the drain loop's investigator fixes it by its mechanical remedy and re-converges.
Orphan / stub / coverage detection is left to the recheck agent (it needs to read
code and walk ``ostler trace``); this script owns only the mechanical part.

Args: [repo_root] [features_root] [round]
Outputs JSON: {"checkpoint_clean","doctor_output","round","fixup_items"}
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "checkpoint_clean": "no", "doctor_output": "", "round": 0, "fixup_items": "[]",
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _run(args: list[str], cwd: str) -> str:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return f"[okf-builder] {' '.join(args)} failed: {exc}"


def _doctor_for_features(repo_root: str, features: str) -> tuple[list[dict], str]:
    """Return only doctor errors located in the service book being built.

    A monorepo's unrelated epic/spec history may already contain doctor findings. Those cannot be
    repaired by a docs/features-only workflow and must not prevent one service book converging.
    """
    try:
        p = subprocess.run(
            ["ostler", "doctor", "--json"], cwd=repo_root, capture_output=True, text=True,
            timeout=300,
        )
        data = json.loads(p.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return [{"severity": "error", "message": str(exc), "path": features}], str(exc)
    try:
        prefix = Path(features).resolve().relative_to(Path(repo_root).resolve()).as_posix().rstrip("/")
    except ValueError:
        prefix = Path(features).as_posix().rstrip("/")
    findings = [
        finding for finding in data.get("findings", [])
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and (str(finding.get("path", "")) == prefix
             or str(finding.get("path", "")).startswith(prefix + "/"))
    ]
    return findings, json.dumps(findings, indent=2)


def main() -> None:
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    features = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        rnd = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0
    except ValueError:
        rnd = 0
    rnd += 1

    if features:
        _run(["ostler", "fmt", features], repo_root)
    findings, out = _doctor_for_features(repo_root, features)
    clean = not findings

    fixups: list[dict[str, str]] = []
    if not clean:
        fixups = [{"kind": "fixup", "target": f"doctor-r{rnd}",
                   "context": out[-4000:]}]
    emit(checkpoint_clean="yes" if clean else "no", doctor_output=out[-4000:],
         round=rnd, fixup_items=json.dumps(fixups))


if __name__ == "__main__":
    main()
