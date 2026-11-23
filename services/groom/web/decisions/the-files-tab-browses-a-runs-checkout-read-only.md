story: SM-01M6CP89MHPC9GSEGDMHD2C690
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/projection.py, groom/groom/sidecar_hub.py, groom/groom/sidecar.py

An operator watching a coder run in a container wants to look at the files the run works on without opening a shell. The Files tab lists the run's checkout in a folder tree and shows one file at a time, read only.

The tab exists under the same condition as Diff, the run row's `sidecar` flag, and sits directly before it, so the tabs read Overview, Activity, Files and Diff. Selecting a run reads no tree, so a run nobody browses costs nothing. The first open of Files for a selection reads the tree once. The other tabs of the same run keep the tree, the selected file and the folders the operator collapsed, and read nothing new. Selecting another run resets all three. A gate leaves the tab alone.

A read that did not happen is never shown as an empty result. A tree the sidecar reports as failed, a rejected fetch and a sidecar error with no volume to fall back on all say the checkout could not be read and offer a retry. A file read that failed says `<path> could not be read` and 'This does not mean the file is empty.' An empty file reads 'This file is empty.', and a checkout with no files reads 'This checkout has no files.' An empty answer from a sidecar that sends no `failed` says the page cannot confirm either. The reads behind this are `a-tree-or-file-read-says-whether-it-failed`.

The file's text goes through the page's one highlighting path, beside a gutter of line numbers that screen readers skip, on a band darker than the pane. The tab sets no other markup from a file or a path, so content cannot inject markup. The tab has no control that edits, saves, deletes or refreshes. Retry shows only beside a failed read or a stale tab. The folders, files and the contents region carry roles and names and work from the keyboard, and Close keeps the top right of the run head's first row.

The story's criterion 7 says the tab goes when the sidecar disconnects. The epic's required state and story SM-01M6CP8HF9R9DWZPT3MR7FFZS3 overturn that half. While the page holds a diff for the run, the tab stays, says the sidecar stopped answering, keeps its tree and file, offers 'Retry now' and reads the tree again when the sidecar returns. With no diff held the tab goes. The half where the run ends holds: the tab goes and Overview shows.

This story keeps `the-details-tab-gave-way-to-activity-files-and-diff`: the run has no Details tab, and the working-tree files show only on Files.

The book's groom holds only pushed runs, which have no sidecar and no Files tab, so these elements are declared and not played.
