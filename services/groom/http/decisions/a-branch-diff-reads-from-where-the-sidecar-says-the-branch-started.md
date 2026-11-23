story: SM-01M6CP8EWDTQ08DD9GHE30JY34
date: 2026-11-23
elements: ReadDiff
sources: groom/groom/gitdiff.py, groom/groom/sidecar.py, groom/groom/app.py

Only the checkout knows where its branch started, so the sidecar computes the base. It is the merge base of `HEAD` and the default branch, and the default branch is the ref `origin/HEAD` names, else a local `main`, else a local `master`. The reply carries `base`, `base_ref`, `base_branch` and `base_reason`, and the diff is `git diff <base>`, so it holds the committed and the uncommitted change together.

The computation reads local refs only. It fetches nothing, writes no ref and changes no index. Every git call runs with `diff.autoRefreshIndex=false`, because `--no-optional-locks` alone still lets `git diff` rewrite the index of a checkout whose file times changed.

The query parameter is `view`, because Litestar reserves `scope`. A read with no `view`, or an empty one, sends the sidecar no new parameter and returns the uncommitted reply, so the terminal client reads what it read before.

`/diff/` adds `based`, false when the sidecar sent no `base_reason`, so a sidecar too old for the view is told apart from a checkout whose start cannot be found.

A branch view is never answered from a volume, which extends `a-pushed-run-has-no-workspace`, and a git failure or a timeout is a failed read and never a missing start, which keeps `a-diff-read-says-whether-it-failed`.
