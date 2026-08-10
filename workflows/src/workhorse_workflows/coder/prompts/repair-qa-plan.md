---
agent: agent
---

# Repair The Cited Parts Of An Existing QA Plan

A QA plan for this story already exists and a gate sent it back. Apply the repairs the
diagnostics name. **Do not re-author the plan.** Do not execute QA.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`
- Context status: `{{ workhorse_var('context_status') }}`
{% if workhorse_var('context_notes') %}- Context diagnostics: `{{ workhorse_var('context_notes') }}`
{% endif %}{% if workhorse_var('plan_validation_notes') %}- Plan validation diagnostics: `{{ workhorse_var('plan_validation_notes') }}`
{% endif %}{% if workhorse_var('plan_review_notes') %}- Semantic plan-review findings: `{{ workhorse_var('plan_review_notes') }}`
{% endif %}{% if workhorse_var('run_assessment_notes') %}- Execution-assessment diagnostics: `{{ workhorse_var('run_assessment_notes') }}`
{% endif %}{% if workhorse_var('audit_notes') %}- Independent-audit diagnostics: `{{ workhorse_var('audit_notes') }}`
{% endif %}{% if workhorse_var('evidence_notes') %}- Deterministic evidence diagnostics: `{{ workhorse_var('evidence_notes') }}`
{% endif %}

The reviewer's findings are a list, one per line, each naming an id, a target and the
smallest acceptable repair. That list is the whole of your worklist.

{% if workhorse_var('prior_plan_reviews') %}## Everything The Plan Reviewer Has Already Asked For

Every refusal across every draft of this plan, oldest first. An entry is still open unless
the current plan satisfies it.

{{ workhorse_var('prior_plan_reviews') }}

A demand that appears here *and* in the findings above has now been made twice: the previous
repair did not land, so re-stating the same intent in different words will not close it
either. Change what the scenario **observes** — the oracle, the artifact it asserts on, the
page or process it reads from — not how it is described.

{% endif %}

## The rule

**Every scenario the findings do not cite stays byte-identical.** Read
`<spec_dir>/qa-plan.yml` and `<spec_dir>/qa-plan.md`, change only the scenarios, actions and
sections the diagnostics name, and leave everything else exactly as it is — including
formatting, ordering and ids.

This is not a stylistic preference. Regenerating the whole plan resamples the scenarios the
reviewer already accepted, which hands the next review a fresh set of defects to find; the
loop then never terminates, and the story ends with no QA verdict at all. A repair that
rewrites an uncited scenario is a defect in this turn, even when the rewrite is an
improvement.

Two consequences worth stating:

- If a finding is already satisfied by the current plan, do not touch that scenario. Say so
  in `notes`.
- If a finding cannot be satisfied by an executable scenario — it asks for something outside
  the plan's authority, or for the heavyweight stack the workflow's `ensure_stack` step owns —
  record that in `qa-plan.md` and in `notes` rather than inventing a scenario to satisfy it.

Adding a *new* scenario is a repair when a finding says coverage is missing. It is not a
repair when no finding asks for it.

## Staying inside the contract

The plan already validated against, or is being repaired toward, the universal plan schema.
The rules the repairs most often trip over:

- Every scenario keeps its `target`, `mechanism`, unique `id`, explicit `objective`, asserted
  causal preconditions, observable checkpoints, `covers`, and at least one machine-executed
  terminal assertion. `mechanism` is provenance (`live`, `synthetic`, `fixture`); `driver` is
  execution. Never use a driver name as a mechanism.
- An action `id` is unique across the **whole plan**. A new action gets an id namespaced to
  its scenario.
- An action declares **exactly one** of `do`, `expect`, or `capture`. Splitting a step into
  exercise-then-assert means two actions, each with its own id.
- Every Playwright locator and every URL comes from the book — the obligation's `locators`
  (`role` + `name`, or its stated `selector`) and its documented `route`/`entry`/`params` —
  never from the running page or from memory. `ostler qa validate` enforces this.
- No stub or placeholder `cmd`, no invented CLI flags or REST routes, and no time/entropy
  expression (`$(date +%s)`, `$RANDOM`, `$(uuidgen)`) outside a `fixture` step: generate it
  once, `capture:` it, and reference `{% raw %}{{key}}{% endraw %}`.
- `out:` and `capture:` paths resolve against the spec directory; a `cmd` runs at the repo
  root. A command that writes a file itself needs the absolute
  `{{ workhorse_var('qa_dir') }}/steps/…` path.
- The heavyweight stack is not the plan's to start. Only per-run `background:` daemons are.

Keep `qa-plan.md` in step with what you changed: the AC/obligation-to-scenario map has to
still describe the YAML. Do not rewrite sections whose scenarios you did not touch.

Do not validate the plan yourself — not `ostler qa validate`, not `ostler qa run`, and not by
importing `ostler.qa` from Python. A workflow node validates it the moment you return and
hands you its diagnostics if it fails, so a self-check can only repeat a verdict that is one
call away.

## Output

Return JSON only:

```json
{
  "status": "done",
  "notes": "R2: scenario `create-document` now asserts the new row after the dialog closes."
}
```

`notes` names each finding you closed and how. A finding you did not close is named there
too, with why.
