story: SM-01M6CP8HF9R9DWZPT3MR7FFZS3
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/app.py

A sidecar that goes quiet does not mean the run stopped, so the operator keeps the diff they were reading. This overturns the half of `the-diff-tab-reads-a-runs-uncommitted-change` and `the-files-tab-browses-a-runs-checkout-read-only` that removed the tab when the sidecar disconnected. The Diff tab stays, marked stale in words and not by colour alone, with a strip above the diff. The strip says how long ago the sidecar stopped answering, the time the diff was read and that the run may still be working, so an old diff never passes as current.

The kept diff lives in the page's memory, per run, per checkout and per view of `the-diff-tab-shows-the-whole-change-since-the-branch-started`. Nothing new is stored on the server. A reload drops the kept diff, so a run first seen after the drop or after a reload has no Files or Diff tab until the sidecar returns. Only runs the operator selected in this page keep a diff. A view the page did not read before the drop says so in words, and a run selected here whose sidecar dropped before any read says no diff was read.

The strip's Retry now replaces the refresh while the mark shows. `/diff/` falls back to the run's volume, and a volume reply is not the run's live checkout, so a retry the volume reader answers never replaces the kept diff, its time or its selection, and never clears the mark. The page tells the two apart by `served`, which `a-diff-read-says-whether-it-failed` records. A retry that finds no sidecar says the sidecar is still not answering.

A reconnect reads the diff again, clears the mark and the strip, and keeps the selected file when it is still in the diff.

Files keeps no tree. It says the sidecar stopped answering and offers Retry now, as `the-files-tab-browses-a-runs-checkout-read-only` records, and it reads the tree again when the sidecar returns.

A run that ends while the mark shows loses Files and Diff and shows Overview, which keeps the run-ends half of `the-diff-tab-reads-a-runs-uncommitted-change`.

The book's groom holds only pushed runs, which have no sidecar and no Diff tab, so these elements are declared and not played.
