---
description: "Get an epic branch's CI green, then make it merge cleanly into its base: read the failing logs, fix each cause, prove it locally and commit. The coder fix_ci subflow by hand. Nothing is pushed or merged."
argument-hint: "<epic branch> [base branch]"
---

# Get $ARGUMENTS green and mergeable

This command does by hand what the coder `fix_ci` subflow does
(`workhorse-coder run fix_ci`). `$ARGUMENTS` names the epic branch, then an optional base
branch to merge into. You own the diagnosis, every fix and the local proof. You do not push,
open or merge a pull request. The person running this pushes and merges.

## 1. Confirm the branch

Run `git branch --show-current`. It must be the epic branch. When it is not, stop and say
so. Do not switch branches in a checkout someone else uses.

**Done when** the epic branch is checked out.

## 2. Read the failing logs

Read CI through the Actions REST API, because a fine-grained token cannot read check runs.

- `timeout 60 gh run list --branch <branch> --limit 5` lists the latest runs.
- `timeout 60 gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[] | {id, name, conclusion, failed_steps: [.steps[] | select(.conclusion=="failure") | .name]}'`
  names each failing job and step.
- `timeout 120 gh api repos/{owner}/{repo}/actions/jobs/<job-id>/logs` returns a job's log.

**Done when** each failing job has its failing command and the log lines that show why.

## 3. Diagnose and reproduce

For each failure, name the cause and whether it lies in the repository's code or outside
it: a flaky runner, a missing secret, a service the job cannot reach. Run the failing job's
commands locally with the repository's own targets or the exact command from the workflow
file, each under a timeout. A failure that shows on some runs is a race. A failure you
cannot reproduce is still a failure. Fix it from the log and say so.

**Done when** every failure has a cause, and each cause in the code is reproduced or
explained from the log.

## 4. Fix and verify

Repair the root cause of each failure in the repository's code: generated-file drift,
formatting, a failing test or a build break. Keep the change to what CI flagged. Do not
add or change a user-facing contract, such as an endpoint, screen, command or format. When
CI can only go green through such a change, stop and report the change it would take.
Re-run the failing commands and leave them green. Commit on the epic branch with an `Epic:`
trailer and no `Story:` trailer.

**Done when** every failing command exits 0 locally on the last commit.

## 5. Merge the base

Skip this step when no base branch was given.

1. `timeout 120 git fetch origin <base> <branch>`.
2. Check for a stale remote. When `git merge-base --is-ancestor origin/<branch> HEAD`
   fails and `git cherry origin/<base> origin/<branch>` prints only `-` lines, the remote
   branch is a duplicate of work already in the base. Stop and report it. Replacing it
   takes a force push, which the person decides.
3. `timeout 120 git merge --no-edit origin/<base>`. Do not rebase.
4. Resolve each conflict by keeping the intent of both sides. Regenerate generated files
   with the repository's codegen command instead of merging them by hand. A conflict that
   needs a product decision aborts the merge with `git merge --abort`. Report it.
5. Run the touched layers' gates again, each under a timeout. Commit the merge as
   `chore(<package>): merge <base> into <branch>`.

**Done when** the branch holds the base, the gates exit 0 and the tree is clean. Report
each cause you fixed, each one outside the code, and the commits left to push.
