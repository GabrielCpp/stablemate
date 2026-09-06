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

No model run has been scored against this fixture yet. The harness tests pass
(oracle mutants, fixture isolation, packet/receipt/scoring composition, stale-source
rejection); the measured run is the next step and gets its own label.

```bash
uv run --all-packages pytest paddock/data/tests/test_behavior_php_eval.py -q
uv run --all-packages paddock --data-dir paddock/data --store <store> run okf-behavior-audit --label php-controlled-v1 --no-pin-project --no-seal --param language=php --param max_turns=6
```
