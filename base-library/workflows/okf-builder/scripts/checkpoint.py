#!/usr/bin/env python3
"""okf-builder: the deterministic convergence gate, run when the drain is dry.

Auto-canonicalizes (``ostler fmt`` write) then runs ``ostler doctor``, turning a dirty doctor into
worklist items the drain loop repairs before re-converging. Orphan / stub / coverage detection is
left to the recheck agent (it needs to read code and walk ``ostler trace``); this script owns only
the deterministic part.

**One item per file, not one per run and not one per node.** An earlier version packed every
finding into a single item whose context was the last 4000 characters of the findings JSON — so on
a book with more than a dozen findings the rest were dropped silently, and the loop churned without
ever seeing them. Truncation that looks like completion is the failure this gate exists to prevent.
Splitting per *node* fixed that but overcorrected: a component file with a hundred findings became
a hundred agent turns re-reading the same source. Per file, bounded by a chunk cap, keeps every
finding while letting one turn repair everything one reading explains.

**Two kinds, because two different repairs.** A dangling link or a mis-ordered bullet is mechanical:
the finding names its own remedy. A *missing required bullet* is not — the profile evolves, and
every book authored before a bullet became required is retroactively behind, with no way to derive
the value from the finding text. Those are emitted as ``backfill``, whose prompt requires the value
be grounded in source. Filed as ``fixup`` they would be "fixed" by writing an empty or ``none``
stub, which satisfies the linter while asserting something nobody checked.

Args: [repo_root] [features_root] [round]
Outputs JSON: {"checkpoint_clean","doctor_output","round","fixup_items","backfill_count"}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess
import sys


# Findings whose remedy cannot be read off the finding: the value has to come from the source.
# Everything else is mechanical and stays a `fixup`.
GROUNDED_CODES = frozenset({
    "missing-required-bullet",
    "unreachable-screen",
    # A collision is resolved by reading the two controls' real accessible names off the running
    # app or the source — renaming one to silence the check invents a label the UI does not have.
    "ambiguous-locator",
    "unnamed-interactive",
})


# How many findings one repair item may carry. A doc's findings overwhelmingly share a cause — the
# same component file, the same route module — so batching them is both cheaper and *better* work:
# the agent reads the source once and fixes everything it explains. The cap exists because that
# stops being true past a point, where a huge item invites a shallow pass over its tail.
MAX_FINDINGS_PER_ITEM = 25


def _repair_items(findings: list[dict], rnd: int) -> list[dict[str, str]]:
    """One item per file (chunked), carrying that file's findings and nothing else.

    Grouped by path, not by node. Per-node items make the drain re-derive the same context once per
    node: a component file with a hundred findings became a hundred turns, each re-reading the same
    route module to answer the same question. Per file, the agent opens it once — which is fewer
    turns *and* a more coherent repair, because sibling controls are usually wrong the same way.

    Findings stay sorted by line so an agent works top-down, and each chunk is bounded by
    ``MAX_FINDINGS_PER_ITEM``. The round is in the target because a finding that survives its
    repair must be re-queued next round rather than deduped away as already-seen.
    """
    groups: dict[str, list[dict]] = {}
    for finding in findings:
        groups.setdefault(str(finding.get("path", "")), []).append(finding)

    items = []
    for path, group in sorted(groups.items()):
        group.sort(key=lambda f: (f.get("line", 0), f.get("code", "")))
        chunks = [group[i:i + MAX_FINDINGS_PER_ITEM]
                  for i in range(0, len(group), MAX_FINDINGS_PER_ITEM)]
        for n, chunk in enumerate(chunks, start=1):
            grounded = any(f.get("code") in GROUNDED_CODES for f in chunk)
            # The suffix only appears when a file actually split, so the common target stays
            # readable — and two chunks of one file remain distinct worklist entries.
            suffix = f"#{n}" if len(chunks) > 1 else ""
            items.append({
                "kind": "backfill" if grounded else "fixup",
                "target": f"r{rnd}:{path}{suffix}",
                "context": json.dumps(chunk, indent=2),
            })
    return items


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "checkpoint_clean": "no", "doctor_output": "", "round": 0, "fixup_items": "[]",
        "backfill_count": 0,
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


def main(logger: logging.Logger) -> None:
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    features = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        rnd = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0
    except ValueError:
        rnd = 0
    rnd += 1

    if features:
        _run(["ostler", "fmt", features], repo_root)
    else:
        # No book to canonicalize: doctor still runs, but its findings can't be scoped to
        # a service, so every unrelated error in the repo lands on this round.
        logger.warning("no features root given — skipping ostler fmt; "
                       "doctor findings are unscoped")
    findings, out = _doctor_for_features(repo_root, features)
    clean = not findings

    fixups: list[dict[str, str]] = []
    backfills = 0
    if clean:
        logger.info("round %d: doctor is clean for %s — the gate converges",
                    rnd, features or repo_root)
    else:
        fixups = _repair_items(findings, rnd)
        backfills = sum(1 for i in fixups if i["kind"] == "backfill")
        logger.info("round %d: doctor reports %d error(s) across %d item(s) in %s — "
                    "queuing %d backfill + %d fixup item(s)", rnd, len(findings), len(fixups),
                    features or repo_root, backfills, len(fixups) - backfills)
    emit(checkpoint_clean="yes" if clean else "no", doctor_output=out[-4000:],
         round=rnd, fixup_items=json.dumps(fixups), backfill_count=backfills)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("checkpoint"))
