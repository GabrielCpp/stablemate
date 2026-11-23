story: SM-01M6CP8CERP74W2EBRG0AW3W1K
date: 2026-11-23
elements: RunDetail, Runs
sources: groom/groom/assets/dashboard.js, groom/groom/templates/dashboard.html, groom/groom/sidecar.py

An operator with a run across several checkouts reads each one from inside the run. A Checkout selector at the right of the tab bar replaces the rail's Files and Diff buttons and its repo picker, which go in the same change. Every checkout stays reachable, and the rail keeps Runs, History, Attendant, Dispatch and Settings, as `the-page-has-five-panes` says.

The list comes from the `repos` the sidecar sends with its tree and diff replies, not from `/repos`. The selector names the checkouts the run's own container sees, and the page never reads `/repos`. The names show alone, because the run is already selected, and the workspace root reads '(workspace root)'. `/repos` keeps its run-prefixed labels for the terminal client.

The selector shows only when the sidecar names more than one checkout, and only on Files and Diff. A run with one checkout shows none and reads that checkout.

The choice lives in the browser's memory, per run. It holds across Files and Diff, across a refresh of the diff and across a trip to another run and back. A reload starts again at the first checkout, which is the checkout an empty `repo` reads. A remembered checkout the sidecar no longer names falls back to the first, so the pane never reads empty.

Changing the checkout drops the open file and the collapsed folders of Files, because they belong to the other checkout. Diff reads the new checkout, and its size on the tab follows.

A pane id saved from the old rail, such as Files or Diff, lands on Runs. `j` and `k` skip every form control, the selector among them, so choosing a checkout from the keyboard never moves the run selection.

A native run has no route to files or a diff in the browser. Its Overview shows the checkout path among the run facts.

This keeps `the-details-tab-gave-way-to-activity-files-and-diff`, `the-files-tab-browses-a-runs-checkout-read-only` and `the-diff-tab-reads-a-runs-uncommitted-change`, and completes the selector and rail rules the Files decision leaves to this story.

The book's groom holds only pushed runs, which have no sidecar, so the selector is declared and not played.
