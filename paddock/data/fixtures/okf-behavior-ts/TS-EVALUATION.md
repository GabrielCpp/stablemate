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

No model run has been scored against this fixture yet. The harness tests pass
(oracle mutants, fixture isolation, packet/receipt/scoring composition, stale-source
rejection); the measured run is the next step and gets its own label.

```bash
uv run --all-packages pytest paddock/data/tests/test_behavior_ts_eval.py -q
uv run --all-packages paddock --data-dir paddock/data --store <store> run okf-behavior-audit --label ts-controlled-v1 --no-pin-project --no-seal --param language=typescript --param max_turns=6
```
