---
agent: agent
---

# Interpret And Explore An Ostler QA Run

Ostler already executed the complete YAML plan. You are an interpreter, not the primary
executor and not an evidence producer.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Runner status: `{{ workhorse_var('runner_status') }}`
- Runner diagnostics: `{{ workhorse_var('runner_notes') }}`
- Target environment: `{{ workhorse_var('target_env') }}`

Read `qa-okf-context.json`, `qa-plan.yml`, `qa/qa-run.ndjson`,
`qa/run-manifest.json`, and `qa-evidence.json` when they exist. Interpret the runner's
four-state outcome exactly:

- `passed`: assertions and required evidence completed; summarize what ran.
- `failed`: product behavior or an assertion was wrong; identify failed scenarios and
  affected AC/OKF coverage for defect triage.
- `blocked`: required environment, device, service, credential, or recorder could not
  run; identify the setup/operator dependency.
- `invalid`: plan, context, coverage, or runner evidence was malformed; identify the
  planning/context repair. Never relabel invalid evidence as failed or passed.

Write or update `<spec_dir>/qa.md` as a concise interpretation with runner status,
scenario/assertion references, affected AC/obligation ids, and artifact paths already
registered by the runner.

## Boundaries

Do not:

- drive Playwright, Maestro, a browser, a device, curl, or product commands directly;
- start/stop services or record video;
- write or edit `qa-evidence.json`, `qa/qa-run.ndjson`, `qa/run-manifest.json`, or any
  evidence artifact;
- supply a replacement PASS/FAIL verdict; or
- upgrade `invalid`, `blocked`, or `failed` to `passed`.

If `{{ workhorse_var('spec_dir') }}` is blank, derive it as `docs/specs/<story-name>` where `<story-name>` is the story folder name from the story path above. Derive `qa_dir` as `<spec_dir>/qa/`.

## Required Context

Read:

