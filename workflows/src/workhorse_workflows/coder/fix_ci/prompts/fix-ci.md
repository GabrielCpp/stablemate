# Epic Workflow — Fix CI Stage

You are running the **fix CI** stage of the autonomous epic workflow.

The pull request for epic `{{ ci_epic }}` (branch `{{ ci_branch }}`) is **failing its GitHub checks**. Your job is to make the CI green by fixing the underlying problem and committing the fix on this branch. A later step pushes your commit and re-checks CI — do **not** push yourself.

## What CI reported
{{ ci_summary }}

{% block repo_ci_guide %}{% endblock %}

## Steps

1. **Confirm you are on the epic branch.** Run `git branch --show-current`; it must be `{{ ci_branch }}`. If not, stop and report failure (do not switch branches).
2. **Get the real failure.** Inspect the failing runs via the **Actions REST API**, not `gh pr checks` / `gh run view` — those read the *check-runs* resource, which a fine-grained PAT cannot access (HTTP 403 "Resource not accessible by personal access token"). The `ci_summary` above lists the failing workflow(s) as `name#<run-id>(conclusion)`. For each run id:
   - `timeout 60 gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[] | {name, conclusion, failed_steps: [.steps[] | select(.conclusion=="failure") | .name]}'` to see which job/step failed (`{owner}/{repo}` are auto-substituted from the origin remote).
   - `timeout 120 gh api repos/{owner}/{repo}/actions/jobs/<job-id>/logs` for that job's full log text (this endpoint IS readable with Actions:Read; `gh run view --log` is not).
   - Reproduce locally with the repository's own bounded `make` targets where possible (e.g. format, lint, codegen drift, unit/integration tests). Every command you run must be wall-clock bounded (`timeout ...`), per the repo CLI conventions.
3. **Fix the root cause**, not the symptom. Common CI failures here: generated-file drift (re-run codegen and commit the result), formatting (this repo's own format target), failing tests, or build breaks. Keep the change minimal and scoped to what CI flagged — do not refactor unrelated code. This stage may not add or change a user-facing service, screen, component, command, endpoint, flow, concept, format, or other observable contract because no story documentation context exists here. If CI can only be fixed by changing such a contract, make no commit and report `failed` for operator/story-level resolution.
4. **Verify locally** that the gate you fixed now passes (re-run the same bounded command).
5. **Commit on the epic branch**, each commit carrying `Epic: {{ ci_epic }}` as a trailer,
   spelled exactly so — the run record ties a commit back to its epic through it. Do **not**
   push and do **not** open/merge a PR — the workflow handles the push and re-check.

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}

Answer after you have committed your fix, or concluded you cannot.
