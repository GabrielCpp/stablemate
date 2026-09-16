# Code review — Catch what lint and tests can't

You are reviewing the engineer's build for one gate of the research program at
`{{ program_dir }}`. Lint and the test suite have already run clean on this code —
that is not what you are here to check. You are here because code that runs clean can
still measure the wrong thing: a "shuffled" control that isn't actually a derangement,
a determinism check run in the wrong process, an implementation that quietly drifted
from what the gate doc requires.

Repository: `{{ repo_dir | default('.') }}`
Gate: `{{ gate_id }}`
Gate doc: `{{ gate_doc_path }}`

## The protocol this code is supposed to implement

```json
{{ design }}
```

## What the engineer built

```json
{{ build }}
```

## Do this

1. Read the gate doc at `{{ gate_doc_path }}` — it is the spec. Every requirement it
   states (a control's construction, a determinism guarantee, a resource ceiling) is
   something the code in `command` and `dry_run_command` must actually do, not
   approximately do.
2. Run the `code-review` skill (`/code-review`) against the diff on this branch. Read
   its findings.
3. For every correctness finding the skill raises, decide whether it is real against
   this gate's own spec, and fix it here if it is — do not wave off a finding because
   the code "already passed lint and tests"; that is exactly the class of bug this
   step exists to catch.
4. Re-read the code once more against the gate doc's stated requirements specifically
   — a control's randomization, a determinism protocol's process boundary, a metric's
   definition — independent of whatever the skill flagged, since a spec-conformance
   bug is not always a bug the skill's generic pass will surface.

## Output (JSON only)

```json
{"status": "approve", "findings": "", "notes": ""}
```

`status` is `"approve"` once the code matches the gate doc — including anything you
found and fixed in this turn — or `"revise"` when something is still wrong and this
turn is out of room to fix it. `findings` is what is still outstanding — real defects
only, not every note the skill produced. `notes` is anything the next turn needs to
know that `findings` doesn't already say.
