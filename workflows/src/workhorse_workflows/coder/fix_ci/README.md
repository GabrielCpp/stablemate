# fix_ci

The ship lane of the coder workflow. One CI owner agent gets each workspace repo's epic
branch green, and the run checks its work between turns. Once every repo is green, the
lane merges the epic into its base.

The lane walks the workspace one repo at a time. It reads the repo's CI first, so a green
branch costs no agent turn. A red one goes to the owner, which reads the failing logs,
diagnoses through a triage subagent, fixes through a fixer subagent and commits. Code then
pushes and polls CI again. A red verdict goes back to the owner as its report, up to the
lap budget in `coder/shared/owner.py`.

A blocked owner, a spent budget, a push that does not land or CI the token cannot read asks
upward. The shared resolver answers it from what is written down, or the run parks on a
gate at `.agents/operator/ci-fix/<epic>/context.md` under the launch repo. The answer
resumes the owner's session. `operator_mode` set to `human` or `operator` skips the
resolver.

The merge runs when the launch passed a base branch. A refused merge goes to a merge turn
in its own session. The turn makes the branch merge cleanly and commits, code pushes, and
the lane walks CI again before it retries the merge. A merge still refused after the lap
budget asks upward like any other block, and flags the PR. The answer resumes at the merge.

## Map

- `flow.py`: the `FixCi` state machine. It polls, runs the owner turn, pushes and polls
  again, merges, and routes a block to the resolver and the gate.
- `merge.py`: the merge itself, and the note it leaves on a PR a person must merge.
- `prompts/fix-ci.md`: the owner's prompt, with its subagent seats.
- `prompts/fix-merge.md`: the merge turn, which resolves what keeps the branch from merging.
