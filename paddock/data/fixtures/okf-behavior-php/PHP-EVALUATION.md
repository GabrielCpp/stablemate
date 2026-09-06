# Controlled PHP behavior audit

## Root Chain

1. Why needed? The TypeScript arm (`../okf-behavior-ts/TS-EVALUATION.md`) measured the
   first table under the generic tree-sitter visitor; PHP is the second table and has
   no ground truth of its own.
2. What decision caused it? The `acme` legacy website book covers PHP controllers and
   Twig templates, and an audit run over it is unbounded until the extractor's detection
   and false-alarm behavior is measured on a source whose truth is executable. Twig gets
   no arm: its grammar is flat, so it has no extractor to measure.
3. How prevented? The same one-function experiment as Go and TypeScript: a `dispatch`
   function in PHP, a control book, and the shared omission/contradiction mutations of
   `_behavior_eval.variant_book` against identical source, with a dependency-free PHP
   script as the oracle, printing TAP.
4. Core property: a `throw` is a `raise` candidate and an early `return` a `return`
   candidate, each with a line the rubric can name; a top-level function is public by
   the language's own rule (`exported: true` without an export keyword), so the table's
   `module_public` knob, not a spelling rule, decides the tier.
5. Shape checks: the task selects the fixture from `language=php`; no live book, seed,
   prompt or verdict changes. Curated truth and the oracle stay outside the witness. The
   oracle runs under the `php` binary on PATH or, failing that, the official
   `php:8.3-cli` image under Docker; neither present is an assertion failure, not a
   green skip.
6. Prediction: the oracle rejects all four source mutants (error, empty, success
   status, append-versus-replace) and observes zero-limit, oversized-limit and
   empty-negative-limit behavior. Confirmed by
   `paddock/data/tests/test_behavior_php_eval.py` on 2026-09-06.

## Contract And Bounds

Three cases: control (no expected defects), omissions (missing throw and empty
branches: `raise` line 5, `return` line 8), incorrect (wrong success status and
append-versus-replace effect: `returns:1`, `does:1`). Each case must prepare one
packet. The PHP arm shares the Go and TypeScript arms' `max_turns` ceiling of six.
`toolchain.json` records `behavior_tree.py` alongside the other extractor hashes.

## Observation

The real Paddock run `php-controlled-v1` on 2026-09-06 assessed all three cases
through `workhorse-okf-builder run audit` against the PHP table of the tree-sitter
extractor (`ostler/behavior_tree.py`). No prompt adjustment, answer-key change,
manual receipt edit, or second benchmark run followed the responses. All
witnesses stayed unchanged. One run was discarded before the model ran because a
relative `--store` broke the `--context-file` path; that was a harness defect,
fixed in `paddock/cli.py`, and the scored run started from a clean stage.

| Case | Curated detection | Missed | Unmatched adverse IDs | Unresolved | Backend attempts |
| --- | --- | --- | ---: | ---: | ---: |
| control | none expected | none | 0 | 0 | 1 |
| omissions | OMIT-ERROR, OMIT-EMPTY | none | 1 | 0 | 1 |
| incorrect | WRONG-EFFECT, WRONG-RESPONSE | none | 0 | 0 | 1 |

Observed detection is **4/4**, with **zero adverse findings on the correct
control** (four claims and four candidates). This is one deliberately selected
function, not a statistical accuracy estimate. Each case has four candidates;
control/incorrect have four claims each, omissions has two. Zero packets omitted,
zero memo hits. Append-versus-replace is `contradicted` ("it does not replace
that list"); wrong status is `partial`, explicitly explained as `sent` rather
than `queued`. Both omission candidates are `missing`. Every case took exactly
one model turn and one backend attempt; output tokens were 902 / 587 / 790 and
wall time 55 / 49 / 82 seconds. The subscription backend reports zero cost.
Exact IDs and statuses remain in the original score.

### Unmatched Findings

The one unmatched ID is the enclosing function contract
`evidence:b9c53ff53ac478fad030b04049772ead34bfffa8c73e400fb3e3dd06f33c070e` in
the omissions case, marked `missing`: the reviewer restated the two seeded
omissions (the negative-limit throw and the empty-input return) as gaps in the
whole-function contract, in addition to marking the two branch candidates
`missing` on their own. The oracle's negative-limit and empty cases confirm both
branches. This is the same overlap the Go run produced on its function contract,
not a new seeded defect and not a false alarm on correct text. This is author
adjudication, not a blinded second reviewer; the raw unmatched count stays **1**.

### Comparison With Go and TypeScript

The same seeded defects on the same function shape gave the same 4/4 detection
in all three languages. PHP matched TypeScript on backend attempts (3 in total)
and on the unmatched count (1), against Go's 5 attempts and 3 unmatched. The
PHP overlap sits on the function contract where the TypeScript one sat on the
remaining `returns:` claim; both are restatements of OMIT-ERROR. One sample
each; the difference is noted, not claimed as significant.

### Twig

Twig gets no arm. The grammar is flat (an end tag is a sibling of its opening
tag, not its parent), so a candidate would have no block to attach a condition
to, and `.twig` files report `unsupported` by design rather than parsing into
unconditioned noise. A template's behavior is audited through the PHP that
renders it.
