# Epic Workflow — Fix CI Stage

You are running the **fix CI** stage of the autonomous epic workflow.

The pull request for epic `{{ ci_epic }}` (branch `feat/{{ ci_epic }}`) is **failing its GitHub checks**. Your job is to make the CI green by fixing the underlying problem and committing the fix on this branch. A later step pushes your commit and re-checks CI — do **not** push yourself.

## What CI reported
{{ ci_summary }}

{% block repo_ci_guide %}{% endblock %}

## Steps

1. **Confirm you are on the epic branch.** Run `git branch --show-current`; it must be `{{ ci_epic }}`. If not, stop and report failure (do not switch branches).
2. **Get the real failure.** Inspect the failing runs via the **Actions REST API**, not `gh pr checks` / `gh run view` — those read the *check-runs* resource, which a fine-grained PAT cannot access (HTTP 403 "Resource not accessible by personal access token"). The `ci_summary` above lists the failing workflow(s) as `name#<run-id>(conclusion)`. For each run id:
   - `timeout 60 gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[] | {name, conclusion, failed_steps: [.steps[] | select(.conclusion=="failure") | .name]}'` to see which job/step failed (`{owner}/{repo}` are auto-substituted from the origin remote).
   - `timeout 120 gh api repos/{owner}/{repo}/actions/jobs/<job-id>/logs` for that job's full log text (this endpoint IS readable with Actions:Read; `gh run view --log` is not).
   - Reproduce locally with the repository's own bounded `make` targets where possible (e.g. format, lint, codegen drift, unit/integration tests). Every command you run must be wall-clock bounded (`timeout ...`), per the repo CLI conventions.
3. **Fix the root cause**, not the symptom. Common CI failures here: generated-file drift (re-run codegen and commit the result), formatting (`make fmt`), failing tests, or build breaks. Keep the change minimal and scoped to what CI flagged — do not refactor unrelated code.
4. **Verify locally** that the gate you fixed now passes (re-run the same bounded command).
5. **Commit on the epic branch.** Stage and commit your fix with a clear message, e.g.:
   `git add -A && git commit -m "{{ ci_epic }}: fix CI — <what you fixed>"`
   Do **not** push and do **not** open/merge a PR — the workflow handles the push and re-check.

If you cannot determine or fix the failure (e.g. the checks are unreadable, or the failure is infrastructure/flake outside the code), make no spurious commit and report `failed` with a short explanation — the workflow will retry or escalate.

## Output
Respond with JSON only after you have committed your fix (or concluded you cannot):
```json
{"fix_ci_result": {"status": "fixed|failed", "notes": "<what you changed, or why you couldn't>"}}
```
