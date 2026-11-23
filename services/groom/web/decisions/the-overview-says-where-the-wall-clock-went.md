story: SM-01M6CN64ZGB3KBX2Z3FM9DFE7F
date: 2026-11-23
elements: RunDetail
sources: groom/groom/store.py, groom/groom/overview.py, groom/groom/figures.py, groom/groom/projection.py, groom/groom/cli.py, groom/groom/assets/dashboard.js

A run's wall clock can be more than double its active time, and the operator needs to see why before trusting either
figure. The Overview of a run with a finished node holds four sections for it: where the wall clock went, the models,
the run's facts and the sessions.

The clock has six segments: agent turns, deterministic steps, infrastructure, waits, unclassified time and time stopped
between sessions. An instant that more than one kind covers counts once, in the order the segments are listed from the
last: stopped between sessions first, then a wait, agent, infra, deterministic and unclassified. So the six add up to the
wall time, and the first three add up to the active time of the Active time tile. The legend carries every segment's name
and duration, and the bar is an image named with the same words, so the section reads without color.

A model with no priced turn reads "not reported" and never $0, because a zero would claim the model was free. A model with
some priced turns shows its cost with "N of M priced". The cache read is a share of the context tokens, with the token
count as its tooltip, because a share compares models of different sizes.

The facts are the start time, branch, run id and run directory, each with a copy button that confirms the copy in a status
note a screen reader announces, or says it could not copy. A native run adds its checkout path. A container run has none,
because its workspace volume is a name on the container host and not a path the operator can open. A run with no finished
node shows only the facts of the four sections, because it has no time, model or session figures yet.

Each session row gives its start, its active time, the gap until the next session and how it stopped, from the ending of
its root span. A session with no recorded ending says "no recorded ending". The last session of a running or blocked run
says "running", and a run that stopped never claims it.

All four sections read `run_profile` through `figures.read`, the same read as `groom profile` and `groom cost`, and the
Overview query carries them with its other figures, so they refresh with the same figures revision. `groom profile` prints
the models and sessions in the same words.

This keeps `the-attention-tile-counts-problems-by-one-definition`, which defines a session as a resume generation, and
`the-details-tab-gave-way-to-activity-files-and-diff`, which moved the run facts into the Overview.