- **`{{ workhorse_var('spec_dir') }}/qa-plan.md` — the QA runbook to execute (the authority for this stage).** Run its pre-flight, then every per-AC step in order. If it is missing/empty, derive the per-AC checks from the story yourself and note the plan was absent.
- **`{{ workhorse_var('docs_path') }}/docs/qa/lessons.md` — the QA lessons log (cross-run memory). Read it first and apply every applicable lesson** so you do not re-hit a trap a prior run already solved (see "Learn Between QA Runs" below). If it is absent, there are simply no lessons yet.
- `{{ workhorse_var('docs_path') }}/AGENTS.md` and the project's developer / local-stack runbook
- `{{ workhorse_var('story_path') }}`
- the parent `epic.md` (sibling directory of the story folder)
- plan artifacts under `{{ workhorse_var('spec_dir') }}/` — including `plan-context.json` and the plan's **Verification Commands** / **Local run (smoke)**
- `review.md` and its resolution section, if present
- the instruction + QA files the workflow resolved for this story (decoded from `plan-context.json`):
  {% if impl_instruction_paths or qa_run_plan %}
  {%- for path in impl_instruction_paths %}
  - `{{ path }}`
    {%- endfor %}
    {%- for r in qa_run_plan %}
  - {% for s in (r.qa_skills if r.qa_skills else [r.qa_skill]) %}`{{ s }}`{% if not loop.last %}, {% endif %}{% endfor %} — how to run / exercise the {{ r.label }} layer
    {%- endfor %}
    {%- else %}
  - _(none resolved — fall back to the plan's **Required Skill Files Read** and load every instruction file it names)_
    {%- endif %}

## Goal

Verify the story's **Acceptance Criteria** are met by **actually exercising the change** using the tools the runbook specifies. Each acceptance criterion is a claim about observable behaviour; QA's job is to _perform the action_ and _observe the real result_, compared against the source of truth.

A green test suite or a successful build alone never proves an AC is met — the actual verification output (CLI results, rendered behaviour, command exit codes) is the oracle.

## QA Method — execute the runbook, manually, against the source of truth

Drive QA by **executing `qa-plan.md` acceptance-criterion by acceptance-criterion**. The plan already
states, per AC, the user action, the expected observation, the source-of-truth comparison, and the
pass rule — your job is to _perform_ each one on the running app and apply its pass rule. The
acceptance criteria are the contract; tests, lint, and build are necessary background but they NEVER
decide a pass on their own.

### Non-UI / infrastructure stories

If the runbook designates a shell script (`qa/qa-driver.sh`) as the execution vehicle — not Playwright — execute it directly. For non-UI stories (chart changes, config removal, dead-code deletion, backend-only work), the verification is CLI-driven: `helm template`, `grep`, `tsc --noEmit`, `go build`, `curl`, etc. Do NOT launch a browser, open Playwright, or attempt DOM assertions.

For ACs marked `kind: operator-only` in the runbook (require live cluster/Grafana/DNS), do NOT attempt them locally. If **all** ACs are operator-only, emit `blocked`. If some are locally testable and others are operator-only, exercise the local ones and note the operator-only ones cannot be verified in the current environment.

**Re-check device/target-dependent ACs before accepting `operator-only`.** If an AC is
`operator-only` specifically because it needs a UI-automation run against a physical device or
emulator, do not take the runbook's word for it — run the discovery check the layer's `qa_skill`
specifies yourself first. Environments change between planning and execution (a device may now be
attached that wasn't when the plan was written, or vice versa). A usable target means the AC is
actually `local` right now — run the UI flow the runbook specifies instead of skipping it. Record
the discovery check's output as the evidence for whichever way it goes.

### Per-AC execution

For **each** acceptance criterion in the runbook (run its pre-flight first to bring the stack up):

1. **Perform the action the runbook specifies.** Use the tools the runbook names: run the shell script, execute the CLI commands, or drive the app as described. Match the plan's verification approach — do not introduce tools the runbook does not call for.
2. **Judge by the actual output against the expected state.** Compare the real result (command output, exit codes, rendered behaviour, grep results) to the runbook's expected observation. The pass rule is concrete — apply it literally.
3. **Compare with the source of truth.** The runbook names what the result is compared against (the plan's expected state, captured evidence, a reference surface). If evidence exists (`evidence/old-*.png` or prior captures), load it and diff against the current output.
4. **Verify stateful flows end to end.** When the AC involves persisting state, perform the whole flow: action → save/commit → verify persistence (reload, re-query, re-run).
5. **Capture evidence** into `{{ workhorse_var('qa_dir') }}` as the runbook specifies (text files for CLI output, screenshots for UI).
6. **Confirm automated coverage exists** for the behaviour you exercised. A shipped behaviour with no automated test is a missing-coverage finding — record it.

**An acceptance criterion is "met" only when you performed its action and observed the correct,
source-of-truth-matching result — with captured evidence to prove it.** An AC you did not actually
exercise is **not** a pass: it is a Fail (build the missing precondition), or — only when the
environment itself is unavailable — a Blocked.

**An AC passes only when its _full_ pass-rule is satisfied — every clause of it.** The runbook (or
the AC text) states a concrete pass-rule; meeting _part_ of it is a **Fail**, not a Pass. If the
rule is "the Add/Remove/Clone controls render **and** clicking Add adds an item" and the controls
render but clicking Add errors (e.g. a 500), the observable behaviour the AC promises — _items can
be managed_ — does not happen, so the AC is **Fail**. "The control is present but does nothing", "it
renders but the action 500s", "it works at one breakpoint but not the other", "it's there but shows
the wrong value" are all **Fail**. Do not pass an AC on the presence of a control, the first half of
a flow, or a partial result. When in doubt whether the pass-rule is fully met, it is **not** met →
Fail.

To bring each touched layer up so you can exercise the ACs, the workflow resolved a per-layer run
plan from the plan's touched layers — follow each layer's QA skill for the exact setup/tool:
{% if qa_run_plan %}
{%- for r in qa_run_plan %}

- **{{ r.label }}**: follow `{{ r.qa_skill }}` — bring the layer up, drive the touched path with the tools the plan's Verification Commands specify, and capture evidence. Include authenticated sign-in where the path requires it, and any code generation / contract compile checks the plan lists.
  {%- endfor %}
  {%- else %}
- _(No run plan resolved.)_ Fall back to the plan's `services` (each service's `type` + `path`) + **Verification Commands** / **Local run (smoke)** and the touched services' instruction files.
  {%- endif %}
- Docs/decision stories: consistency review against roadmap, epic, dependent stories, and source-of-truth docs.
  {% if qa_stack and (qa_stack.profile or qa_stack.fixtures) %}
  **Run against the capable stack — with realistic data.** The story's **Verification setup** named the stack/profile and data this surface needs to render; the plan carried it forward as `qa_stack`{% if qa_stack.profile %} (stack: {{ qa_stack.profile }}){% endif %}. Exercise the surface on **that** stack with those fixtures present — not whatever thin/empty default happens to be up. A surface that renders **blank because the data isn't there** has NOT been QA'd: that is a **Fail** (the implementer must seed/build it), never a pass-by-omission and never "Blocked".
  {% endif %}
  Do not mark QA as passed if the core observable behavior was not checked, or if a touched layer was never actually run and exercised, or if the surface was only seen empty for lack of data.

## Independent Oracle (contract-consuming surfaces)

A green unit suite is **not** sufficient when a surface consumes an external contract (an API payload, another producer's output): the tests and the code share an author, so a fixture that encodes the _same wrong assumption_ as the code passes over a real bug. For any touched layer that consumes such a contract:

- Verify it **end-to-end against a real instance of that contract** running in an environment **independent of the local dev stack and the code's own fixtures** — the oracle named by the repo's QA skill. For a **rewrite** repo that is the reference/legacy mirror; for a **greenfield** repo it is a **deployed/staging environment** (a real backend outside the dev setup). Compare the consumer's actual rendered behavior against the **real response**, not the unit fixtures.
- **Capture the real payload** to `{{ workhorse_var('qa_dir') }}` as the oracle evidence.
- **Deployed-env safety**: a deployed/staging oracle is shared and outward-facing — keep QA **read-mostly** and use a dedicated **test tenant/account**. Never mutate shared or production-like data to satisfy QA.
- If the repo genuinely declares **no independent oracle** for this surface, say so explicitly in the QA report and proceed on the local checks (this section is then a no-op — it must not block).

{% block repo_qa_browser_gates %}{% endblock %}

### Required Success Gates (Must Pass Before QA Passes)

Do not mark QA as passed if required success gates fail. The **behavioural gates decide the
verdict**; the build gates are necessary background that can never, by themselves, make QA pass.

| Gate                                                    | What must pass                                                                                                                                                                                                                                                 |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every AC exercised                                      | each AC's action was actually performed and the observed result matches the source of truth — proven by captured evidence (command output, screenshots, or both as the runbook specifies)                                                                      |
| Every AC's full pass-rule met                           | each AC passes only when **every clause** of its stated pass-rule is satisfied — a partial result, a half-completed flow, or a result correct in one layer but broken in another is a **Fail**                                                                 |
| Stateful flows persist                                  | where data is entered or state is mutated, the full flow was exercised: action → persist → verify persistence (reload / re-query / re-run)                                                                                                                     |
| Automated coverage present                              | the behaviour exercised carries proper automated coverage that passes — shipped behaviour with no automated test is a missing-coverage finding                                                                                                                 |
| Tests + lint/format + build (necessary, NOT sufficient) | the plan's **Verification Commands** per touched layer pass — but a green suite alone does **not** make QA pass; the behavioural gates above do                                                                                                                |
| Accessibility (UI layers touched)                       | the live axe scan on the touched surface shows **no new serious/critical violations** (missing name/role, unlabeled input, interactive `<div>`, contrast, missing live region), and the keyboard smoke passes — recorded in `qa-evidence.json` `accessibility` |
| Contract-consuming layer (if any)                       | verified against a **real producer payload** from the independent oracle (captured to `qa/`), not asserted solely from unit fixtures — unless the repo declares no oracle                                                                                      |
| Docs (if touched)                                       | cross-reference epic, roadmap, dependent stories; no missing links                                                                                                                                                                                             |
| Agent toolkit (if touched)                              | `farrier --check` leaves generated adapter files current                                                                                                                                                                                                       |
| Data/DB-behavior ACs                                    | must cite **runtime evidence** — the actual query output or command result showing before/after state; "source review confirms" is **not** sufficient                                                                                                          |

{% block repo_qa_rules %}{% endblock %}

## Regression-Suite Failures: Attribute Before You Fail

A failing regression/integration suite (e.g. a full journey/e2e suite) is not automatically this
story's fault. Blaming every failing test on the story sends the bounded fix loop chasing bugs it
did not cause — it will never converge, and it burns the rework budget before a human ever sees the
real cause. **It is your job to attribute each failure, not just count it.**

For every test failing in a regression/integration suite (not the per-AC checks you drove
yourself — those are already scoped to this story by construction):

1. **Check whether it's pre-existing.** Run the same failing test(s) against a clean checkout of
   the base branch (or with this story's diff stashed) for the affected layer. If it fails
   identically there, it predates this story — it is **not** a reason to fail this story.
2. **Check whether it's flaky.** Re-run the failing test at least once in isolation. If it passes
   on rerun while the rest of the suite is stable, treat it as non-deterministic, not a story-caused
   regression.
3. **Classify each failure** as one of:
   - **regression** — fails on this story's branch, passes on the base branch, and reproduces
     consistently. This is a real, story-caused failure and **does** count toward a Fail verdict.
   - **pre-existing** — fails identically on the base branch. Not caused by this story: do not fail
     the story on it. File it to the backlog (see "File Separate-Scope Discoveries" above) so it is
     not lost, and name it explicitly in **Issues Found** as pre-existing with the base-branch
     evidence.
   - **flaky** — non-deterministic (fails, then passes on rerun with no code change). Not a reason
     to fail the story. Note it in **Issues Found** with the repro (fail run + pass rerun), and log
     it to `docs/qa/lessons.md` if it is likely to recur so future runs don't re-litigate it.
4. **Only `regression` classifications count toward a Fail driven by the regression suite.** If
   every failure in the suite is `pre-existing` or `flaky`, that suite alone does not fail the
   story — but the story can still fail on other grounds (a per-AC check you drove yourself, a
   review finding, missing evidence).
5. **Record the classification, not just the raw count**, in `qa.md`'s **Issues Found** — one line
   per failing test: `<test name> — regression|pre-existing|flaky — <how you determined it>`. A bare
   "N tests failed" with no attribution is not sufficient evidence for a Fail driven by the
   regression suite; the auditor that re-judges this verdict will check for this attribution and
   route back to you if it is missing.

Do not skip this because it costs time — an unattributed regression-suite failure is exactly the
kind of finding that looks like "the story is broken" but is actually "the suite/environment is
flaky", and shipping that misclassification wastes the fix loop's whole budget.

## Fail vs Blocked Result Status

This choice has real cost. **Fail** routes to a tight, targeted fix loop (`apply-qa-fixes`,
bounded) that edits code and re-runs QA — no re-planning. **Blocked** escalates to the operator
and can re-enter the whole plan→implement→review→QA chain. So **Blocked is expensive — reserve
it for genuine walls that code in this repo cannot resolve.**

**Fail** (the default for anything wrong): the observable behavior is wrong but **a code change
in this repo can fix it** — including a _missing_ control, an unwired entry point, an
unreachable page, a missing layer you could add, a wrong/empty data binding, a divergence
from the source-of-truth surface, or **a surface that renders blank because the data/seed/fixtures
/migration/stored-procs it needs are absent** (the implementer must build or seed them — see the
capable-stack gate above). If a developer could open the repo and fix or seed it, it is **Fail**,
not Blocked.

**Blocked** (the _environment_ could not be brought up to run the ACs — not the code): the dev
stack/tooling needed to exercise the verification is not running and you could not make it run — e.g.
the required tools are not installed, the local config/ports are broken, a real credential/secret/
deployed-preview env is needed and only the operator can provide it, or a prerequisite story is
not yet merged so the surface cannot exist at all. Also Blocked when **all** ACs are marked
`kind: operator-only` in the runbook (require live infra inaccessible locally). **Report this as
`blocked`, do not claim a partial Pass when you could not exercise the ACs** — the evidence gate
will downgrade that to a Fail and the code-fix loop will spin on a stack that cannot run.

Blocked is **not** a dead end here: the workflow first routes it to an **automated setup-fix**
agent that does anything it can to make the dev stack QA-capable (start the emulators/devstack,
install missing tooling, fix local config) and then **re-runs QA**. It escalates to the operator
only if that setup-fix loop is exhausted or the blocker is genuinely human-only (a secret, a real
deployed env, hardware). So: when the **environment** can't run, prefer **Blocked** (it gets fixed
and re-QA'd) over a forced Fail.

"The feature is missing / broken / does not work" is still **not** a block — that is the work, and
it is **Fail** (the code-fix loop). A **missing fixture, seed, or data row the surface needs** is
likewise a **Fail** (buildable by the implementer) — unless it is the dev stack's own baseline seed
that the documented runbook brings up, which the setup-fix agent handles. When uncertain between a
**code** Fail and a Blocked, choose **Fail**; but do not force a Fail (or a hollow Pass) when the
real problem is that **the environment never ran** — that is **Blocked**.

## File Separate-Scope Discoveries To The Backlog (don't drop, don't scope-creep)

QA often surfaces a real defect or broken surface that is **genuinely outside this story's scope**
— a different surface, a contract mismatch in an untouched layer, a follow-on this story should
not absorb (e.g. discovering a blank section-tree screen while QA'ing the create form). Do not
silently drop it, and do not scope-creep this story to fix it. **File it to the backlog** so the
author workflow picks it up next run:

- Append an entry to `{{ workhorse_var('spec_dir') }}/backlog-items.json` — a JSON array; each
  item `{"id": "<kebab-id>", "description": "<one self-contained line>", "section": "## <domain heading>"}`
  (`section` optional). A deterministic node drains this into the repo backlog (format-checked,
  de-duplicated). Reference the filed `[id]` in **Issues Found** / **Follow-Ups** of the report.
- **Guardrail (load-bearing):** file **only** genuinely separate scope. A buildable in-scope
  precondition for _this_ surface (a missing seed/fixture/migration the surface needs) is **Fail**
  → the implementer builds it; it is **not** filed. "Finish the rest of this story" is finished,
  not filed. Filing is for creating a _new owner_, never for walking away from in-scope work.
- **Filing never upgrades a Fail to a Pass.** If the discovered defect is part of an acceptance
  criterion's _own_ pass-rule (the AC says "clicking Add adds an item" and Add 500s; the AC says
  "the label is translated" and it shows a code), that AC is **Fail** — the defect is in-scope and
  the fix loop must resolve it. You may _also_ file a genuinely separate follow-on (e.g. a deeper
  backend refactor the AC doesn't require), but the AC that promised the behaviour does **not** pass
  while the behaviour is broken. Backlog filing records _extra_ scope; it never excuses the scope
  the AC already owns.

{% block repo_qa_auth_setup %}{% endblock %}

## Execution Vehicle

Follow the QA runbook's (`qa-plan.md`) specified execution vehicle. For tool-specific guidance (how to write a Playwright script, how to run Maestro flows, how to drive CLI checks), read the `qa_skill` instruction files listed in Required Context — they are the authority for each layer's tooling.

### `ostler qa run` — primary execution vehicle for CLI/API/backend layers

**When `qa-plan.yml` is present**, use `ostler qa run` instead of running CLI commands directly:

```bash
# 1. Write payload files into qa/payloads/ BEFORE running
# 2. Validate the plan
ostler qa validate {{ workhorse_var('spec_dir') }}/qa/qa-plan.yml
# 3. Execute
ostler qa run {{ workhorse_var('spec_dir') }}/qa/qa-plan.yml --spec {{ workhorse_var('spec_dir') }}
# 4. Report (paste into jira-comment.md)
ostler qa report --spec {{ workhorse_var('spec_dir') }}
```

Set `qa_run_log: "qa/qa-run.ndjson"` in `qa-evidence.json` and add `log_refs: ["<step-id>", ...]` to each criterion citing the relevant step/assert ids from the run log.

**If a step fails validation or execution — fix the plan, do not abandon ostler.** A `validate`/`run`
failure on a step (an unresolved placeholder, a CLI flag or endpoint that doesn't exist, a
`capture` that doesn't parse) is not license to fall back to driving the rest of the plan by hand.
Edit that step's `cmd` in `qa-plan.yml` to the real command — discover it the same way you would
manually, per the layer's `qa_skill` — then re-run
`ostler qa validate` and `ostler qa run` on the corrected file. The plan file is allowed to change
mid-run; what has to stay trustworthy is the **executed** record (`qa-run.ndjson`), not the first
draft of the plan. **Never** substitute freehand, unlogged commands for one or more steps while
leaving `qa-plan.yml` present — that produces exactly the agent-narrated, unverifiable run this
format exists to prevent, and it must not happen silently (say so in `qa.md` if you had to correct
a step).

**If `qa-plan.yml` is absent entirely** (UI-only story with no CLI/API component), fall back to
direct Playwright / Maestro / CLI. This is the _only_ condition under which a fully manual run
without `ostler qa run` is acceptable.

**The agent does NOT:**

- Start or stop background daemons manually when they are declared in `qa-plan.yml` — ostler owns their lifecycle.
- Write evidence files directly into `qa/` (except payload files and the plan file).
- Supply PASS/FAIL verdicts for inline assertion checks — those are executed by ostler.

- **Reuse across runs.** On a re-QA, re-run the existing `qa-plan.yml`; add steps only for previously-failing scenarios.
- **All QA artifacts live under `{{ workhorse_var('qa_dir') }}`**. Evidence paths must be absolute.

## Learn Between QA Runs

QA should get **smarter each run, not repeat the same mistake**. Two durable artifacts carry that memory
forward — use both:

1. **The QA script** (above). A working setup / execution flow, once scripted under `qa/`, is re-run
   rather than re-derived. Re-deriving a flow by hand each time is exactly how the same setup misstep
   recurs — script it and the misstep is solved once.
2. **The QA lessons log — `docs/qa/lessons.md`.** This is the cross-run, cross-story memory of
   _non-obvious_ traps and their fixes (an env/config that must be aligned, a flake and the workaround that
   stabilizes it, a wrong assumption about tool output, a stack quirk that masquerades as a
   product bug). You already **read** it in Required Context — now **close the loop**:
   - At the end of the run, if you hit a non-obvious problem that cost real time **and will recur on a
     future story** (not a one-off, not a fact specific to this story), append a single deduplicated line:
     `- [<area>] <the trap> → <the fix>`. Create `{{ workhorse_var('docs_path') }}/docs/qa/lessons.md` (with a `# QA Lessons` header) if it
     does not exist yet.
   - Keep it **general, durable, and short** — a lesson the next QA run can apply blind. Do **not** log
     story-specific data, evidence, verdicts, secrets, or one-off observations (those belong in `qa.md`).
     If an existing line already covers it, don't duplicate; refine the existing line if your run sharpened
     it.
   - If you applied a lesson from the log and it turned out **stale or wrong**, correct that line — the log
     is only useful while it stays true.
You may propose targeted exploration only when the existing ledger exposes a concrete
uncertainty not already covered. To do so, append replayable scenarios and assertions to
`qa-plan.yml` and return `rerun`. Do not execute them yourself. The workflow will validate
the amended plan and rerun Ostler, which will replace `qa/` with fresh runner-owned output.
Do not append exploration merely to retry a deterministic failure or bypass invalid
coverage.

## Output

Return JSON only:

```json
{
  "qa_interpretation": {
    "action": "continue",
    "notes": "Interpreted the runner outcome and recorded scenario/coverage references."
  }
}
```

`action` is exactly `continue` or `rerun`. It is routing only, never a QA verdict.
