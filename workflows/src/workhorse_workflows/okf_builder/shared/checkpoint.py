"""The deterministic convergence gate, run when the drain is dry.

Ported from `base-library/workflows/okf-builder/scripts/checkpoint.py`. Two divergences,
both deliberate:

* **ostler is called as a library, not as a subprocess.** The script shelled out to
  `ostler fmt <features>` and `ostler doctor --json` and parsed the stdout back; here it
  is `run_fmt(okf.graph, [features])` and `okf.doctor()`, which is what the CLI itself
  does one layer down — `ostler/ostler/api.py` is "the *library* face of the `ostler` CLI
  … the CLI merely `json.dumps` what these return". This is a *convergence*, not a
  narrowing: `auto-waive.py` already computed the identical scoped finding set through
  `okf.doctor()`, and said in its own docstring that it "mirrors
  checkpoint._doctor_for_features" — so the two nodes disagreed on mechanism while
  claiming to agree on result. What the subprocess bought was crash isolation, and what
  replaces it is the same `except` arm the script had for a failed `subprocess.run`.
* **The graph is reloaded between fmt and doctor.** `run_fmt` writes files, and
  `Ostler.graph` is a cached snapshot whose contract says a mutation invalidates it. The
  subprocess version got this for free by starting a second process; in-process it has to
  be asked for, or doctor reads the book as it was *before* canonicalization.
* **The rename.** The node is `checkpoint_book`, not `checkpoint`, because the state that
  calls it is `checkpoint` and a method body resolves a free name against module globals.
  Both spellings would work; only one is readable.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ostler import Ostler
from ostler.fmt import run_fmt
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Checkpoint

#: Findings whose remedy cannot be read off the finding: the value has to come from the
#: source. Everything else is mechanical and stays a `fixup`.
GROUNDED_CODES = frozenset({
    "missing-required-bullet",
    "unreachable-screen",
    # A collision is resolved by reading the two controls' real accessible names off the
    # running app or the source — renaming one to silence the check invents a label the UI
    # does not have.
    "ambiguous-locator",
    "unnamed-interactive",
    # Splitting one overlong bullet into several needs the source to say which clauses are
    # actually separate requirements; cutting it on punctuation invents obligations.
    "overlong-normative-bullet",
})

#: How many findings one repair item may carry. A doc's findings overwhelmingly share a
#: cause — the same component file, the same route module — so batching them is both
#: cheaper and *better* work: the agent reads the source once and fixes everything it
#: explains. The cap exists because that stops being true past a point, where a huge item
#: invites a shallow pass over its tail.
MAX_FINDINGS_PER_ITEM = 25


def _repair_items(findings: list[dict], rnd: int) -> list[dict[str, str]]:
    """One item per file (chunked), carrying that file's findings and nothing else.

    Grouped by path, not by node. Per-node items make the drain re-derive the same context
    once per node: a component file with a hundred findings became a hundred turns, each
    re-reading the same route module to answer the same question. Per file, the agent opens
    it once — which is fewer turns *and* a more coherent repair, because sibling controls
    are usually wrong the same way.

    Findings stay sorted by line so an agent works top-down, and each chunk is bounded by
    `MAX_FINDINGS_PER_ITEM`. The round is in the target because a finding that survives its
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
            # The suffix only appears when a file actually split, so the common target
            # stays readable — and two chunks of one file remain distinct worklist entries.
            suffix = f"#{n}" if len(chunks) > 1 else ""
            items.append({
                "kind": "backfill" if grounded else "fixup",
                "target": f"r{rnd}:{path}{suffix}",
                "context": json.dumps(chunk, indent=2),
            })
    return items


def _signature(findings: list[dict]) -> str:
    """A stable fingerprint of a finding SET, order-independent.

    Keyed on `(code, path, line, ref)` — the identity of a finding, not its prose (a
    reworded message must not read as a different finding). Empty findings → `""` so a
    clean round can never match a prior dirty signature.
    """
    if not findings:
        return ""
    keys = sorted(
        (str(f.get("code", "")), str(f.get("path", "")), int(f.get("line", 0) or 0),
         str(f.get("ref", "")))
        for f in findings
    )
    return hashlib.sha1(json.dumps(keys).encode()).hexdigest()[:16]


def scoped_error_findings(report: dict, repo_root: str, features: str) -> list[dict]:
    """Doctor's error-level findings located in the service book being built.

    A monorepo's unrelated epic/spec history may already contain doctor findings. Those
    cannot be repaired by a docs/features-only workflow and must not prevent one service
    book converging.

    Already-waived findings are `warn` and so excluded, which is what lets
    `nodes/waivers.py` re-run without re-waiving.

    Shared with `nodes/waivers.py`, which needs the identical set — in the YAML it was
    *copied* into `auto-waive.py` under a comment saying it mirrored this one, and the two
    copies had already drifted: on an empty `features` the checkpoint's version scoped to
    whatever `Path("").resolve()` came out as (the process's cwd) and kept almost nothing,
    while auto-waive's `if not prefix` kept everything. Unified on auto-waive's reading,
    which is the one the checkpoint's own "doctor findings are unscoped" warning describes.
    Reachable only with no book to scope to, which the graph reaches only by failing first.
    """
    try:
        prefix = Path(features).resolve().relative_to(
            Path(repo_root).resolve()
        ).as_posix().rstrip("/") if features else ""
    except ValueError:
        prefix = Path(features).as_posix().rstrip("/")
    return [
        finding for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and (not prefix
             or str(finding.get("path", "")) == prefix
             or str(finding.get("path", "")).startswith(prefix + "/"))
    ]


