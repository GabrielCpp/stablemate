"""Accepting the code-fix-only a11y defects that stall the fixup loop — with an IOU.

Ported from `base-library/workflows/okf-builder/scripts/auto-waive.py`. The script was
already an ostler *library* caller, so the only changes are the shape ones — plus its
private copy of the scoped-findings computation, which now calls the one in
`shared/checkpoint.py` that it said in its own docstring it was mirroring.

One divergence worth naming: the re-run command this node embeds in every IOU is the
ported spelling (`workhorse-okf-builder --params …`), because that is the command that
reproduces this run. It no longer passes `recheck_only` — that parameter is retired, and
a run against a book that already exists re-enters at the checkpoint on its own.
"""
from __future__ import annotations

import logging

from ostler import Ostler, crud
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.checkpoint import scoped_findings
from workhorse_workflows.okf_builder.shared.schemas import Waived

#: Doctor codes whose ONLY real remedy is a source change. Deliberately narrow: a code a
#: doc edit could fix must keep failing until it is actually fixed, never be auto-accepted.
AUTO_WAIVABLE = frozenset({"ambiguous-locator", "unnamed-interactive"})

#: Where a code-fix-only defect is filed so the coder lane can pick it up. A backlog
#: bullet was the old destination and it is a dead end: nothing selects work from the
#: backlog, so an accepted defect went into the same undifferentiated pile as grammar
#: debt and was never fixed. A seed in a queued epic is the shape the author lane reads.
SEED_EPIC = "accessibility-code-fixes"
SEED_EPIC_TITLE = "Accessibility defects the book cannot repair"


@blueprint.node
def auto_waive(
    logger: logging.Logger,
    repo_root: str = ".",
    features_root: str = "",
    service: str = "",
) -> Waived:
    """Waive the stalled defects a doc edit cannot fix, and seed the code fix they need.

    Reached only after the doctor→fixup→doctor loop has stalled: the identical finding set
    recurred for N rounds because its repair cannot land in the book. A few doctor findings
    are genuinely **code-fix-only** — two controls that co-render with one accessible name
    (`ambiguous-locator`), an operable control the source leaves unnamed
    (`unnamed-interactive`). Documentation cannot resolve them, and re-flagging them
    forever is not convergence.

    Each such defect is accepted the honest way, never by hiding it:

    * a **doctor waiver** (`docs/doctor-waivers.json`) downgrades the finding error→warn —
      it stays visible in `doctor --json` with its reason, it just stops gating; and
    * a **seed** in the `accessibility-code-fixes` epic names the real fix, asks for the
      waiver to be removed once done, and gives the exact command to re-run and confirm
      the book is green *without* it — so the defect reaches the lane that writes code
      instead of settling into the waiver file next to the grammar debt.

    A stalled finding that is NOT auto-waivable (a mis-annotated role, a missing bullet —
    things a doc edit *could* fix) is a genuine dead end: `has_unwaivable` comes back true
    and the workflow fails honestly rather than papering over it.

    **Two reads of doctor, deliberately.** The dead-end verdict is taken over the *standing*
    set — every non-waived finding, which is exactly what the checkpoint gates on — because
    a stall on warns alone is still a stall, and answering it from the error-only view would
    report nothing to waive and send the workflow back to a checkpoint that is still dirty,
    forever. The IOU-minting loop keeps the error-only view: a seed per finding is the
    right price for a code-fix-only a11y defect and the wrong one for thousands of prose
    warns, which are repaired in the book rather than owed in code.
    """
    okf = Ostler(repo_root)
    report = okf.doctor().data
    standing = scoped_findings(report, repo_root, features_root)
    if not standing:
        # Nothing standing (a race, or all already waived): let the next checkpoint converge.
        return Waived(note="no standing findings — nothing to waive")

    unwaivable = [f for f in standing if f.get("code") not in AUTO_WAIVABLE]
    if unwaivable:
        for f in unwaivable:
            logger.warning(
                "doctor stuck — not auto-waivable: %s %s: %s",
                f.get("code"), f.get("ref"), str(f.get("message", ""))[:200],
            )
        codes = ", ".join(sorted({str(f.get("code")) for f in unwaivable}))
        return Waived(
            has_unwaivable=True,
            note=f"{len(unwaivable)} of {len(standing)} standing finding(s) are not "
                 f"auto-waivable ({codes})",
        )

    findings = scoped_findings(report, repo_root, features_root, errors_only=True)

    # Create-or-nothing: `create_epic` reports False when the epic is already there, which
    # on the second stalled run is the normal answer and not a failure. Queue it too — a
    # seed in an epic nobody queued is exactly as invisible as the waiver file this split
    # exists to empty, because epic selection only ever looks at the queue.
    okf.create_epic(SEED_EPIC, SEED_EPIC_TITLE)
    okf.todo_add(SEED_EPIC)

    reissue = f"workhorse-okf-builder --params '{{\"service\":\"{service}\"}}'"
    waived = 0
    for f in findings:
        code, ref = str(f.get("code", "")), str(f.get("ref", ""))
        # An ostler-minted, repo-prefixed id (ACME-15) — a first-class numbered work item,
        # not a descriptive slug. Each error finding is numbered exactly once: once waived
        # it becomes a `warn` and is excluded from the error set above, so a re-run never
        # re-mints for it.
        sid = okf.allocate_id()
        okf.add_doctor_waiver(
            code, ref,
            f"code-fix-only a11y defect auto-waived after the doc-repair loop stalled; "
            f"tracked by seed [{sid}]", sid,
        )
        remedy = str(f.get("suggestion", "") or "give the control a distinct accessible name")
        text = (
            f"BUG(a11y/{code}): {ref} — {str(f.get('message', ''))[:220]} "
            f"Fix in source ({remedy}), then remove this finding's entry from "
            f"docs/doctor-waivers.json and re-run `{reissue}` to confirm doctor is green "
            f"without the waiver."
        )
        # Use the cached graph directly (crud.add_seed re-reads epic.md itself, so its
        # update-or-create dedup still sees earlier adds) — the facade's add_seed reloads
        # the whole book per call, which on a large book is seconds per finding.
        crud.add_seed(
            okf.graph, SEED_EPIC, sid, summary=text,
            meta={"layers": ["frontend"], "services": [service] if service else []},
        )
        waived += 1
        logger.info("waived %s %s + filed seed [%s]", code, ref, sid)

    return Waived(
        waived_count=waived,
        seed_epic=SEED_EPIC,
        note=f"auto-waived {waived} code-fix-only a11y defect(s); seeds filed in epic "
             f"'{SEED_EPIC}'",
    )


__all__ = ["AUTO_WAIVABLE", "SEED_EPIC", "SEED_EPIC_TITLE", "auto_waive"]
