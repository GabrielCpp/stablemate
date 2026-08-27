---
agent: agent
---

# Fix One Failing QA Scenario

QA ran this story's plan and one scenario came back red. Fix **that one scenario**, prove it
green with a dry run, and return. The workflow hands you the rest of the worklist one item at
a time; this turn owns exactly one of them.

This is deliberately narrower than a whole-report fix pass. A batch fix re-reads every finding
on every lap, re-derives the ones it already repaired, and proves nothing until a full suite
run says so at the end — so one wrong guess costs a complete rerun of everything. One scenario
with its own dry-run proof costs one scenario.

## Time budget — {{ node_timeout_min }} minutes

This turn is stopped at its budget ("unbounded" = no cap), and what survives is the file on
disk, not this turn's reply. Being cut is not a failure. Save each edit as you make it, and
dry-run as soon as the scenario is plausibly green rather than at the very end.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`
- QA evidence directory: `{{ workhorse_var('qa_dir') }}`
- **The scenario you are fixing**: `{{ workhorse_var('scenario') }}`
{% if failed_assertions %}- The assertions that failed inside it:
{% for assertion in failed_assertions %}  - `{{ assertion }}`
{% endfor %}{% endif %}
{% if remaining_scenarios %}
Other scenarios are red too — `{{ remaining_scenarios | join('`, `') }}` — and each gets its
own turn after this one. **Do not fix them here.** If a repair you make for
`{{ workhorse_var('scenario') }}` also happens to fix one of them, say so in `notes`; do not
go looking.
{% endif %}

### Prior QA Notes

{{ workhorse_var('qa_notes') }}

The report is `{{ workhorse_var('spec_dir') }}/qa.md`; read the section that names
`{{ workhorse_var('scenario') }}` — the action performed, and the observed-versus-expected
divergence — and read that scenario's function in `{{ workhorse_var('spec_dir') }}/qa_plan.py`.

## Required Context

Read:

- `AGENTS.md`
- this repo's developer / local-stack runbook: {{ find_by_tags("runbook") | default("(none installed — follow `AGENTS.md` and the repo's own documented commands)", true) }}
- the story file, and the plan artifacts beside it
- `qa.md`, limited to this scenario's findings
- the instruction files for the layers you touch, from those this repository installs: {{ find_by_tags("standards") | default("(none installed — follow `AGENTS.md` and the repo's own conventions)", true) }}

## Goal

Make `{{ workhorse_var('scenario') }}` pass against the running system, by fixing the root
cause of the acceptance criterion it asserts.

Root cause, not a narrow patch: within this story's surface, a defect that spans the surface
(state keyed wrong across every field, labels untranslated everywhere, a missing section) is
the fix, not the one field the scenario happened to look at. Genuinely separate scope — a
different surface, a different story — is filed to the backlog and named in `notes`, never
used as a reason to leave this criterion unmet.

## Rules

- Change only what this scenario's failure requires. Another red scenario's repair is another
  turn's work, and a fix that rewrites shared code out from under it wastes both turns.
- Do not rewrite the plan or broaden product behaviour.
- Do not weaken, delete or narrow the scenario to make it pass. A scenario bent until it
  agrees with a broken product is the one outcome this lane exists to prevent. If the
  scenario itself is wrong — it asserts something the story never promised — leave it alone,
  return `failed`, and say so in `notes`: the plan lane owns that repair, not you.
- Add or update tests for a fix that changes behaviour. Before changing a layer's tests, load
  that layer's testing instruction file from the list above and follow it.
- Never edit `qa-evidence.json`, `{{ workhorse_var('qa_dir') }}/qa-run.ndjson` or
  `{{ workhorse_var('qa_dir') }}/run-manifest.json`, and never recompute a manifest hash.
  Those are the scored rerun's output, and the manifest hashes are what `ostler artifact vet`
  checks the other two against — refreshing a hash to match an edited ledger makes `vet`
  report clean on a ledger nobody executed. A coverage claim you believe is wrong is a
  finding for `notes`, not a record to delete.
- Preserve unrelated user changes.

## Dry-Run The Scenario You Fixed

The stack is already up. **This is a contract, and a workflow node checks it.** Before
returning, execute:

```bash
ostler qa run {{ workhorse_var('spec_dir') }}/qa_plan.py --spec {{ workhorse_var('spec_dir') }} \
  --scenario {{ workhorse_var('scenario') }} --out-dir {{ workhorse_var('scenario') }}
```

`--out-dir` takes a label, not a path — one name, no slashes — and the run lands in
`{{ workhorse_var('qa_scratch_dir') }}/{{ workhorse_var('scenario') }}/`, inside the directory
the repo already ignores. The gate opens
`{{ workhorse_var('qa_scratch_dir') }}/{{ workhorse_var('scenario') }}/qa-run.ndjson` and
requires it to exist, to contain at least one assertion, and to contain no `FAIL`. A missing
directory fails the same way a failing assertion does, and the item comes straight back to
you.

Omitting `--scenario` runs the whole plan and writes the *scored* ledger the evidence gate
reads. Do not do that: this turn does not own the scored run, and overwriting it with a
partial one destroys the evidence the rest of the lane is holding.

Fix what does not resolve and run it again. One call settles what no amount of re-reading
does — a locator matching zero elements, a straight `'` where the fixture has `’`, a
credential that disagrees with the seed script. Each of those otherwise costs a full suite
rerun to discover.

You may repair **runner tooling** to make the dry run executable — the ostler venv and its
dependencies, harness wiring, fixture plumbing, a missing browser binary — and say so in
`notes`.

If you cannot get it green, return `failed` with what you tried and what the product does
instead. The workflow decides what happens next; it does not need you to be sure.

## Commit Trailers

Every commit you write carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_slug') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Story Status

Append this scenario's outcome to the `## QA Fix Resolution` section of
`{{ workhorse_var('spec_dir') }}/qa.md`:

```markdown
- **{{ workhorse_var('scenario') }}**: Resolved | Not resolved | Blocked
  - Notes:
  - Verification:
```

Do not set the story's **Status** to `QA passed`. The scored rerun makes that decision, and a
hand-written verdict only forges the artifact the rerun exists to produce.

## Structured Output Requirement

Return this exact JSON object as the LAST thing in your final response — these keys at its top
level, with no wrapper object around them. Any other shape fails to parse and the node is
retried:

```json
{"status": "passed|failed|blocked", "notes": "What you changed, what the dry run showed, and anything left"}
```

- `status` is `"passed"`, `"failed"` or `"blocked"`, lowercase.
- `notes` is a non-empty string naming the root cause, the files you changed and the dry-run
  result.

### `failed` versus `blocked` — the distinction is load-bearing

`blocked` hands the story to an operator. `failed` sends this scenario round again, and the
workflow — not you — decides how many times.

- Report **`failed`** when the defect is real, in scope, and you did not finish it, including
  when it is hard, when you ran out of ideas, or when your fix did not dry-run green. A
  stubborn in-scope defect is not a blocker, and reaching for `blocked` to get out of
  difficult work is the exact failure this stage exists to stop.
- Report **`blocked`** only when no further attempt in this repository could succeed, because
  what is missing is external to it: a credential or deployment you cannot perform, a product
  decision present in neither the story nor the plan, or work in another repo.
- A `blocked` report names that dependency and states what you attempted before concluding
  it. "Blocked, cannot fix" is not actionable and comes straight back to you.
