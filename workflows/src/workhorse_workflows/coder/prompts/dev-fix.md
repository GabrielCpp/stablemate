# Coder Workflow — Fix Stage

A gate this story must pass reported a failure, and the workflow routed it back to you.
Your only job is to make that gate pass. Nothing else.

- **Gate:** `{{ report.source }}`
- **Where:** `{{ report.cwd }}`{% if report.command %}
- **Command:** `{{ report.command }}`{% endif %}
- **Repair attempt:** {{ report.lap }}

## What the gate reported

{% if report.output %}
```
{{ report.output }}
```
{% endif %}
{% if report.findings %}
{% for finding in report.findings %}
- **{{ finding.target }}** — {{ finding.issue }}
  - Repair: {{ finding.repair }}
{% endfor %}
{% endif %}
{% if changed_files %}
## What this story has already changed

{% for path in changed_files %}- `{{ path }}`
{% endfor %}
{% endif %}

## Steps

1. **Reproduce it.** Run the command above in the directory above, exactly as written. If
   there is no command, work from the findings. Do not substitute a command you believe is
   equivalent — the gate will re-run this one.
2. **Read what it points at.** Open every file and line named in the output. Understand why
   the change made in this story caused it, before editing anything.
3. **Fix the cause, minimally.** Correct the code the gate flagged. Do **not** weaken,
   suppress or delete the gate to make it pass — that removes the check instead of the
   defect. A targeted suppression is defensible only when the rule is wrong for one specific
   line, and then you say why in the notes. Do not refactor or add features beyond passing.
4. **Re-run the command and confirm it is clean.** The workflow re-runs it deterministically
   afterwards, so a still-failing tree simply comes back to you.
5. **Commit what you fixed.** The workflow does not commit on your behalf. Stage **by
   explicit path** — never `git add -A`, `git add .` or `git commit -a`, which sweep in
   whatever else is in the tree — and write a Conventional Commit subject scoped to the
   package you changed:

   ```
   fix(<package>): <lowercase imperative description>
{% if epic %}
   Epic: {{ epic }}{% endif %}
   Story: {{ story_slug }}
   ```

   Subject ≤ 72 characters, no capital first word, no trailing period. Keep the trailers
   exactly as spelled; they are how the run record ties a commit back to its story. **Do not
   push or open a PR** — the workflow owns those.

If one finding cannot be fixed without changing intended behaviour, fix everything else and
explain the one you left in `notes`.
{% if report.source == "lint" %}

### For this gate: lint

The findings are the repo's own standard, not advice. Follow the repo's loaded skills for the
correct fix on each one; a suppression is not a fix.
{% elif report.source == "verify" %}

### For this gate: verification

The gate ran the story's own verification. Make the behaviour it checks correct — changing
the check to match the code is the one repair this stage may never make.
{% elif report.source == "regression" %}

### For this gate: regression

Something that used to pass no longer does, and it is very likely the change this story just
made. Prefer repairing the change over amending the older expectation; if the older
expectation is genuinely obsolete, say so explicitly in `notes`.
{% elif report.source == "tdd" %}

### For this gate: missing tests

The story changed behaviour without a test that would fail if the change were reverted. Add
that test at the level the repo already tests this kind of code, and confirm it fails without
the change. List every test file you wrote or extended in `tests_added` below — the gate
re-runs against that list, so a test you write and do not report still reads as missing.
{% elif report.source == "goal" %}

### For this gate: your own exit conditions

Before implementing, this story's turn wrote down what "done" would look like — the commands
that would be green and the files that would be touched. The output above is that promise
compared to what actually happened.

The repair is to **meet the promise**, not to withdraw it. A command that fails is a command
whose failure the turn already agreed was disqualifying; a file that was promised and never
written is usually work that was planned and then dropped. Finish it.

The one case where the promise itself was wrong is real, and it has its own field. A file that
was promised and then turned out to need no change — a generated file whose regeneration is a
no-op, a path the plan renamed, a branch that already did what the story wanted — is
**retracted**, not manufactured: list it in `retracted_files` and say in `notes` what you
checked to be sure. Editing a file to satisfy this gate when the code was already right is the
one outcome worse than the failure, and a retraction is a claim you are on record for.

Retract only what you have verified. A promise you simply did not get to is unfinished work,
and the repair for that is to finish it.
{% endif %}
{% block repo_fix_rules %}{% endblock %}

## Output

Respond with JSON only, after you have re-run the gate locally:

```json
{"status": "fixed|failed|blocked", "notes": "<what you changed, or why a finding remains>", "tests_added": ["<test file you wrote or extended>"], "retracted_files": ["<promised file that needed no change>"]}
```

- `fixed` — the gate passes now in this directory.
- `failed` — findings remain, but another lap over the same output could plausibly close
  them.
- `blocked` — **no lap of this stage can make the gate pass**: the command does not run here
  at all, the fix demands a behaviour change this stage may not make, or it lives in a repo
  you were not given. Say which, specifically, in `notes`. This ends the laps and hands the
  block to whoever can decide it — it is not a way to stop trying.
- `tests_added` — test files this lap wrote or extended, service-relative. Omit it when this
  repair added none; it is what the tests gate re-reads, not a summary of the change.
- `retracted_files` — promised files this lap verified needed no change, on the `goal` gate
  only. Omit it everywhere else. It withdraws the promise for the next lap; `notes` is where
  the evidence goes, and both are kept in the run log.
