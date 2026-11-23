story: SM-01M6CQJAC2PDSF75N01TSA85H0
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/activity.py, groom/groom/flows.py, groom/groom/churn.py

An operator who remembers a moment by where it sat in the run, such as the second qa pass of one work item, needs the Activity list to say so. The list groups the run's moments by work item, then by flow pass, then by visit. A run with no work items groups its passes directly under the top level.

A heading's time and cost equal the Overview's figures for the same work item or flow, and the heading writes them with the Overview's formatter. A heading that rounded to whole minutes while the Overview read minutes and seconds sent the operator comparing two numbers for one thing. Item time counts agent turns only, as `the-breakdown-traces-cost-to-a-node-or-a-work-item` says, and the item heading's hint says so. A pass counts steps that ran no agent too, so the passes below an item can add up to more than the item. The passes of one flow add up to the flow's row.

Passed steps fold into one row, "N steps · time · all passed", and a failed step stands as its own row between folds. A failed step, a gate, a backend retry and a churn alert each get a row whose mark differs by more than color: ✕, ?, ! and ! with the kind's name in words. Retry and churn share the mark and differ by name, because both mean the run is spending effort on a problem and the name says which.

Churn rows replay from the stored spans through the same counting the attention tile uses, as `the-attention-tile-counts-problems-by-one-definition` says, so they come back after groom restarts. A backend retry is a note on the node's span, because workhorse ends the turn before it records the retry. The row shows as soon as the retried turn's span is stored, and its attempt and delay fill in once the node's span is stored.

Finished groups start folded and the group in progress starts open. The group that holds the selected row stays open whatever its fold state, so a selection is never hidden. Selecting a turn reads as it did before grouping, under `a-turn-reads-from-its-own-record`.

The book's groom holds only pushed runs, which report no telemetry, so these elements are declared and not played.
