---
agent: agent
---

# Repair The Cited Parts Of An Existing QA Plan

A QA plan for this story already exists and a gate sent it back. Apply the repairs the
diagnostics name. **Do not re-author the plan.** Do not execute the scored QA run — the
per-scenario dry run described below is the one execution this turn owns.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`
- Context status: `{{ workhorse_var('context_status') }}`
{% if qa_stack %}- The stack that is **already up** for you{% if qa_stack.profile %}, profile `{{ qa_stack.profile }}`{% endif %}:
{% if qa_stack.fixtures %}  - fixtures already loaded — assert against **these**, do not re-derive a path:
{% for f in qa_stack.fixtures %}    - `{{ f }}`
{% endfor %}{% endif %}{% if qa_stack.capable_of_rendering %}  - what it can render: {{ qa_stack.capable_of_rendering }}
{% endif %}{% endif %}{% if shared_packages %}- Shared files this story's services both read, resolved by the implementation plan:
{% for p in shared_packages %}  - `{{ p }}`
{% endfor %}{% endif %}
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
`<spec_dir>/qa-plan.yml` and `<spec_dir>/qa-plan.md` — and `<spec_dir>/qa.md` when a finding
cites it — change only the scenarios, actions and sections the diagnostics name, and leave
everything else exactly as it is — including formatting, ordering and ids.

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
  This escape hatch is for a *coverage* demand you have no way to execute. It is not
  available for a finding that says a sentence you wrote is false: correcting a sentence is
  always within your authority.

Adding a *new* scenario is a repair when a finding says coverage is missing. It is not a
repair when no finding asks for it.

## A finding that cites prose is closed by editing that prose

Some findings do not name a scenario at all. They name a passage — a section of
`qa-plan.md`, a caveat in `qa.md` — and say the claim it makes is untrue: the plan asserts a
file, a test or a sibling story does not exist when it does, or that a check proves something
it never touches. **Edit the cited passage so it says the true thing.** Read the target the
finding names, find the sentence it quotes, and rewrite that sentence.

Appending a note elsewhere does not close such a finding, and neither does adding a section
that *discusses* the discrepancy, acknowledges it, or explains why it does not change the
verdict. The next gate re-reads the passage the finding cited, still finds the false claim
sitting there verbatim, and refutes again — the same demand, another full re-run of the
suite, another audit. That has happened on live stories; it is the single most expensive way
this turn can fail, and it fails while reporting `"status": "done"`.

So before you return: for every finding whose target is a file and a section, re-read that
exact location and confirm the words the finding objected to are gone. If you left them
standing on purpose, say that in `notes` and say why — do not report the finding closed.

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
  root. A command that writes a file itself needs **`$QA_DIR/steps/…`**, which ostler sets to
  whichever ledger directory this run was given. Spelling that directory out by hand —
  `{{ workhorse_var('qa_dir') }}/steps/…` — pins it to the scored ledger even during a dry
  run, so the rehearsal writes into the evidence the scored run is judged on. `ostler qa
  validate` rejects the pinned spelling.
- The heavyweight stack is not the plan's to start. Only per-run `background:` daemons are.

Keep `qa-plan.md` in step with what you changed: the AC/obligation-to-scenario map has to
still describe the YAML. Do not rewrite sections whose scenarios you did not touch.

## Coverage Has To Be Earned

`ostler qa validate` now grades what a scenario's `covers:` is worth. A scenario whose only
assertion is a runner's exit banner — `assert_contains: "VITEST_EXIT:0"`, `GOTEST_EXIT:0`, any
bare `EXIT:0` — no longer counts as covering anything: it proves the suite is green and is
indistinguishable from a suite that skipped every case. A `test_file:` reference needs a
`test_name:` naming the case the coverage rides on. When a finding cites a scenario like that,
the repair is a real oracle — something the command prints about the behaviour, or an `expect:`
on the surface — not a reworded objective.

## Dry-Run The Scenarios You Repaired

The stack is already up. Before returning, execute each scenario you changed on its own:

```bash
ostler qa run <spec_dir>/qa-plan.yml --spec <spec_dir> \
  --scenario <scenario-id> --out-dir {{ workhorse_var('qa_scratch_dir') }}
```

`--out-dir` keeps the artifacts out of `{{ workhorse_var('qa_dir') }}`, the scored ledger the
evidence gate reads — a scenario tuned until it passed must not be able to leave its own proof.
Fix what does not resolve and run it again. One call settles what no amount of re-reading does:
a locator matching zero elements, a straight `'` where the fixture has `’`, a credential that
disagrees with the seed script. Each of those otherwise costs another full workflow lap.

You may repair **runner tooling** to make the dry run executable — the ostler venv and its
dependencies, harness wiring, fixture plumbing, a missing browser binary — and say so in
`notes`. You may **not** touch product code: a scenario that fails because the product is wrong
is the finding this whole loop exists to surface.

Do not validate the *plan* itself by any other route — not `ostler qa validate`, not a
whole-plan `ostler qa run`, and not by importing `ostler.qa` from Python. A workflow node
validates it the moment you return and hands you its diagnostics if it fails, so a self-check
can only repeat a verdict that is one call away.

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