@blueprint.node(stub=stubs.clean)
def checkpoint_book(
    logger: logging.Logger,
    repo_root: str = ".",
    features_root: str = "",
    prev_round: int = 0,
    prev_signature: str = "",
    prev_stall: int = 0,
) -> Checkpoint:
    """Canonicalize the book, then read doctor, then queue the repairs it names.

    Auto-formats (`ostler fmt`) then runs `ostler doctor`, turning a dirty doctor into
    worklist items the drain loop repairs before re-converging. Orphan / stub / coverage
    detection is left to the recheck agent (it needs to read code and walk `ostler trace`);
    this node owns only the deterministic part.

    **One item per file, not one per run and not one per node.** An earlier version packed
    every finding into a single item whose context was the last 4000 characters of the
    findings JSON — so on a book with more than a dozen findings the rest were dropped
    silently, and the loop churned without ever seeing them. Truncation that looks like
    completion is the failure this gate exists to prevent. Splitting per *node* fixed that
    but overcorrected: a component file with a hundred findings became a hundred agent
    turns re-reading the same source. Per file, bounded by a chunk cap, keeps every finding
    while letting one turn repair everything one reading explains.

    **Two kinds, because two different repairs.** A dangling link or a mis-ordered bullet
    is mechanical: the finding names its own remedy. A *missing required bullet* is not —
    the profile evolves, and every book authored before a bullet became required is
    retroactively behind, with no way to derive the value from the finding text. Those are
    emitted as `backfill`, whose prompt requires the value be grounded in source. Filed as
    `fixup` they would be "fixed" by writing an empty or `none` stub, which satisfies the
    linter while asserting something nobody checked.

    **Stall detection.** The drain-then-recheck loop assumes each fixup round *reduces* the
    findings — but a defect whose only real fix is a code change (two controls that
    genuinely co-render with the same accessible name) survives its doc-repair and doctor
    re-flags the identical set every round. That is an infinite loop the transition budget
    never catches, because each round still marks its fixup item done. So this node
    fingerprints the finding set and reports how many consecutive rounds it has recurred
    *unchanged* (`stall_rounds`); the workflow bounds the loop on that, not on the raw
    round count — which legitimately climbs on a big book that takes many *productive*
    fixup rounds to converge.
    """
    rnd = prev_round + 1
    okf = Ostler(repo_root)
    if features_root:
        try:
            result = run_fmt(okf.graph, [features_root])
            if result.changed:
                logger.info("canonicalized %d file(s) under %s", len(result.changed), features_root)
        except (OSError, ValueError, RuntimeError) as exc:
            # The subprocess version swallowed a failed `ostler fmt` too: doctor is the
            # gate, and an un-canonicalized book fails it loudly rather than quietly.
            logger.warning("ostler fmt failed for %s: %s", features_root, exc)
        # fmt writes; the cached snapshot is now the book as it was *before* it did.
        okf.reload()
    else:
        # No book to canonicalize: doctor still runs, but its findings can't be scoped to
        # a service, so every unrelated error in the repo lands on this round.
        logger.warning("no features root given — skipping ostler fmt; doctor findings are unscoped")

    try:
        findings = scoped_error_findings(okf.doctor(), repo_root, features_root)
        out = json.dumps(findings, indent=2)
    except (OSError, ValueError, RuntimeError) as exc:
        findings = [{"severity": "error", "message": str(exc), "path": features_root}]
        out = str(exc)
    clean = not findings

    signature = _signature(findings)
    if clean:
        stall = 0
    elif signature and signature == prev_signature:
        # The identical finding set as last round: a repair that cannot land (a
        # code-fix-only defect re-flagged unchanged). Count it so the workflow can bound
        # the loop.
        stall = prev_stall + 1
    else:
        # Findings changed — something was repaired or discovered. Real progress; reset.
        stall = 0

    fixups: list[dict[str, str]] = []
    backfills = 0
    if clean:
        logger.info(
            "round %d: doctor is clean for %s — the gate converges", rnd, features_root or repo_root
        )
    else:
        fixups = _repair_items(findings, rnd)
        backfills = sum(1 for i in fixups if i["kind"] == "backfill")
        logger.info(
            "round %d: doctor reports %d error(s) across %d item(s) in %s — "
            "queuing %d backfill + %d fixup item(s)%s",
            rnd, len(findings), len(fixups), features_root or repo_root, backfills,
            len(fixups) - backfills,
            f" [stall {stall}: same findings as last round]" if stall else "",
        )
    return Checkpoint(
        checkpoint_clean=clean,
        doctor_output=out[-4000:],
        round=rnd,
        fixup_items=fixups,
        backfill_count=backfills,
        fixup_signature=signature,
        stall_rounds=stall,
    )


__all__ = ["GROUNDED_CODES", "MAX_FINDINGS_PER_ITEM", "checkpoint_book", "scoped_error_findings"]
