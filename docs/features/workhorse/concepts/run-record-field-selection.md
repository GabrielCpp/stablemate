---
type: concept
slug: run-record-field-selection
title: Run record field selection
---
# Run record field selection

`RunRecord`'s fields partition into purpose groups, each answering a distinct question a
reader of `run.json` may need answered. Two groups sit under this symbol:

- **Process-death detection** — `previous_process_died_at` paired with
  `previous_process_pid`. Stamped by a resume that found the previous attempt's recorded
  PID no longer running on this host; the timestamp tells groom the run is not just wedged,
  and the PID is preserved only for forensic inspection. See
  [run record process-death field selection](run-record-process-death-selection.md) for the
  full reading rule.

- **Worktree dispatch** — `worktree_path` paired with `worktree_branch`. Both are set once
  at dispatch when the run was launched with `--worktree`, and both are carried unchanged
  across every resume. Both are empty when the run used the invoking repo directly.

These groups do not overlap: the process-death fields record what happened to the previous
process, while the worktree fields record where this run was dispatched. Reaching for one
when the question is the other leaves the reader looking at empty values that mean "the
question was not asked", not "the answer is no".

- rule: inspect the process-death pair when the question is what happened to the previous attempt; inspect the worktree pair when the question is where the run was dispatched
