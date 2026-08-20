---
agent: agent
---

# Repair The Cited Parts Of An Existing QA Plan

A QA plan for this story already exists and a gate sent it back. Apply the repairs the
diagnostics name. **Do not re-author the plan.** Do not execute the scored QA run — the
per-scenario dry run described below is the one execution this turn owns.

## Time budget — {{ node_timeout_min }} minutes

This turn is stopped at its budget ("unbounded" = no cap), and what survives is the file on
disk rather than this turn's reply. Being cut is **not** a failure. Apply the repairs **one
at a time, saving after each**, and dry-run each one as you finish it rather than batching
every execution at the end — the budget covers both the edits and the scenario runs, and a
run is the slow half. Take the worklist in the order it is given; if you cannot reach the end
of it, a plan carrying most of the cited repairs is worth more than one carrying none. If you
are cut, the next turn continues this same conversation and is told so: it picks up your
worklist where you left it, so do not re-apply an edit that already landed, and never
re-author the plan — that is the single fastest way to lose this turn's work.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`
- Context status: `{{ workhorse_var('context_status') }}`
{% if verification_setup %}- The stack that is **already up** for you{% if verification_setup.profile %}, profile `{{ verification_setup.profile }}`{% endif %}:
{% if verification_setup.fixtures %}  - fixtures already loaded — assert against **these**, do not re-derive a path:
{% for f in verification_setup.fixtures %}    - `{{ f }}`
{% endfor %}{% endif %}{% if verification_setup.capable_of_rendering %}  - what it can render: {{ verification_setup.capable_of_rendering }}
{% endif %}{% endif %}{% if shared_packages %}- Shared files this story's services both read, resolved by the implementation plan:
{% for p in shared_packages %}  - `{{ p }}`
{% endfor %}{% endif %}
{% if workhorse_var('context_notes') %}- Context diagnostics: `{{ workhorse_var('context_notes') }}`
{% endif %}{% if workhorse_var('plan_validation_notes') %}- Plan validation diagnostics: `{{ workhorse_var('plan_validation_notes') }}`
{% endif %}{% if workhorse_var('run_assessment_notes') %}- Execution-assessment diagnostics: `{{ workhorse_var('run_assessment_notes') }}`
{% endif %}{% if workhorse_var('audit_notes') %}- Independent-audit diagnostics: `{{ workhorse_var('audit_notes') }}`
{% endif %}{% if workhorse_var('evidence_notes') %}- Deterministic evidence diagnostics: `{{ workhorse_var('evidence_notes') }}`
{% endif %}

The findings are a list, one per line, each naming an id, a target and the smallest
acceptable repair. That list is the whole of your worklist.

{% if failed_scenarios %}
## Scenarios that failed the last run

These are the scenarios the runner did not pass, with the ids of the assertions that failed
inside each. They are what this repair is for, and **every one of them must be dry-run green
before you return** — see "Dry-run the scenarios you repaired", which is a contract and not
advice.

{% for scenario in failed_scenarios %}
- `{{ scenario.id }}`{% if scenario.failed_assertions %} — failed assertions: `{{ scenario.failed_assertions | join('`, `') }}`{% endif %}
{% endfor %}
{% endif %}

## The rule

**Every scenario the findings do not cite stays byte-identical.** Read
`<spec_dir>/qa_plan.py` and `<spec_dir>/qa-plan.md` — and `<spec_dir>/qa.md` when a finding
cites it — change only the scenario functions and sections the diagnostics name, and leave
everything else exactly as it is — including formatting, ordering and function names.

This is not a stylistic preference. Regenerating the whole plan resamples the scenarios the
earlier passes already accepted, which hands the next gate a fresh set of defects to find;
the loop then never terminates, and the story ends with no QA verdict at all. A repair that
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

When a finding cites a broad acceptance criterion — words such as `every`, `all`,
`throughout`, `any other`, `each`, `whole app`, or a parenthesized category list — first
write the concrete category inventory into `qa-plan.md`, then close each cited missing
category with a replayable assertion or fixture case. Do not answer by strengthening the
best existing sample. A sample proves only the category it reaches; the repair is complete
only when the plan names the remaining categories and maps each one to terminal evidence.

For document/PDF/print repairs, close the specific evidence shape the finding names:

- "every word" requires a complete normalized source-text inventory compared with the
  produced output's text/OCR inventory for each cited browser, minus only named browser
  headers/footers;
- "every heading" includes the page/reader H1 as well as generated subsection headings;
- "inspect by eye", "visual inspection", or equivalent wording requires a terminal
  artifact-backed visual-review assertion with explicit accept/reject criteria for clipping,
  chrome leakage, page breaks, blank pages, and print fidelity. Registering PDFs, screenshots,
  rasters, or a manifest is not enough unless a `qa.check`/`qa.require` records that review's
  verdict.

