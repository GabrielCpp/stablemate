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
5. **Commit on the epic branch.** Stage and commit your fix with a **Conventional Commit** subject — releases in these repositories are cut by release-please, which reads commit subjects and nothing else, so a non-conforming subject ships to nobody. Use `fix` when the CI failure was a defect in the code, `chore` when it was generated-file drift, formatting or config, and scope it to the package you changed:
   Stage **by explicit path** — never `git add -A`, `git add .` or `git commit -a`, which sweep in
   whatever else happens to be in the tree — and give the commit an `Epic:` trailer:

   ```
   fix(<package>): <what you fixed>

   Epic: {{ ci_epic }}
   ```

   e.g. `fix(api-service): reject an expired token instead of panicking`,
   `chore(web-app): regenerate the API client`. Keep the subject ≤ 72 characters, lowercase after
   the colon, no trailing period. One commit per package you changed.
   Do **not** push and do **not** open/merge a PR — the workflow handles the push and re-check.

## Output
Respond with JSON only after you have committed your fix (or concluded you cannot):
```json
{"status": "fixed|failed|blocked", "notes": "<what you changed, or why you couldn't>"}
```

- `fixed` — you found the failure, repaired it, verified the gate locally and committed.
- `failed` — you understood the failure but this attempt did not repair it, or it looks like
  infrastructure flake. Make no spurious commit and say what you tried; the workflow retries.
- `blocked` — **nothing you can do in this repository would make CI green**, so another attempt
  is the same attempt. The checks are unreadable to this token, the fix needs a credential or a
  deployment you cannot perform, the failure lives in a repo you were not given, or CI can only
  be made green by changing an observable contract — which this stage may not do, because no
  story documentation context exists here. A `blocked` turn hands the epic to an operator, so
  name the specific dependency in `notes` and say what you attempted before concluding it.
