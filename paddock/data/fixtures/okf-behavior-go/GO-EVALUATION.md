# Controlled Go behavior audit

## Root Chain

1. Why needed? The existing controlled evaluation exercises Python, while the latest
   `../okf-behavior/LIVE-RUNS.md` explicitly leaves non-Python coverage unmeasured.
2. What decision caused it? The evaluator selects a captured Python source and its
   answer key; using that score for Go would attribute evidence to unobserved behavior.
3. How prevented? Add an independent Go source/book and executable oracle, then pair
   a correct control with omission and contradiction books against identical source.
4. Core property: a semantic correspondence requires observing both representations;
   a resolving citation or evidence from another language cannot establish it.
   This holds after rewriting the extractor. The terminal change is an explicit
   `language=go` fixture selection at witness preparation, not a synthetic score.
5. Shape checks: the task owns fixture selection and exact-ID scoring; no live book,
   captured seed, extractor, prompt, or verdict is changed. Curated truth and oracle
   stay outside the model witness. The shared mutation function removes error/empty
   claims or changes success status and append to replace, without changing source.
6. Prediction: the independently executable oracle rejects all four source defects
   and also observes zero-limit, oversized-limit, and empty-negative-limit behavior.
   The first run passed all five pytest oracle cases (control plus four mutants).
   The harness test failed before implementation because Python/live-slice cases
   were selected despite `language=go`. JUnit: `.cache/go-behavior-red.xml`.

## Contract And Bounds

Three cases: control (no expected defects), omissions (missing error and empty
branches), incorrect (wrong success status and append-versus-replace effect).
The limit is explicit, not a fictional Go default argument; default behavior is
deliberately outside this four-defect experiment. A non-nil `sent` pointer is the
fixture's calling convention. Nil-pointer and concurrent mutation behavior are
not claimed. No model keyword oracle: detection joins validated adverse IDs to
predeclared kind/line or claim-suffix aliases. Unresolved is not detection credit.

Each case must prepare one packet (80 items / 60,000 serialized characters).
The Go arm caps `max_turns` at six and reserves two workflow turns per case using
the existing audit workflow's bound. Provider-internal retries are distinct from
that bound: the actual backend attempt count must also be inspected. The config is
unchanged OpenCode `openai/gpt-5.6-terra`, effort omitted (default variant). Runs
must use the absolute workspace store and `--no-pin-project`; workspace code is
not a release pin. Source/book hashes, packet claims/digests, receipts, review
contract, turns, and backend token categories are retained in the existing stage.

Oracle compilation runs only on ephemeral copies, with workspace-local pytest
temporary directories and Go build caches. Missing Go is an assertion failure,
not a green skip. The seed zip and captured `okf-behavior/source` remain unchanged.

## Observation

The real Paddock run `go-controlled-v1` on 2026-09-06 assessed all three cases
through `workhorse-okf-builder run audit`, after the concurrent core Go extractor
became available. No prompt adjustment, answer-key change, manual receipt edit,
or second benchmark run followed the responses. All witnesses stayed unchanged.

| Case | Curated detection | Missed | Unmatched adverse IDs | Unresolved | Backend attempts |
| --- | --- | --- | ---: | ---: | ---: |
| control | none expected | none | 0 | 0 | 1 |
| omissions | OMIT-ERROR, OMIT-EMPTY | none | 2 | 0 | 1 |
| incorrect | WRONG-EFFECT, WRONG-RESPONSE | none | 1 | 0 | 3 |

Observed detection is **4/4**, with **zero adverse findings on the correct
control** (four claims and four candidates). This is one deliberately selected
function, not a statistical accuracy estimate. Each case has four candidates;
control/incorrect have four claims each, omissions has two. Zero packets omitted.
Append-versus-replace is `contradicted`; wrong status is `partial`, explicitly
explained as `sent` rather than `queued`, not an abstention. Both omission return
candidates are `missing`. Exact IDs and statuses remain in the original score.

### Unmatched Findings

Independent reading against the unchanged source and executable oracle classifies
the three unmatched IDs as overlapping descriptions of the seeded defects, not
three additional detections or three automatic false positives. This is author
adjudication, not a blinded second reviewer. The raw unmatched count stays **3**.

1. Omissions, packet `47c3bc20a247d8bc19eb2f38688ad6348fc137779b3b292463b851fa0056fd2f`:
   `evidence:461d16d380a85881f00486bb8f3f36b204782237c62ac4b730cde6c20a42ebde`
   is the enclosing function contract. Its `missing` explanation repeats both
   absent branches already detected by the line-7 and line-10 return IDs.
2. Same packet: `okf:docs/features/dispatch/dispatch.md#dispatch:returns:1` is
   `partial`: after removing the negative-limit exception claim, the remaining
   broad nonempty-input success promise no longer specifies its error exclusion.
   The oracle's negative-limit case confirms the stated counterexample. This is
   another consequence of OMIT-ERROR, not a new independent seeded defect.
3. Incorrect, packet `7c043070ba52a36a222c3fae2f27f0b78edf472cb8b5871bee4047201964b543`:
   `evidence:fe2acc3c2d4881b3bf3ca150ada8d0e0b84c7742dd448533a015260063b6e4e6`
   is the success return. Its `missing` explanation asks for `sent` rather than
   `queued`, duplicating WRONG-RESPONSE's partial claim verdict. The real success
   oracle independently observes `sent` and preserves the prior list entry.

No unnecessary semantic correction was identified in that reading. The control
measurement is the stronger false-alarm observation: zero alarms without relying
on post-hoc aliases. The source-target entries in `repairs` are audit output only;
no automatic repair was executed or proven safe.

### Negative Outcomes

