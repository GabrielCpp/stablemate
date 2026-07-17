# Epic Workflow — Resolve Merge Stage

You are running the **resolve merge** stage of the autonomous epic workflow.

The pull request for epic `{{ ci_epic }}` (branch `feat/{{ ci_epic }}` → base `{{ ci_base }}`) **could not be merged**: GitHub refused `gh pr merge` (typically a merge conflict, the branch is behind `{{ ci_base }}` under a "require branch up to date" rule, or — see Step 0 — the remote branch is a stale duplicate of already-integrated work). Your job is to make the branch cleanly mergeable into `{{ ci_base }}`, then commit the result on this branch. A later step pushes your commit and re-attempts the merge — do **not** push, and do **not** run `gh pr merge` yourself, **except** in the Step 0 remediation, which is explicitly allowed to push because there is nothing left to merge.

## Step 0 — Rule out a stale duplicate branch before treating this as a content conflict

This failure mode is common: a prior run's push silently landed in the wrong checkout, or an earlier attempt at this epic was squash-merged into `{{ ci_base }}` under a different PR while the local/remote epic branch kept its own divergent history. When that happens, `origin/feat/{{ ci_epic }}` and local `HEAD` have genuinely diverged, but there is no real conflict to resolve — the remote branch just needs to be replaced with the correct (local) lineage. Diagnose this **before** attempting a content merge, since merging a stale divergent branch in would resurrect superseded work.

1. `timeout 120 git fetch origin {{ ci_base }} feat/{{ ci_epic }}`
2. Check whether the remote epic branch is already an ancestor of local HEAD: `git merge-base --is-ancestor origin/feat/{{ ci_epic }} HEAD`. If this **succeeds**, there is no divergence — skip the rest of Step 0 and go to Step 1.
3. If it fails, you have real divergence. Confirm local HEAD is itself a valid, up-to-date continuation of the base: `git merge-base --is-ancestor origin/{{ ci_base }} HEAD` must **succeed**. If it does not, local is behind base too — this is not a safe stale-duplicate case; skip the rest of Step 0 and go to Step 1.
4. Check whether every commit unique to the remote epic branch is already reflected in base's history, by content (this survives squash-merges, which change commit metadata but not the diff): `git cherry origin/{{ ci_base }} origin/feat/{{ ci_epic }}`. Every line must be prefixed `-` (an equivalent patch already exists in base). If **any** line is prefixed `+`, there is real remote-only content — do not proceed with remediation here; skip to Step 1 (or report `failed` if that content looks like it needs a product decision).
5. Even when every line is `-`, confirm directly rather than trusting the heuristic alone: `git diff --stat origin/feat/{{ ci_epic }} HEAD`. The output should be a small, explainable set of files (e.g. local HEAD simply has additional story work on top). If the diff is large or looks systemic rather than additive, treat the check as inconclusive — skip to Step 1 instead of remediating.
6. Only when steps 3–5 all hold, remediate by replacing the stale remote branch with local HEAD (which is the correct lineage):
   - Capture the exact remote tip and force-push with an explicit lease naming it — never a blind `--force`:
     ```
     actual_remote=$(git rev-parse origin/feat/{{ ci_epic }})
     timeout 120 git push --force-with-lease="feat/{{ ci_epic }}:$actual_remote" origin HEAD:refs/heads/feat/{{ ci_epic }}
     ```
   - If the push fails on an SSH/agent auth error (not a lease rejection), retry over HTTPS using the already-authenticated `gh` credential helper instead of the `origin` remote (`gh auth status` to confirm HTTPS auth is active first): push to `https://github.com/<owner>/<repo>.git` with the same `--force-with-lease` clause. Never print, log, or write any token value.
   - If the lease is rejected (remote moved again since you fetched), re-fetch and re-derive `actual_remote`, then re-run steps 2–5 from scratch rather than retrying blindly — the remote may no longer be the stale branch you diagnosed.
   - Verify the fix landed: `gh pr view feat/{{ ci_epic }} --json mergeable,mergeStateStatus` (poll briefly; GitHub computes this asynchronously). It should settle to `mergeable: MERGEABLE`. Only if the existing PR itself is unusable (closed, errored, no PR found) should you comment on/close it and open a fresh `gh pr create --base {{ ci_base }} --head feat/{{ ci_epic }}`.
   - Report success now (see Output below) — do not continue to Steps 1–5, there is nothing left to content-merge.

## Steps

1. **Confirm you are on the epic branch.** Run `git branch --show-current`; it must be `feat/{{ ci_epic }}`. If not, stop and report failure (do not switch branches).
2. **Get the base.** Fetch and integrate `{{ ci_base }}` into the branch:
   - `timeout 120 git fetch origin {{ ci_base }}`
   - `timeout 120 git merge --no-edit origin/{{ ci_base }}` (a merge commit preserves the per-story history; do **not** rebase, which would rewrite the pushed branch and force-push later).
3. **Resolve conflicts with judgment.** For each conflicted file (`git status`, `git diff --name-only --diff-filter=U`), understand *both* sides before choosing — preserve the intent of the base changes AND the epic's changes; never blindly take one side or delete code to make a conflict disappear. For generated files (OpenAPI/clients, mocks, codegen output), do **not** hand-merge — re-run the repository's codegen command and commit the regenerated result. Read the relevant layer instruction files for any code you touch (e.g. `{{ instruction_ref("go") }}`, `{{ instruction_ref("go-testing") }}`).
4. **Verify locally.** Re-run the touched layers' own bounded `make` targets (format, lint/analyze, codegen drift, tests). Every command must be wall-clock bounded (`timeout ...`), per the repo CLI conventions. The branch must build and its tests pass after the merge.
5. **Commit on the epic branch.** Conclude the merge with a clear message, e.g.:
   `git commit --no-edit` (for the merge) — or if you staged manual resolutions, `git add -A && git commit -m "{{ ci_epic }}: merge {{ ci_base }}, resolve conflicts"`.
   Do **not** push and do **not** open/merge a PR — the workflow handles the push and the merge re-attempt.

If you cannot safely resolve the merge (e.g. the conflict needs a product decision, or the base change fundamentally contradicts the epic), make no spurious commit, leave the working tree clean (`git merge --abort` if mid-merge), and report `failed` with a short explanation — the workflow will retry or escalate to the operator.

> Note: a refusal caused purely by branch protection (required reviews, or required CI checks that never ran) is **not** something you can resolve here. If `git status` shows the branch is already up to date with `{{ ci_base }}` and there are no conflicts **and Step 0 found no stale-duplicate remote to remediate either**, report `failed` with that observation so the workflow escalates to the operator rather than committing a no-op.

## Output
Respond with JSON only after you have committed your resolution (or concluded you cannot):
```json
{"fix_merge_result": {"status": "fixed|failed", "notes": "<what you resolved (content merge, or Step 0 stale-duplicate remediation — say which), or why you couldn't>"}}
```
