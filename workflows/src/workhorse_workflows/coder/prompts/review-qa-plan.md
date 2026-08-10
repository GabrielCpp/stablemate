---
agent: agent
---

# Independently Review A QA Plan

Review the proposed QA plan before execution. Deterministic validation has already proved that
the YAML is structurally valid and names every known acceptance criterion and OKF obligation.
Your job is semantic: decide whether its actions and assertions can actually reach and observe
the behavior each `covers` claim promises.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`

Read the story, `qa-okf-context.json`, `qa-plan.yml`, `qa-plan.md`, review artifacts, and
`docs/qa/lessons.md` under the docs root (`docs_path` when non-empty) when present. Read applicable
QA skills and inspect cited native tests or flows when the plan delegates execution to them.

## What the plan does not own

The plan author is held to a contract you are also held to. Reject a plan for what it got
wrong, never for a responsibility it was forbidden to take:

- **The heavyweight shared stack — docker compose, emulators, the DB and its baseline seed —
  is not the plan's to start.** It is owned by the workflow's `ensure_stack` step, which reads
  the repo's `qa-stack.yml`, brings the stack up *after* this review and *before* the plan runs,
  and leaves it up. A plan that records the stack as not-yet-started is describing the state at
  authoring time, correctly. "This scenario needs the auth emulator and the emulator is not
  running" is therefore not a defect, and a revision demanding the plan establish it asks for
  something the author is explicitly told not to write.
- Only `background:` daemons — per-run services pinned to the working tree — are the plan's to
  declare, and those you may review normally.
- The plan may not edit product code or tests. A scenario that delegates to a cited native test
  is reviewed on whether that test proves the claim; if the test itself is inadequate, say so as
  a coverage finding against the scenario, not as an instruction to go write it here.

A finding the author cannot act on inside a plan file spends the repair budget and returns the
same worklist next pass, which ends the story with no verdict at all. When the only thing left
is outside the plan's authority, approve and put it in `notes`.

## What the plan is answerable for

The contract is fixed and written down: the story's acceptance criteria, plus the OKF
obligations in `<spec_dir>/qa-okf-context.json`. That union is the whole of what this plan
owes. Every check below is a check *against that contract*, not against QA in the abstract.

**A plan that covers its contract is approvable even if you can imagine a better plan.** There
is always another scenario worth adding, another assertion worth strengthening; a review that
asks for the best plan rather than a sufficient one never terminates, and the story ends with
no QA verdict at all — which is strictly worse than QA run against a merely adequate plan. If
a scenario reaches and observes what its `covers` claims, it passes. Improvements you would
like but do not need go in `notes`.

**Find everything you are going to find, this pass.** List every finding you have, however
many that is. A defect you could have named this pass and held back is not grounds for a later
refusal: if the author repairs what you listed, you approve.

For every scenario, independently verify — against the acceptance criteria and obligations it
`covers`, and not beyond them:

- its objective is explicit and corresponds to every AC/obligation in `covers`;
- causal preconditions are established and asserted rather than assumed from fixture selection;
- long browser/mobile chains begin at the documented flow entry and contain observable
  checkpoints before the terminal assertion;
- the terminal assertion proves the objective, not merely page presence or command success;
- expected error, retry, persistence, role, locale, keyboard, accessibility, and isolation paths
  are exercised **where `qa-okf-context.json` lists them as obligations** — a path OKF does not
  oblige for this story is not a gap;
- unexpected 5xx responses, crashes, and browser console errors cannot pass unnoticed;
- producer-consumer and pooled/shared-state obligations use an integration-strength oracle;
- each `verify:` reference has an appropriate level and actually runs in the declared environment;
- runner-owned artifacts will demonstrate the claimed result.

Do not execute the plan, drive the product, edit either plan file, or author evidence. This is an
independent review, not another planning pass. Approve when every acceptance criterion and
obligation in the contract has a scenario that would actually catch it failing. Otherwise return
precise revision notes keyed to scenario and coverage IDs.

Return JSON only:

```json
{
  "disposition": "revise",
  "findings": [
    {
      "id": "R1",
      "scope": "plan",
      "target": "scenario `create-document` / covers `AC-2`",
      "issue": "The terminal assertion checks the dialog closed, not that the document exists.",
      "repair": "Assert the new row is present in the document list after the dialog closes."
    }
  ],
  "notes": "One coverage gap; the rest of the plan reaches its objectives."
}
```

`disposition` is exactly `approved` or `revise`. A `revise` must carry the findings that
justify it — `notes` summarizes them, it is not the repair contract.

Every finding names its `scope`, and the flow acts on that field rather than on the prose
above it:

- `plan` — the plan author can fix it by editing `qa-plan.yml` / `qa-plan.md`. This is the
  only scope that is sent back for repair.
- `stack` — it belongs to `qa-stack.yml` and the workflow's `ensure_stack` step: a service,
  emulator, database, seed or aggregate command that must be up before the plan runs.
- `product-test` — it belongs to product code or a native test the plan only cites.

`stack` and `product-test` findings are **dropped** before the author sees them, and a
`revise` whose findings are all outside the plan's authority is recorded as `approved`. That
is the contract above made mechanical, not a loophole: name the scope honestly, because a
misfiled finding is now silently discarded rather than argued with.
