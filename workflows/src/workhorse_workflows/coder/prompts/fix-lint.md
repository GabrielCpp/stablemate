# Coder Workflow — Fix Lint Stage

You are running the **fix lint** stage. The implementation of service `{{ service }}`
left its lint gate **failing**, and the deterministic gate routed it back to you. Your only job is
to make `{{ lint_command or "make lint" }}` pass in this service — nothing else.

You are in the service directory: `{{ cwd }}`.

## What lint reported

Command: `{{ lint_command or "make lint" }}`

```
{{ lint_output }}
```

## Steps

1. **Read the findings above** and open each file/line they point at. Lint here is the repo's own
   gate — typically `ruff` (Python style/correctness) plus, for a UI service, a static
   **accessibility** check (missing input labels, `<img>` without `alt`, role-less/unnamed
   interactive controls, action attributes on non-interactive tags, push targets with no live
   region). Follow the loaded accessibility skill for the correct fix on a UI finding — add a real
   `<label>`/`aria-label`, a semantic element or `role`, `alt` text, etc. — not a suppression.
2. **Fix the root cause, minimally.** Correct the code the linter flagged. Do **not** broaden ignore
   rules, add blanket `# noqa`, or delete the lint target to make it pass — that defeats the gate.
   Reach for an inline suppression only when the rule is genuinely wrong for one specific line, and
   say why in the notes. Do not refactor or add features beyond satisfying the linter.
3. **Re-run the exact command** (`{{ lint_command or "make lint" }}`) in this
   directory and confirm it now exits clean. A later step re-runs it deterministically; a still-dirty
   tree just comes back to you.
4. **Commit what you fixed.** The workflow does not commit on your behalf. Stage **by explicit
   path** — never `git add -A`, `git add .` or `git commit -a`, which sweep in whatever else is in
   the tree — and write a Conventional Commit subject scoped to the package you changed:

   ```
   fix(<package>): <lowercase imperative description>
{% if epic %}
   Epic: {{ epic }}{% endif %}
   Story: {{ story_slug }}
   ```

   Subject ≤ 72 characters, no capital first word, no trailing period. Keep the trailers exactly
   as spelled above; they are how the run record ties a commit back to its story. **Do not push or
   open a PR** — the workflow owns those.

If a finding is impossible to fix without changing intended behavior (e.g. it flags a deliberate
choice), fix everything else and explain the one you left in `notes`.

## Output

Respond with JSON only, after you have re-run lint locally:

```json
{"status": "fixed|failed|blocked", "notes": "<what you changed, or why a finding remains>"}
```

- `fixed` — the command above exits clean in this service.
- `failed` — findings remain, but another lap over the same output could plausibly close them.
- `blocked` — **no lap of this stage can make the linter pass**: the command itself does not run
  here, the finding demands a behaviour change this stage may not make, or the fix lives in a repo
  you were not given. Returning `blocked` skips the remaining laps rather than re-asking a turn
  that has already said it cannot; QA's own lint gate is the binding one and still sees the
  finding. Name the specific dependency in `notes`.
