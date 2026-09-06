# Controlled TypeScript behavior audit

## Root Chain

1. Why needed? The Go arm (`../okf-behavior-go/GO-EVALUATION.md`) measured the second
   extractor; the TypeScript/TSX extractor (`ostler.behavior_tree`, driven by a
   per-language table) is the third and has no ground truth of its own.
2. What decision caused it? The `acme` `web` book covers 420 TypeScript files, and an
   audit run over it is unbounded until the extractor's detection and false-alarm
   behavior is measured on a source whose truth is executable.
3. How prevented? The same one-function experiment as Go: a `dispatch` service in
   TypeScript, a control book, and the shared omission/contradiction mutations of
   `_behavior_eval.variant_book` against identical source, with a Node test oracle.
4. Core property: a `throw` is a `raise` candidate and an early `return` a `return`
   candidate, each with a line the rubric can name; exportedness is the extractor's
   own verdict (`exported: true` on the `export function`), not a spelling rule.
5. Shape checks: the task selects the fixture from `language=typescript`; no live
   book, seed, prompt or verdict changes. Curated truth and the oracle stay outside
   the witness. The oracle runs under `node --test` with Node's native type stripping
   (Node ≥ 22.18); a missing `node` is an assertion failure, not a green skip.
6. Prediction: the oracle rejects all four source mutants (error, empty, success
   status, append-versus-replace) and observes zero-limit, oversized-limit and
   empty-negative-limit behavior. Confirmed by
   `paddock/data/tests/test_behavior_ts_eval.py` on 2026-09-06.

## Contract And Bounds

Three cases: control (no expected defects), omissions (missing throw and empty
branches: `raise` line 3, `return` line 6), incorrect (wrong success status and
append-versus-replace effect: `returns:1`, `does:1`). Each case must prepare one
packet. The TypeScript arm shares the Go arm's `max_turns` ceiling of six.
`toolchain.json` records `behavior_tree.py` alongside the other extractor hashes.

## Observation

The real Paddock run `ts-controlled-v1` on 2026-09-06 assessed all three cases
through `workhorse-okf-builder run audit` against the table-driven tree-sitter
extractor (`ostler/behavior_tree.py`). No prompt adjustment, answer-key change,
manual receipt edit, or second benchmark run followed the responses. All
witnesses stayed unchanged.

| Case | Curated detection | Missed | Unmatched adverse IDs | Unresolved | Backend attempts |
| --- | --- | --- | ---: | ---: | ---: |
| control | none expected | none | 0 | 0 | 1 |
| omissions | OMIT-ERROR, OMIT-EMPTY | none | 1 | 0 | 1 |
| incorrect | WRONG-EFFECT, WRONG-RESPONSE | none | 0 | 0 | 1 |

Observed detection is **4/4**, with **zero adverse findings on the correct
control** (four claims and four candidates). This is one deliberately selected
function, not a statistical accuracy estimate. Each case has four candidates;
control/incorrect have four claims each, omissions has two. Zero packets omitted,
zero memo hits. Append-versus-replace is `contradicted` ("it does not replace the
supplied list"); wrong status is `partial`, explicitly explained as `sent` rather
than `queued`. Both omission candidates are `missing`. Every case took exactly one
model turn and one backend attempt; output tokens were 821 / 623 / 683 and wall
time 50 / 51 / 54 seconds. The subscription backend reports zero cost. Exact IDs
and statuses remain in the original score.

### Unmatched Findings

The one unmatched ID is `okf:docs/features/dispatch/dispatch.md#dispatch:returns:1`
in the omissions case, packet
`bb4921078a5f83c82ea322535d24b50e45153f592980533be2cad8a6a2477c4b`, marked
`partial`: with the negative-limit exception claim removed, the remaining
nonempty-input success promise no longer states its error exclusion, and the
reviewer cited the negative-limit throw as the counterexample. The oracle's
negative-limit case confirms that counterexample. This is a consequence of
OMIT-ERROR, the same overlap the Go run produced, not a new seeded defect and not
a false alarm on correct text. This is author adjudication, not a blinded second
reviewer; the raw unmatched count stays **1**.

### Comparison With Go

The same seeded defects on the same function shape gave the same 4/4 detection.
TypeScript needed fewer backend attempts (3 versus 5) and produced fewer unmatched
findings (1 versus 3): the Go run's two extra overlaps were the enclosing function
contract restating the two missing branches, which the TypeScript reviewer instead
marked `covered` with the claims it linked. One sample each; the difference is
noted, not claimed as significant.