## A race is repaired by waiting, never by loosening

When a finding says an assertion failed intermittently, or that it read a half-rendered page,
the plan raced the product: the assertion was right and the read was early. `.count()`,
`.get_attribute()`, `.inner_text()` and `qa.page.evaluate()` sample once and never retry, so
against a UI still settling they report whatever happened to be on screen at that instant.

Repair the **read**. Await the specific locator — `badge.wait_for(state="visible")` — before
sampling it, and check that the wait is a wait for *that* element: a `wait_for_url` waits for
the navigation and proves nothing about what rendered after it.

Do not widen the expected value, delete the check, or add a sleep. The first two turn a red
run green without touching the product, which is the most expensive mistake available in this
turn; the third is the same race with a worse constant. A state that is transient by nature
needs the transition held (block the response, throttle the route) or a durable consequence
asserted instead.

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

The plan is a Python module and its scenarios are functions. The rules the repairs most often
trip over:

- Every scenario keeps its `target`, `mechanism`, explicit objective (its **docstring**),
  asserted causal preconditions, observable checkpoints, `covers`, and at least one
  `qa.check`/`qa.require`. `mechanism` is provenance — `live` or `fixture`, never a test
  suite standing in for the product; `driver` is execution. Never use a driver name as a
  mechanism.
- A scenario's id is its function name with underscores turned into dashes. Renaming a
  function renames the scenario the findings cite — don't, unless a finding asks.
- **Module level is declarations only.** A request, a subprocess or a file write at module
  scope turns every `ostler qa validate` into a run, because validation imports the module.
- **Do not defend against a wrong key.** If a repair makes you reach for `.get(…, [])` or a
  `try/except` around a lookup, you are hiding the defect the traceback would have named.
  Let it raise.
- Every Playwright locator and every URL comes from the book — the obligation's `locators`
  (`role` + `name` via `qa.by_role`, or its stated `selector` via `qa.by_css`) and its
  documented `route`/`entry`/`params` — never from the running page or from memory.
  `ostler qa validate` enforces this.
- No invented CLI flags, REST routes or output shapes. A value two scenarios share is
  generated inside one of them, not at module scope.
- Files a scenario writes go through `qa.artifact("steps/…")`, which resolves inside
  `qa.dir` — this run's ledger, including a dry run's `--out-dir`. Spelling that directory
  out by hand pins it to the scored ledger even during a dry run, so the rehearsal writes
  into the evidence the scored run is judged on.
- `qa.vet(screen, name=...)` without `components=` asks the runner to find every documented
  component on that screen. Use that only after a state that should render the whole screen.
  For stateful screens, mutually exclusive panels, fixture variants, tab states, loading,
  empty, or error states, pass `components=["component-id", ...]` for the components that are
  actually present in that screenshot. Do not turn a required state-specific vet into a
  whole-screen vet that fails on components the state correctly omits.
- The heavyweight stack is not the plan's to start. Only per-run `background(...)` daemons are.
- **There is no `subprocess` escape hatch, and a repair does not get one either.** `ostler qa
  lint` statically allowlists the plan's AST before it is ever imported — `subprocess`,
  `os.system`, `os.popen` and anything else outside that allowlist fail lint regardless of what
  they would have run. If a finding needs a CLI, reach for a tool this repo already opted into
  in `agents.yml`: `qa.tesseract.ocr(image)`, `qa.convert.resize(image, width, height)`, or
  `qa.tool("name").run(*args)` for anything else in the table below. `{{ repo.name }}` has
  opted into:

{% if qa_tools %}
  | tool | command | on this host |
  | --- | --- | --- |
  {% for tool in qa_tools -%}
  | `{{ tool.name }}` | `{{ tool.command }}` | {{ "available" if tool.available else "NOT on PATH" }} |
  {% endfor %}
{%- else %}
  None. This repo's `agents.yml` declares no `qa: {tools: [...]}` opt-in.
{% endif %}

  A tool the repair needs and does not see above is a gap in the opt-in, not something to
  route around with a raw call — `qa.tool("whatever")` raises before it runs anything.

Keep `qa-plan.md` in step with what you changed: the AC/obligation-to-scenario map has to
still describe the module. Do not rewrite sections whose scenarios you did not touch.

## Coverage Has To Be Earned

`ostler qa validate` grades what a scenario's `covers` is worth on two counts. It refuses one
that claims coverage while its body calls no `qa.check`/`qa.require` at all — and it refuses one
that claims an obligation whose `checksDeclared` name a call no scenario invokes. That second
one is the common repair: read the obligation row, and for every declared check invoke the
declared call with exactly its declared arguments:

