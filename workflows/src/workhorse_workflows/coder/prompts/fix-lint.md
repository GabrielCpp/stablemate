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
4. **Do not commit, push, or open a PR** — the workflow owns those. Leave your fixes in the working
   tree.

If a finding is impossible to fix without changing intended behavior (e.g. it flags a deliberate
choice), fix everything else and explain the one you left in `notes`.

## Output

Respond with JSON only, after you have re-run lint locally:

```json
{"fix_lint_result": {"status": "fixed|failed", "notes": "<what you changed, or why a finding remains>"}}
```
