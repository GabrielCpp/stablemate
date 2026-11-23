story: SM-01M6CP871J1D23N6KMN0Z77FWX
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/projection.py, groom/groom/sidecar_hub.py, groom/groom/gitdiff.py

An operator watching a coder run in a container wants to know what the run changed in its checkout without opening a shell. The Diff tab shows that uncommitted change, read from the run's own checkout by its sidecar.

The tab follows the run row's `sidecar` flag, which groom reads from the sidecar hub when it projects the row. Only a connected sidecar can read a live container's checkout, so a native run, an ended run and a container run with no connected sidecar have no Diff tab. The tab appears within five seconds of the sidecar connecting, and the run header shows a `docker · sidecar` chip while it is connected.

The page reads the diff once when it selects such a run, and once more when a sidecar connects while its run is selected. A run that is not selected costs no read. The tab shows the `+N −M` size of the tracked change before it opens, so the operator sees whether a change exists without opening the tab.

Git has no diff for an untracked file, so those files sit in their own group, 'Not tracked by git yet', and add nothing to the size. A failed read never reads as no change. A failed reply, a rejected fetch and text diff2html cannot parse all say the diff could not be read and offer a retry. An empty diff from a sidecar that sends no `failed` says the tab cannot confirm there are no changes. The read behind this is `a-diff-read-says-whether-it-failed`.

The file header above the lines is the tab's own, with the path, the counts, the word 'uncommitted' and a words-based 'new file', 'deleted file' or rename note, because diff2html's card header carries a badge and no scope. A chain of single-child folders is one tree row. A refresh keeps the old content on screen, marks the bar 'reading…' and keeps the selected file by its path. diff2html renders the lines and escapes file content, and the client sets no other markup from the diff.

The story's criteria 1 and 20 name a Details tab. This story keeps `the-details-tab-gave-way-to-activity-files-and-diff`: the run has no Details tab, the Diff tab sits after Overview, Activity and Files, and the working-tree diff shows only there.

The story's criterion 6 says the tab goes when the sidecar disconnects. The epic's required state and story SM-01M6CP8HF9R9DWZPT3MR7FFZS3 overturn that half. When the sidecar drops, the Diff tab stays marked stale with the last diff kept, and with no diff read it says none was read and offers a retry. The half where the run ends holds: the tab goes and Overview shows.

The book's groom holds only pushed runs, which have no sidecar and no Diff tab, so these elements are declared and not played.
