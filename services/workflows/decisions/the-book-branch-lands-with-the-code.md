story: none
date: 2026-11-22
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/shared/branches.py::cut_run_branch, workflows/src/workhorse_workflows/coder/main/nodes/pr.py::open_run_prs, workflows/src/workhorse_workflows/coder/fix_ci/merge.py::merge_pr

The coder opens the book branch as a worktree of the artifacts repository on the code branch's name. The worktree goes into
`worktree_dir`, or the user data directory when none is set. A run that keeps the book in its repository with
`book.home: repo` opens none. The artifacts folder itself is never switched off its base, so a run's book commits
never touch the branch a person has checked out there.

A local merge of the code lands the book right after it. The book branch is rebased onto the artifacts base and
fast-forwarded, so the artifacts history gets no merge commit. A conflict keeps the branch open and the log names the
files.

Code that went out as a pull request keeps the book branch open. The run's log names `ostler book land --branch <b>`,
so the book lands when the code does. An artifacts repository with an origin and a token gets its own book pull
request instead. `merge_pr` lands the book branch after it merges the code, when the artifacts repository has no origin.

A run that commits straight with `delivery="commit"` commits its book on the artifacts base and opens no branch.
