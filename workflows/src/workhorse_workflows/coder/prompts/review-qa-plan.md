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

**An obligation is covered by the union of the scenarios carrying its id, not by any one of
them.** An OKF `does:` bullet is routinely a whole route contract in a single paragraph — the
passing path, the validation refusal, each failure response, the conflict status. No one
scenario can observe all of that, so a review that asks a single scenario to prove a composite
obligation has posed a question with no satisfiable answer, and the author spends the whole
repair budget moving the same id between scenarios. The mechanical gate unions `covers:` across
the plan, and so do you: read the obligation clause by clause, and refuse only a clause that no
scenario in the plan would catch failing. Never direct the author to carry an id "only where
the complete behaviour is observed" — name the unproven clause instead, and let the id ride on
every scenario that proves a part of it.

**Find everything you are going to find, this pass.** List every finding you have, however
many that is. A defect you could have named this pass and held back is not grounds for a later
refusal: if the author repairs what you listed, you approve.

For every scenario, independently verify — against the acceptance criteria and obligations it
`covers`, and not beyond them:

- its objective is explicit and corresponds to the part of each AC/obligation in `covers` that
  this scenario is there to prove;
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
obligation in the contract has, somewhere in the plan, a scenario that would actually catch
each of its clauses failing. Otherwise return
precise revision notes keyed to scenario and coverage IDs.

Return JSON only:

```json
{
  "disposition": "revise",
  "findings": [
    {
      "id": "R1",
      "scope": "plan",
      "kind": "coverage",
      "target": "scenario `create-document` / covers `AC-2`",
      "issue": "The terminal assertion checks the dialog closed, not that the document exists.",
      "repair": "Assert the new row is present in the document list after the dialog closes."
    }
  ],
  "notes": "One coverage gap; the rest of the plan reaches its objectives."
}
```

`disposition` is exactly `approved` or `revise`. A `revise` must carry the findings that
justify it — `notes` summarizes them, it is not the repair contract. The author is briefed
from `findings` alone, so a `revise` with an empty `findings` list, or a finding missing any
of `id`, `target`, `issue` or `repair`, fails the run outright rather than being reinterpreted
from your prose. `id` is any stable handle; reuse the same one when you restate a finding.

Every finding names its `scope`, and the flow routes on that field rather than on the prose
above it. The question the scope answers is **where the repair lives**:

- `plan` — the repair is an edit inside `qa-plan.yml` / `qa-plan.md`. Sent to the plan author.
- `product-test` — the repair is an assertion, fixture or fix in product code or a committed
  test the plan only cites. Sent to the fix loop, which edits the code.
- `stack` — the repair is in `qa-stack.yml` and the workflow's `ensure_stack` step: a service,
  emulator, database, seed or aggregate command that must be up before the plan runs.

A `revise` whose findings are all outside the plan's authority is recorded as `approved` —
the plan is not what needs revising — and the findings still reach whoever owns them. Name
the scope by where the repair lands, not by who found it: a real gap filed as `plan` bills a
replan that cannot close it, and the same gap comes straight back on the next pass.

## `kind` — what breaks if the plan ships as it stands

Every finding also names a `kind`. Decide it by naming the consumer that reads the thing you
are objecting to, and saying what that consumer does differently once it is fixed:

- `coverage` — an acceptance criterion or OKF obligation has no scenario that would catch it
  failing, or the scenario's evidence does not prove what it `covers`. **The runner behaves
  differently.** This is the only kind that refuses a plan.
- `overclaim` — the plan asserts more than its cited evidence proves: a checkpoint claiming a
  viewport, a locale or a path the run does not exercise. Nothing goes untested, but the
  post-run audit reads these claims, so the text must still be corrected.
- `cosmetic` — counts, wording, ordering, a stale summary line. No gate and no runner reads
  it.

The mechanical consequence, so you can price your own verdict: **only `coverage` refuses the
plan.** An `overclaim` or `cosmetic` worklist is handed to the author, repaired once, and
goes straight to execution without returning to you. Correcting it costs the run about a
fifth of what another review pass costs, which is why it does not buy one.

This is `{{ workhorse_var('review_pass') }}`; blocking passes remaining:
`{{ workhorse_var('blocking_passes_left') }}`. At zero, no finding refuses the plan whatever
its kind — a coverage gap that first appears after two repairs of the same plan is treated as
a late nit, and the post-run audit is the gate that stands behind it. So name a real coverage
gap on your first pass or accept that the run will find it the expensive way.

`kind` defaults to `coverage` when omitted, so an unlabelled finding blocks. Label
deliberately rather than defensively: inflating a nit to `coverage` does not make the plan
better, it spends the passes that a genuine gap would need.

## The set-diff is already done — do not redo it

`ostler qa validate` has already passed on this plan, and it is not a schema check. It diffs
every `required: true` obligation and every `ac:N` against the union of the scenarios'
`covers:`, and it refuses a plan that leaves one uncovered. It also refuses a scenario whose
`covers:` rides on nothing but a runner's exit banner (`VITEST_EXIT:0` and its kin) or on a
whole `test_file:` with no `test_name:`. So an id you cannot find in any `covers:` list does
not exist in the plan you are reading — re-deriving that mapping by hand spends a large part
of your pass to reproduce a verdict that already ran.

What the validator cannot decide is whether an assertion that *is* substantive actually
exercises the behaviour its `covers:` names: a component rendered with a hard-coded literal
where the obligation is that the value is *computed*; a checkpoint that reads the fixture back
rather than the surface; a journey deep-linked past the navigation the flow documents. That
judgment is the whole of your `coverage` worklist. Cite the scenario, name what its evidence
proves, and name what the obligation requires instead.