```python
qa.verify("http_status", response, code=409, title="Manifest Conflict", covers=[OBLIGATION])
```

with the id and the check name as **literal** strings, because the binding is recovered
statically before anything runs. Do not answer it by dropping the id from `covers` — that
narrows the claim instead of proving it, and the evidence map then reports the obligation
`uncovered`.

Read the validator's near-miss sentence literally. If it says the plan already invokes the
exact call against another obligation, widen that existing call's `covers=` list. If it says
the plan invokes the same check with a different argument, reshape the observed object until
the declared argument is true — for example pass the subtree to `qa.verify` so the declared
`path="$.blocks"` remains `$.blocks`, rather than changing the plan to
`path="$.tree.blocks"`. If a scenario currently uses `qa.check` for an obligation whose row
has `checksDeclared`, replace that assertion with `qa.verify`; a boolean check never invokes
the declared observation.

Past those counts, an assertion on a runner's exit banner — `result.returncode == 0`, any bare
`EXIT:0` — proves the suite is green and is indistinguishable from a suite that skipped every
case. When a finding cites a scenario like that, the repair is a real oracle — something the
command prints about the behaviour, or an assertion on the surface — not a reworded objective.

## Dry-Run The Scenarios You Repaired

The stack is already up. **This is a contract, and a workflow node checks it.** Before
returning, execute — each on its own, into its own out-dir:

- every scenario listed under "Scenarios that failed the last run", and
- every scenario you changed.

```bash
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> \
  --scenario <scenario-id> --out-dir <scenario-id>
```

**One label per scenario, named after the scenario.** `--out-dir` takes a label, not a path —
one name, no slashes — and the run lands in
`{{ workhorse_var('qa_scratch_dir') }}/<scenario-id>/`, inside the directory the repo already
ignores. The runner deletes its out-dir at the start of every run, so a shared scratch
directory keeps only the last scenario's evidence and every earlier one reads as never run. The gate opens
`{{ workhorse_var('qa_scratch_dir') }}/<scenario-id>/qa-run.ndjson` for each id and requires
it to exist, to contain at least one assertion, and to contain no `FAIL`. A missing directory
fails the same way a failing assertion does, and the repair comes straight back to you.

The scored ledger is what you get by *omitting* the flag, and its own files —
`{{ workhorse_var('qa_dir') }}/qa-run.ndjson` and `run-manifest.json` — are what the evidence
gate reads, so a scenario tuned until it passed cannot leave its own proof.
Fix what does not resolve and run it again. One call settles what no amount of re-reading does:
a locator matching zero elements, a straight `'` where the fixture has `’`, a credential that
disagrees with the seed script. Each of those otherwise costs another full workflow lap — and
that is the whole reason this is mandatory: an edit nobody executed is a guess, and the flow
was paying a complete suite run to find out it was wrong.

If a scenario cannot be made green because the **product** is wrong, leave it red and say so
in `notes`, naming the assertion and what the product does instead. Do not edit product code,
and do not weaken the assertion to make the dry run pass: a plan bent until it agrees with a
broken product is the one outcome this whole lane exists to prevent, and it is worth more to
the run to spend a repair lap saying "the product is wrong" than to hand back a green plan
that proves nothing.

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
  "notes": "R2: scenario `create-document` now asserts the new row after the dialog closes.",
  "repaired_scenarios": ["create-document"]
}
```

`notes` names each finding you closed and how. A finding you did not close is named there
too, with why.

`repaired_scenarios` lists the id of **every scenario whose code you changed**, added ones
included. It is what the dry-run gate checks on top of the failing set, because a rewritten
scenario the last run passed can be broken by this turn and nothing else would catch it. Name
one you did not dry-run and the gate refuses the repair — the claim is checked against the
scratch logs, never taken on its word.

### When no repair of this plan would close the finding

Return `{"status": "blocked", "notes": "...", "repaired_scenarios": []}` instead, and **only**
when the finding cannot be closed by changing the plan at all: what it asks the plan to drive
does not exist to be driven, the repair needs a credential, deployment or product decision that
is in neither the story nor the plan, or it lives in a repo you were not given. A repair that is
merely hard is not blocked — repair it. A repair budget that runs out is not an ending here, and
neither is this: a `blocked` turn stops the alternation between planning and repair and hands
the story to an operator, which is why `notes` must name the specific dependency and what you
attempted. Never weaken or delete a scenario so the dry-run goes green — that closes the finding
by deleting the question, and the run then proceeds as though it had been answered.
