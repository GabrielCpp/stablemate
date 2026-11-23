story: SM-01M6CP8EWDTQ08DD9GHE30JY34
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/gitdiff.py

An operator judging a coder run reads everything it did on its branch, and the uncommitted change is only the part not yet committed. A switch on the Diff tab chooses between Uncommitted and Since branch start. Uncommitted stays the default, so the tab opens as `the-diff-tab-reads-a-runs-uncommitted-change` describes it, and that decision's rule that the lines equal `git diff HEAD` now holds per view: `git diff HEAD` on Uncommitted and `git diff <merge base>` on Since branch start.

The tab's size and tree follow the view being read. Untracked files keep their own group, 'Not tracked by git yet', in both views and add nothing to the size.

The view names its base as a short commit and the default branch, 'since <short commit> on <branch>', with the full commit and the ref it was found at as the title. The operator can rerun `git diff <commit>` in the checkout and read the same lines.

Three states say so in words and leave Uncommitted working. A checkout whose default branch cannot be found, or whose branch shares no history with it, says where the branch started could not be found and why. A checkout on its default branch says it has no branch of its own to compare. A sidecar too old to report a start says the view needs a newer sidecar, and the page never shows that sidecar's uncommitted diff as this view. A branch with no change says so with its base, and no state reads as no change when the read failed, which keeps `a-diff-read-says-whether-it-failed`.

The switch's position lives in the browser per run, beside the checkout choice of `a-run-with-several-checkouts-chooses-one-inside-the-run`. It holds across a refresh of the diff, another tab of the run, another checkout, and another run and back. Moving between tabs reads nothing more.

The pressed view is marked by weight and an underline as well as by colour, and each button exposes its pressed state and works from the keyboard.

The book's groom holds only pushed runs, which have no sidecar and no Diff tab, so these elements are declared and not played.
