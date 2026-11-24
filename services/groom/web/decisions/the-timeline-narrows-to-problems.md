story: SM-01M6CQJNNXA713XBDHEJR1FABM
date: 2026-11-23
elements: RunDetail
sources: groom/groom/problems.py, groom/groom/activity.py, groom/groom/assets/dashboard.js

An operator who opens a run to find what went wrong wants the problems alone, in the place the run's timeline keeps them. The Activity tab answers a Problems control that narrows the timeline to them, and a count on the tab that says how many there are.

Every count of problems reads `problems.found`: the attention tile, the activity's `problems`, the Problems control, the tab count, the rows the view lists and the stops of `e`. This keeps `the-attention-tile-counts-problems-by-one-definition`, so the number on any of them never differs from another for the same telemetry.

A backend retry is a repeat agent turn in one visit, not a `retry` event, because on real runs most repeats follow an attempt that did not fail and many carry no event. The retry's reading says only that the backend started the turn again. It adds the failure and the wait only when the spans record them, because the cause is not in the data.

A failed agent turn shows once in the whole timeline, as its turn row marked failed, and stays one stop for `e`. The Problems view lists it as a failed row that opens the turn. A gate check that is dirty and also ended in error counts once.

The tab count reads the activity's count while Activity shows and the Overview's standing otherwise. Both come from the same definition, so they never disagree on the same telemetry.

Pressing Problems, or opening it from the attention tile, selects the view's newest row when the selection is not in the view, because the view opens at its newest row. A selection inside the view stays, and turning the view off keeps it. This keeps `the-timeline-groups-by-work-item-pass-and-visit`, where the group of a selected row stays open. Search and the work item selector narrow the view as they narrow the whole timeline, as `the-timeline-moves-by-keys-and-narrows-by-search` keeps.

While paused in the view, the pill counts only the new problem rows and says 'new problems'. This keeps `the-activity-timeline-follows-a-live-run`.

The churn row and its pane head read CHURN, as the mockup writes it, and the accessible name keeps 'churn alert' so a screen reader says the words.

The elements are declared and not played, because the book's groom holds only pushed runs, which report no spans, so the timeline has no rows and no bar. The browser tests in `groom/tests/test_activity_problems_dynamic.py` play them against real spans.
