# The anchor: does the cheap paper score predict the expensive one?

The §5 calibration pass. It is not a second score and never becomes one — its only job is
to find out whether `design-score`, which reads epics and stories in a few minutes, says
the same thing as a pass that can also read the app the coder built. Recorded 2026-08-22.

## The verdict

**No mode effect.** Every expectation scored the same in both modes against the same
documents in the same invocation. The paper number is measuring what it claims to.

```
expectation             baseline   control   live
------------------------------------------------------
failure-surfacing       2          2         2
label-coherence         0          0         0
locale-switch           1          1         1
page-delete             1          1         1
screen-reachability     1          1         2      ← variance
session-exit            1          0         1      ← variance
```

Three columns, because two different questions hide in one comparison. **control** is the
same documents judged on paper in this same invocation — a disagreement with it is a real
mode effect. **baseline** is the frozen author-phase scorecard from hours earlier — a
disagreement with *that* is drift, and says nothing about paper-versus-live. The first
version of this pass had only the baseline, reported `session-exit` as diverging, and
would have sent someone to fix a metric whose only fault was having been run twice.

The two `← variance` rows are the honest residual: **±1 level on 2 of 6 expectations,
both citing planning documents the paper pass reads too.** That classification is
mechanical rather than a judgement — the paper pass is forbidden to cite anything outside
`docs/`, so a disagreement resting entirely on an `epic.md` is one the paper pass could
have reached from its own corpus and did not. `session-exit` is the clearest case: the
paper judge grepped `sign out|signed out|logout`, and the epic says "signing out".

**Treat a single-run change of one level on one expectation as noise.** The instrument
resolves a level moving on a *named* expectation, confirmed across runs — not a
percentage moving by 8 points.

## What the pass found in the instrument

Both were rubric holes, and both are fixed:

- **The live note had dropped the paper note's clause** that a feature nobody planned is
  not the planning step's doing. The coder built a sign-out control with an e2e test, and
  the live judge let that lift an expectation the documents left at `absent` — which would
  have scored the coder's instincts as the author's design.
- **The 0/1 boundary never said whether naming a thing in order to exclude it counts.**
  "Deleting pages" under Non-Goals scored `mentioned`; "reload the page *without signing
  out*" scored `absent`, on identical logic. It is now written down as `mentioned`, on the
  ground that an exclusion is a decision someone can review and silence is not.

## The limitation, stated plainly

**Level 3 `operable` was reached by nothing, and that is a budget artifact, not a finding.**
The anchor's coder run built **1 of 9 stories** in six hours and stopped at its ceiling.
Levels 0-2 are decided by the planning documents in both modes, so the calibration above is
unaffected — but this run cannot tell you whether a `covered` plan yields a working feature,
because there was almost no working app to ask.

Two things cost that budget, and both are findings about the coder rather than about this
suite:

- Story one's QA runner blocked on two `from_env` secrets nothing in the sandbox
  provisions, and `setup-fix` spent 61 turns without producing a `qa-stack.yml`. `docs-app`
  is the first benchmark suite with an authenticated surface, so no other suite has ever
  reached this.
- `apply-qa-fixes` averages **38 minutes active per lap**, and story one took four QA laps.

`settle-worktree` also parked on a dirty-tree operator gate — leftover QA daemon logs — and
was answered by hand. `bench.py author` answers the grill gate automatically; nothing
answers this one, so an unattended anchor run stops there.

## Reproducing it

```bash
uv run python bench.py --spec suites/docs-app/benchmark.yaml coder
uv run python bench.py --spec suites/docs-app/benchmark.yaml design-score        # paper
uv run python bench.py --spec suites/docs-app/benchmark.yaml design-score --live # anchor
```

`anchor-scorecard.json` beside this file is the frozen live scorecard. The anchor is meant
to be rare — once per author redesign — and the reason to run it is not to get a number but
to check that the cheap one still deserves to be trusted.
