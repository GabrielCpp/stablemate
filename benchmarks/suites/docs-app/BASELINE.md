# The baseline: today's `author`, scored before any fix

The number this suite exists to move. Recorded 2026-08-22, on the first `genesis` +
`author` run of the suite, with no author change of any kind in front of it.

```
design satisfaction    50%   (mean level 1.0 of 2, over 6 held-out expectations)
dead ends per journey  2.3   (7 of 18 steps, across 3 journeys)
entity × operation     page: created, read, updated — never deleted
```

| expectation | level | what the judge found |
|---|---|---|
| `session-exit` | 1 `mentioned` | epic 0001's journey says "reload the page *without signing out*"; no story's criteria put a sign-out control on any screen |
| `page-delete` | 1 `mentioned` | epic 0002 lists "Deleting pages" under **Non-Goals**; no story's criteria delete a page |
| `screen-reachability` | 1-2 | the criteria chain every screen -- sign-in lands on the tree, a tree click opens detail, detail opens edit -- but no criterion requires a way *back*, and the judge splits on whether that is covered |
| `locale-switch` | 1 `mentioned` | a switcher exists, but a criterion requires a fresh view to reset to English, so the choice does not hold |
| `label-coherence` | 0 `absent` | no criterion requires a concept to carry one label across screens; no glossary |
| `failure-surfacing` | 2 `covered` | specific on-page errors for bad credentials, an unreachable service, and an inline save failure |

The two levels this table reports differently from the run first recorded here were both
rubric holes the §5 anchor found, not new author work -- see [`ANCHOR.md`](ANCHOR.md). The
headline is unchanged at 50%: `session-exit` rose out of `absent` once "naming a thing in
order to exclude it" was ruled a `mention`, and `screen-reachability` fell out of `covered`
in the same pass, which is the +/-1 judge noise the anchor measured.

## What this confirms

The run reproduced the original incident on a brief it had never seen scored. It produced
three epics and nine stories, zero operator escalations, nine story reworks, and a
plan that satisfies every bullet it was handed — and an app you cannot sign out of, cannot
delete a page in, and cannot read in French for longer than one screen.

Three findings are worth more than the number:

- **The failure is not uniform.** `failure-surfacing` came out `covered` without being
  asked for, and `screen-reachability` sits on the `covered` boundary, so `author` does
  carry *some* design instinct. The gap is specific, which is what makes it a fixable one.
- **The workflow wrote its own miss down.** Deletion is not an oversight here; epic 0002
  lists it under Non-Goals. `author` considered it and excluded it, which means the fix is
  about what justifies an exclusion, not about prompting harder for completeness.
- **`locale-switch` is worse than absent.** A criterion actively requires the language
  choice to reset — a bullet the brief *did* name, delivered in a shape that makes it
  unusable. A backlog-satisfaction score reads that as satisfied.

The two deterministic lenses agreed with the judge without being told anything: the
entity × operation matrix found `page` created, read and updated but never deleted, and
the journey walkthrough found the two dead ends the expectation list also names, plus
locale not surviving navigation — which no expectation names.

## Reproducing it

```bash
uv run python bench.py --spec suites/docs-app/benchmark.yaml genesis
uv run python bench.py --spec suites/docs-app/benchmark.yaml author
uv run python bench.py --spec suites/docs-app/benchmark.yaml design-score
```

`baseline-scorecard.json` beside this file is the frozen scorecard, so a later run can be
diffed against it rather than against this prose. It is the re-judged one, under the rubric
the anchor corrected; the numbers above are that pass. `author` is one agent run against a
five-bullet brief and one sample is one sample — a later run scoring 55% has not
demonstrated an improvement, and the honest comparison is a level moving on a named
expectation.