The incorrect case's first receipt failed reciprocal claim/candidate-link
validation. Its next invocation failed inside OpenCode with `Failed to execute
statement`; the existing backend retried after 15 seconds and obtained a valid
receipt. Nothing was ignored or counted as an accepted result before validation.
Total: **five backend attempts**, **four receipt-producing workflow turns**, three
accepted packets. No additional model calls were made. `model_turns` in the legacy
task outcome is 1/1/2; telemetry `work.turns` is 1/1/3 and `backend_retries` is
0/0/1. Thus the task's turn bound is not by itself a hard provider-attempt budget;
this measured run nevertheless stayed below the requested six-attempt limit.
Future automation must bound the provider retry layer as well, not infer attempts
from raw receipts. No retry policy was extended here.

Doctor reported zero errors and 3/2/3 warnings (control/omissions/incorrect):
compound-normative wording and missing verification declarations. These are not
semantic detections. The oracle deliberately stays outside the witness, so doctor
does not establish executable QA coverage. Seven unrelated builder-template skill
references warned for each CLI run because the context manifest is empty, as in
the existing controlled harness. No warnings or gates were suppressed.

### Identity And Usage

All cases share source SHA-256
`596d5045accef09951919022c9ca1c546e6a704bccdee9abebddcae8ccdb24ce`.

| Case | Book SHA-256 | Packet SHA-256 |
| --- | --- | --- |
| control | `6ada13ff6c9204cec8dc2b706dd75f8a9294edd8bf73933de85a98c487e3f9a2` | `c525c0f88d931b7e8cc04bb834339fdb84251ff1344abee153eeb70d670d0a4d` |
| omissions | `e15d5d01da219436f9e73cf446d81d6ece195fa9367b0e9035db0237e9414747` | `47c3bc20a247d8bc19eb2f38688ad6348fc137779b3b292463b851fa0056fd2f` |
| incorrect | `f635273eaa9492ee708eb9dfaa3ede851dfb364fc91ced7ecf96fa7d773a1db3` | `7c043070ba52a36a222c3fae2f27f0b78edf472cb8b5871bee4047201964b543` |

| Case | CLI seconds | Input tokens | Output tokens | Reasoning tokens | Cache-read tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| control | 79.75 | 14,795 | 1,112 | 176 | 5,632 |
| omissions | 72.54 | 14,438 | 764 | 424 | 5,632 |
| incorrect | 251.58 | 19,520 | 2,098 | 1,404 | 21,504 |

Total CLI time: 403.88 seconds; deterministic doctor passes: 0.37 seconds.
Token categories are backend-reported and may overlap. The failed backend attempt
has no exported token/cost receipt; totals cover four exported sessions, not a
complete invoice for five attempts. Reported subscription cost is $0; estimated
API-equivalent cost is unknown. No billing or provider configuration was changed.

`toolchain.json` retains the config and extractor hashes. The measured Go extractor
hash is `ca6efd8d09e0eeb102f8b5df00952f56d3a0157a10f1b463d662f0ef78333c87`;
the measured audit prompt hash is
`85fd5aab2cd2b983b7c3bb32adeedc42d0c50ead5fa73a1cdb65c40f92c442a2`.
Each review retains schema/contract binding alongside actual receipts.

### Reproduction And Verification

Run from `/mnt/data/workspace/stablemate`; the existing seed was present and
unpacked successfully, without recapture or ignored seeding errors.

```bash
uv run --all-packages pytest paddock/data/tests/test_behavior_go.py paddock/data/tests/test_behavior_eval.py paddock/data/tests/test_seed_freshness.py -q --basetemp=/mnt/data/workspace/stablemate/.cache/go-behavior-final --junitxml=/mnt/data/workspace/stablemate/.cache/go-behavior-final.xml
uv run --all-packages paddock --data-dir paddock/data --store /mnt/data/workspace/stablemate/.cache/behavior-paddock run okf-behavior-audit --label go-controlled-v1 --no-pin-project --no-seal --param language=go --param max_turns=6
make lint
git diff --check
```

The label is already used; a new measurement requires a new label and budget.
Stage: `.cache/behavior-paddock/work/okf-behavior-audit/go-controlled-v1/stage/`.
The stage is retained with `--no-seal`, not a claimed archived result zip.
Inspect `score.json`, `steps.json`, `artifacts/cases/{trials,toolchain,outcomes}.json`,
each case's preparation and witness, and `runs/*/behavior-audit.json`, raw receipts,
review contracts, turn prompts, transcripts, and telemetry. No Go build artifacts
were written into fixture source directories.

Verification: **70 tests passed** in 144.34 seconds, including unchanged seed
freshness, real Go oracle mutation rejection, sandbox fixture isolation, real
packet/receipt/scoring composition, stale-source rejection, and abstentions that
contain all defect keywords but earn zero detection credit. The initial parallel
verification timed out; that partial run is not counted as green. Root Ruff and
ty passed. Root basedpyright failed on separately owned
`saddlebag/saddlebag/browser.py:167` (`reportAssignmentType`, possibly empty tuple
unpacked into one target). This is outside `paddock/data` and was not edited or
suppressed. Full root lint is therefore **not green**. `git diff --check` passed.

This experiment does not measure Go HTTP handlers, struct tags, route registration,
interface dispatch, imported helper closure, whole-book completeness, or a no-AST
comparison arm. It measures one in-memory service with explicit inputs and full
function context, once per book variant. See `../okf-behavior/EVALUATION.md` for
historical Python/slice measurements and `../okf-behavior/LIVE-RUNS.md` for the
separate live-run record. No live builder was operated, no live book was repaired,
and no commit or push was made. No new workaround or waiver was added; the inherited
provider-retry accounting limitation and external lint failure remain explicit.
