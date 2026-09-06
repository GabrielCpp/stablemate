# Controlled behavior audit evaluation

## Follow-up experiments, 2026-09-06

The original v1/v2 results below remain historical measurements. Subsequent runs
used the same `openai/gpt-5.6-terra` default variant, now requested by omitting
effort rather than using an unsupported spelling. They measured the uncommitted
toolchain explicitly, with unchanged source witnesses and separate post-repair
book truth. These are single samples, not statistical accuracy estimates.

| Experiment | Controlled detections | Curated Stablemate detections | Unmatched repair targets |
| --- | --- | --- | --- |
| Original v2 controlled / v1 Stablemate | 4/5 | 0/2 | 5 controlled, 4 Stablemate |
| `context-v3c`: enclosing source and same-node book context | 5/5 | not run in this round | 0 |
| `stablemate-context-v3`: same context change | not run | 1/2 | 1, false alarm caused by absent helper evidence |
| `stablemate-support-v4`: explicit helper sources | not run | 2/2 | 0 |
| `stablemate-repaired-v5`: two corrected book claims | not applicable | both original contradictions now supported | 1 new, independently reproduced defect |

The workhorse comparison slice had zero adverse findings in v3. V4 assessed only
the two defective slices. V5's new finding is not a failure of either correction:
invalid UTF-8 checkpoint contents raise `UnicodeDecodeError`, contradicting the
unchanged broad claim about unreadable checkpoints. The default `run_dir=""`
documented only in a signature remains unresolved because receipts require a
normative claim link. Neither has been waived.

### Root-cause chains

1. Why was context preservation needed? Isolated snippets produced false repairs
   and missed the incorrect side-effect claim. What decision caused it? Extraction
   removed preceding mutation/guard statements and the authoring context; the
   reviewer could not retrieve them. Prevention: retain deduplicated enclosing
   source and same-node book excerpts. Core property: a statement's behavior is
   determined by its surrounding execution/data flow, not syntax alone. Excerpt
   spans and file digests bind the evidence, and the full context counts toward
   packet budgets. Prediction confirmed: the unchanged side-effect mutant is now
   detected and all five controlled false repairs disappear.
2. Why was helper context needed? Groom's caller-only review could not establish
   `parse_position` normalization and falsely inferred an error escape. What
   decision caused it? The packet separated the caller from the function that
   determines the behavior. Prevention: explicit `context_paths` resolve selected
   helper files into hashed source excerpts without expanding the obligation
   denominator. Core property: a caller's behavior includes delegated effects.
   Prediction confirmed: supplying the helper both detects GROOM-NONOBJECT and
   removes the malformed-JSON false alarm. Helper-only changes invalidate receipts.
3. Why were book edits needed? The book attributed intermediate helper values to
   public boundaries. What decision caused it? Authoring treated the parsed JSON
   object and inbox `(body, scope)` tuple as the returned contracts. Prevention:
   document the actual projections and output schema, with distinguishing
   observations. Core property: intermediate representations do not determine
   what a boundary returns. The original claims moved from contradicted to
   supported after editing the two books, with all five source/helper hashes
   unchanged. The independent repaired-state fixture rejects unrepaired inputs
   and does not suppress additional findings.

### Remaining causes and next experiments

1. Decoding claim: the book generalized an `OSError` handler to all unreadable
   inputs. Exception classes distinguish failures even when ordinary prose groups
   them. The invalid-UTF-8 boundary regression now reproduces the distinction;
   correct that contract and observe it again rather than broaden the handler to
   accommodate the book.
2. Signature coverage: the audit accepts only normative obligation IDs as book
   evidence, while OKF also stores contracts in signatures and other context.
   Evidence exists but cannot be represented by the receipt. Add resolvable,
   digest-bound document evidence references rather than force duplicate prose or
   label the default an implementation detail. This is not fixed yet.
3. Receipt overhead: v3 required one repeated turn for a mistyped digest; both v4
   cases required repeated turns for inconsistent reciprocal links. Identity and
   graph edges are deterministic data, but the output contract asks the model to
   copy the digest and emit each edge twice. A future experiment should bind the
   response at dispatch and represent each edge once, preserving strict validation
   rather than weakening it or increasing retries.
4. Support selection is explicit, not automatic import closure. The selected
   evidence now suffices for these cases, not arbitrary repositories. Automatic
   dependency retrieval needs grounded resolution and cache invalidation before
   claiming unattended whole-book coverage. Functions with no extracted candidate,
   non-Python sources, and non-normative prose remain coverage limitations.
5. Relative Paddock store paths failed after changing subprocess working directory:
   the producer passed a caller-relative path into another coordinate system.
   The measured rerun used an absolute workspace-local store; normalization at
   the harness boundary remains a separate fix, not an audit-quality improvement.
6. These tests use a deliberately empty context manifest; the CLI warns about
   seven unrelated builder-template skill references. The packet-only audit does
   not consume those templates. Whole-builder measurement must use the installed
   manifest rather than suppress the warning.

### Follow-up artifacts

All new stages are workspace-local under
`.cache/behavior-paddock/work/okf-behavior-audit/<label>/stage/`.
Each carries `score.json`, input hashes, actual model receipts, and usage. The
post-repair report is `.cache/behavior-paddock/repair-v5-report.md`, and its exact
book diff is `.cache/behavior-paddock/repair-v5-book.diff`.

V3 controlled review used three turns in 151.8 seconds; v3 Stablemate used four
turns in 199.9 seconds; v4 used four turns in 188.6 seconds; v5 used two turns in
106.7 seconds. These wall times include execution overhead. Reported subscription
cost remains zero with API-equivalent cost unknown, not free usage. Two earlier
workspace-local attempts (`context-v3`, `context-v3b`) produced no accepted model
measurement: the former timed out, and the latter failed before dispatch on its
relative context-file path. No result is attributed to them.

The five originally stopped builders have not been resumed. This round evaluated
and corrected public Stablemate slices only. The private repository is outside the
current permitted file-operation root and has not received a comparable audit.
The original full-book doctor still reports 195 errors and 1,771 warnings; the
two repaired nodes do not make the full books complete.

Root `make lint` passes. The affected evaluator/workflow/Groom selection passed
263 tests; the final evaluator suite passed 33 tests, including the newly found
decoding failure. No gate was relaxed and no runtime behavior changed.

## Result, 2026-09-06

This measures actual OpenCode model receipts from the standalone
`workhorse-okf-builder run audit` flow, not AST keyword detection. Ostler supplies
candidates and validates receipts; only the external model decides whether
behavior is missing or contradicted. Scoring joins exact candidate/claim IDs to a
separate, pre-review answer key. Duplicate candidate/claim aliases count once.

| Corrected fixture case | Detected defects | Undetected defects | False-positive repair targets | Unresolved IDs |
| --- | --- | --- | ---: | ---: |
| control | none expected | none | 3 | 1 |
| omissions | OMIT-ERROR, OMIT-EMPTY | none | 0 | 1 |
| incorrect | WRONG-DEFAULT, WRONG-RESPONSE | WRONG-EFFECT | 2 | 1 |

**Controlled detection: 4/5 (80%).** The non-detection is an explicit abstention,
not a claimed clean bill. The three controls/mutants all retain the same resolving
`service.py::dispatch` citation. Existing doctor reports **0 errors, 1 warning**
for all three: the same undeclared-verification warning, and **0/5 semantic
defects detected**. Citation validity does not distinguish these books.

False-positive counts above mean **unnecessary repair targets**. All five are
`partial` verdicts that the workflow places in `repairs`, not explicit false
`contradicted` verdicts. The model explains that snippet context is insufficient;
the actual frozen source supports those claims. Unresolved verdicts are counted
separately and never earn detection credit. Adjudications retain the exact IDs,
packet digests, and source-based rationale in `adjudications/behavior-exact-v2.json`.

The initial six-turn diagnostic, `behavior-dirty-v1`, used an ambiguous default
mutant: "at most three" also admits two. Its default detection is not accepted.
The fixture was corrected to an **exact default value**, re-captured through
Paddock, and only the three matched controlled cases were rerun as
`behavior-exact-v2`. Total: **nine measured model turns**, no receipt retry.
Artifact-only scoring runs spent no model turns. These are not repeated samples
of an unchanged benchmark and must not be averaged together.

## Stablemate comparison

The following current working-tree slices were frozen before model review.
Source line positions, book paths/anchors, complete original modules/books, and
supporting modules are preserved in each case's `baseline/` and `scope.json`.
Only the selected function is in the extraction scope; surrounding module code
is blanked in the review witness, retaining line numbers. Originals were never
edited. This is a slice evaluation, not a whole-book coverage estimate.

| Service | Source function/lines | Book claim group/lines | Curated detection | False-positive repairs |
| --- | --- | --- | --- | ---: |
| groom | `groom/groom/sidecar.py::_current_node`, 142-152 | `docs/features/groom/concepts/sidecar-snapshot.md#method-_current_node`, 138-168 | 0/1: GROOM-NONOBJECT unresolved | 2 |
| workhorse | `workhorse/workhorse/cli/target.py::groom_live_run`, 48-89 | `docs/features/workhorse/concepts/run-target-resolution.md#groom_live_run`, 27-35 | comparison slice, no curated defect | 1 |
| workflows | `workflows/src/workhorse_workflows/coder/shared/review.py::check_feedback`, 197-213 | `docs/features/workflows/concepts/coder-review-shared-review.md#check_feedback`, 78-92 | 0/1: WORKFLOWS-SCOPE unresolved | 1 |

Groom normalizes parseable non-object JSON through `parse_position`, whereas its
book permits it to raise. Workflows discards `scope` but promises to return it.
These expectations were recorded before review; the model detected neither.
The four unmatched targets were independently adjudicated against the frozen
book/source in `adjudications/stablemate-v1.json`. In particular, the workflow
default is present in a `sig:` bullet, which is excluded from extracted normative
claims. Groom's normal-return behavior is described in `output:`/`algorithm:`
prose but is also excluded; its additional stale details are not credited to a
finding that merely says no normal behavior is documented.

Doctor reports groom 1 error/1 warning, workhorse 1 error/0 warnings, workflows
0/0. Both errors are **slice-induced dangling document links**, not semantic
detections or defects in the original books. All selected code citations resolve.
The baseline is the existing deterministic doctor/citation capability in the
dirty checkout, not a separately checked-out historical release.

Full original-book SHA-256 hashes:

| Book | SHA-256 |
| --- | --- |
| groom sidecar-snapshot | `4508a0bdfa8e6a64dbe63f363283003cf0f44132a83f814593128ef8f363848e` |
| workhorse run-target-resolution | `a93f5dbc3b441686e492a733d135c21c4ffaa1f492e9ec0ea1410fe13a78c838` |
| workflows coder-review-shared-review | `c97cac1c1e285c7df8f3bc293e8eab3097ad04c072f7cec068a164a7110d4a92` |

Full original-module SHA-256 hashes:

| Source | SHA-256 |
| --- | --- |
| groom sidecar.py | `6a1ac478e046321761f93e954cf683d8f5b59ff6e1ed97e64cb19fd325628f7d` |
| workhorse target.py | `9590de02546a7191bd4b061206bf9511a67a8e41ccfa7fe2608e8e7509ca4d41` |
| workflows shared/review.py | `8b413c3466c1bc1b1b3d6c215175281d9c5ac4a0706e53c29994867d12595d42` |

## Preparation and usage

Every case prepared exactly one packet, with no packet omissions. Item and
serialized-character bounds were 80 and 60,000; the flow received `max_packets=1`.
The task reserves two possible attempts before starting another case and stops
at its ten-turn allocation. Actual transcripts contain one review per case.

| Accepted case | Candidates/claims | Preparation seconds | CLI seconds | Input tokens | Cache-read tokens | Output tokens | Reasoning tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| control v2 | 4/5 | 0.071 | 45.04 | 3578 | 7680 | 896 | 552 |
| omissions v2 | 4/3 | 0.014 | 33.85 | 3327 | 7680 | 605 | 126 |
| incorrect v2 | 4/5 | 0.014 | 43.18 | 3584 | 7680 | 862 | 428 |
| groom v1 | 4/2 | 0.020 | 32.24 | 5391 | 5632 | 693 | 253 |
| workhorse v1 | 6/4 | 0.019 | 50.00 | 4504 | 7680 | 1374 | 467 |
| workflows v1 | 4/5 | 0.015 | 37.52 | 3741 | 7680 | 833 | 291 |

Accepted cases: **241.83 seconds** of CLI wall time; corrected controlled cases
alone: **122.07 seconds**, versus **0.302 seconds** for their doctor passes.
The initial diagnostic took 259.5 seconds including its superseded controls;
all nine review invocations took about 381.6 seconds. One initial telemetry
export timed out, so wall time includes exporter overhead. Backend categories
are retained separately because reasoning/cache accounting can overlap.

Model: `openai/gpt-5.6-terra`, subscription OpenCode. Recorded runs requested
literal `effort="minimal"`, which this workhorse adapter does not map, so their
actual transcript variant is **default**, not minimal. The future-run config
now uses `effort="low"`, which maps to OpenCode `--variant minimal`. No result
above is relabeled as a minimal-variant measurement. All calls reported $0;
API-equivalent **estimated cost is unavailable**, not asserted to be zero.
No new spend or billing configuration was introduced.

## Commands and artifacts

Run from the workspace root. The seed zip lives in the local Paddock store, never
in git. Existing app/seed fixtures were not changed.

```bash
uv run --all-packages paddock --data-dir paddock/data seed capture paddock/data/fixtures/okf-behavior/source --name okf-behavior --force
uv run --all-packages paddock --data-dir paddock/data run okf-behavior-audit --label behavior-dirty-v1 --no-pin-project --param max_turns=10
uv run --all-packages paddock --data-dir paddock/data run okf-behavior-audit --label behavior-exact-v2 --no-pin-project --param cases=control,omissions,incorrect --param max_turns=6
```

Those labels already exist; use a fresh label for a new measurement. The captured
configuration, not today's tracked configuration, describes a past run.
Artifact-only rescore commands used:

```bash
uv run --all-packages paddock --data-dir paddock/data run okf-behavior-audit --label behavior-exact-v2-scored --no-pin-project --param replay_stage="$HOME/.local/share/stablemate/paddock/work/okf-behavior-audit/behavior-exact-v2/stage" --param adjudication=behavior-exact-v2.json
uv run --all-packages paddock --data-dir paddock/data run okf-behavior-audit --label stablemate-v1-scored --no-pin-project --param replay_stage="$HOME/.local/share/stablemate/paddock/work/okf-behavior-audit/behavior-dirty-v1/stage" --param cases=stablemate-groom,stablemate-workhorse,stablemate-workflows --param adjudication=stablemate-v1.json
```

Results are under the store's `results/okf-behavior-audit/<label>.zip`. Inspect
`work/okf-behavior-audit/<label>/stage/score.json`; each case also carries the
read-only final `runs/*/behavior-audit.json`, prompts, raw receipts, transcript
exports, doctor findings, preparation counts, and source/book witnesses.
`replay.json` records original steps and zero new model turns for rescores.

## Limits and next comparison

`--no-pin-project` was explicitly required to include the uncommitted API/flow.
Run ledgers label this diagnostic; `toolchain.json` preserves hashes and the
effective requested model config. Concurrent working-tree code is not a release
pin. The shared evaluation task needs the new Ostler behavior API and audit flow.

The production prompt is **packet-only and forbids tools**. Full function bodies,
helper definitions and non-normative book context are sealed for adjudication
but were not delivered to the model. This explains the side-effect and delegated
behavior blind spots and is a limitation of this measured integration, not
evidence that semantic review with full context would fail.

A matched **no-AST semantic arm was not run**. No copied-book repair/re-evaluation
was attempted. Finding-count reduction is not claimed as quality improvement.
Adjudication is an independent read by the implementing agent against predeclared
truth and executable fixture checks, not a blinded second human assessor.
Single samples, shared warmed provider cache, no arm/order randomization, and
three deliberately selected public functions preclude broad statistical claims.

## Verification

`make lint` passes all three root gates: ruff, ty, and basedpyright. The new
evaluator's eight tests plus the existing seed-freshness tests pass: **30 passed**.
The initial evaluator tests were observed failing before their implementation.
The composition test uses the actual task loader, freeze/doctor steps, real
Ostler-generated packets and validated receipts; it rejects changed source and
does not grant detection credit to unresolved decisions.

`uv run --all-packages pytest paddock/tests paddock/data/tests -q` exceeded first
120 seconds, then a 600-second bound, without a final suite result. No claim of
a fully passing Paddock suite is made. `git diff --check` passes. No commits or
pushes were made, no existing app/seed fixture was edited, and no zip is tracked.

## Decoding boundary correction v6, 2026-09-06

### Numbered chain and outcome

1. Why needed? V5 classified `_current_node:raises:1` as partial because its
   uniform "unreadable checkpoints" guarantee includes invalid UTF-8, which the
   existing direct regression observes raising `UnicodeDecodeError`.
2. What decision caused it? Book authoring conflated error classes and extended
   the checkpoint read/parse `OSError` handler to decoding errors it does not catch.
3. How prevented? State error contracts at the actual boundary, distinguishing
   normalized I/O failure from escaping decoder failure, and test both independently.
   Core property: failures grouped by a human description need not share an
   exception class or handling contract. This remains true after a rewrite.
   The correction belongs in the false book claim, not a broader runtime handler.
4. Terminal prevention tested: the new book regression was run before the book
   edit. It failed with `AssertionError: Declare decoding failure separately from
   the two normalization claims`, `assert 2 == 3`; the run reported **1 failed,
   2 passed, 32 deselected**. The other two tests independently observed an actual
   invalid-byte checkpoint raising `UnicodeDecodeError` and an injected read
   `OSError` returning `""` after a successful real checkpoint read. No runtime
   source was changed to obtain green. The prediction also held: all five existing
   non-object boundary variants still return `""`.
5. Book correction: narrow the existing first `raises` claim to read/parse
   `OSError`, add a separate third `raises` claim for decoder propagation, and
   correct the current-node summary, aggregate error handling, deeper-call summary,
   and algorithms. Preserve the second `raises` GROOM-NONOBJECT replacement and
   its observation exactly. Baseline, repaired truth, audit code, and runtime code
   are unchanged. No exception wrapper, fictional JSON observation, waiver, or
   runtime fallback was added.
6. Actual measurement: `stablemate-decoding-v6` reviewed one packet, three claims,
   and four candidates in **one model turn**, no retry, **43.28 seconds** CLI wall
   time. The same `openai/gpt-5.6-terra` default variant was used. V5 `raises:1`
   was **partial**; v6's same ID with narrower text is **supported**. The unchanged
   `raises:2` remains **supported**, and new `raises:3` is **supported**. All four
   candidates are covered; adverse, unmatched adverse, unresolved, contradictions,
   partial claims, and repairs are all empty. No packets were omitted. Empty
   caught/missed lists reflect repaired truth, not a new detection-rate estimate.
7. Evidence identity: v5/v6 frozen source SHA-256 is identical for the full
   `groom/groom/sidecar.py` module
   (`6a1ac478e046321761f93e954cf683d8f5b59ff6e1ed97e64cb19fd325628f7d`),
   its selected witness
   (`04a1808f9eb3dd9677d927d85d5a9632011ba8d20ac767f972ca4e240ac81cc7`),
   and helper `groom/groom/checkpoints.py`
   (`0505eab6babaaa9f6eb0a10f13106b7b91ec65b829fa2ebdcfec8c1b4bf9f806`).
   The v6 witness stayed unchanged during review. Packet digests changed from
   `17f105807857c5a89c96c9e51adb27024dcd86b0e92f948d5854b13570fcc7d8`
   to `ef91919c0bb854de778f1489cd77bcb1164d2109a34ae5f936cf42fe099a140b`
   with the changed book. Afterwards only algorithm list indentation was tidied;
   measured normative claims are unchanged, but the final book is not byte-identical
   to the frozen book. No second model measurement is claimed.
8. Verification: the focused evaluator/checkpoint/sidecar selection passed **57
   tests**, including repaired-state composition and replacement rejection gates.
   Root `make lint` passed ruff, ty, and basedpyright with zero findings. Doctor's
   full report has **195 errors, 1773 warnings**, not a green book gate. On the
   changed method it reports two compound-normative warnings (existing `raises:1`
   and new `raises:3` semicolon wording); the now-explicit exception name also
   triggers a new non-normative summary warning. These are the two additional
   warnings versus v5. Existing inert concept verification, latest-run null-check
   parse error, sibling compound claims, and shared scan-gates grounding remain.
   The slice doctor has one slice-induced dangling link and two compound warnings.

### Explicit limitations

The verification vocabulary has no direct exception observation. `raises:3`
cites the actual decoder regression via `tests:` rather than inventing a
`verify:` call; per-claim executable OKF exception verification remains unavailable.
The direct tests, not the model receipt, demonstrate execution. The semicolon
warning remains visible rather than waived or split into a fictitious extra
behavior solely to satisfy a heuristic.

Terminal/metadata decoding and non-object semantics and the raw `current_id`
projection claims remain untouched and unvalidated by this slice. V5's workflow
signature-default unresolved item is not rerun or cleared. Explicit helper
selection, non-normative coverage, AST-only extraction, receipt overhead, and
relative-store handling limitations above remain. Seven unrelated builder skill
references again warned because the context manifest is deliberately empty.
This is one unpinned working-tree sample, not whole-book completeness or statistical
accuracy. No audit code was changed to force these results.

Usage: 13,386 input, 920 output, 420 reasoning, 7,680 cache-read tokens (backend
categories can overlap). Reported subscription cost is $0; API-equivalent cost
is unknown, not free usage. No second attempt was needed. No commit or push.

### Commands and artifacts

All commands ran from `/mnt/data/workspace/stablemate`; new artifacts and pytest
temporary directories stayed under its `.cache`. The red failure text is retained
in item 4 above. The last focused run after final edits uses `behavior-decoding-final`.

```bash
uv run --all-packages pytest paddock/data/tests/test_behavior_eval.py -q -k 'current_node_book or checkpoint_read_oserror or decoding_failure' --basetemp=/mnt/data/workspace/stablemate/.cache/behavior-decoding-red
uv run --all-packages pytest paddock/data/tests/test_behavior_eval.py groom/tests/test_checkpoints.py groom/tests/test_sidecar.py -q --basetemp=/mnt/data/workspace/stablemate/.cache/behavior-decoding-green
uv run --all-packages paddock --data-dir paddock/data --store /mnt/data/workspace/stablemate/.cache/behavior-paddock run okf-behavior-audit --label stablemate-decoding-v6 --no-pin-project --no-seal --param cases=stablemate-groom --param book_state=repaired --param support_context=true --param max_turns=2
uv run --all-packages ostler doctor --json --no-index > /mnt/data/workspace/stablemate/.cache/behavior-paddock/decoding-v6-doctor.json
make lint
uv run --all-packages pytest paddock/data/tests/test_behavior_eval.py groom/tests/test_checkpoints.py groom/tests/test_sidecar.py -q --basetemp=/mnt/data/workspace/stablemate/.cache/behavior-decoding-final
git diff --check
```

V6 stage: `.cache/behavior-paddock/work/okf-behavior-audit/stablemate-decoding-v6/stage/`.
Inspect `score.json`, `artifacts/cases/trials.json`, the case's `scope.json`, and
`artifacts/cases/stablemate-groom/runs/okf-builder-behavior-stablemate-decoding-v6-stablemate-groom/behavior-audit.json`.
V5 comparisons use the corresponding `stablemate-repaired-v5` stage; historical
results above remain unchanged.

## Signature evidence v7, 2026-09-06

### Numbered root-cause chain

1. Why needed? V5 left the selected workflow's `run_dir=''` default unresolved
   despite the exact authored signature already being present in `packet.book_context`.
2. What decision caused it? The verdict producer admitted only normative obligation
   IDs as coverage evidence, although the documentation contract also admits signatures.
   Documentation evidence is not the same thing as a QA obligation.
3. How prevented? Let source coverage verdicts carry resolvable book-span references
   without minting normative claims. Claim review stays independent and its reciprocal
   candidate-link requirements remain unchanged.
4. Core property: comparing source to its documented contract requires an actual
   reference to that contract, not a duplicated proposition. This remains true after
   a rewrite. The terminal prevention is typed `BookEvidenceRef(node, start_line,
   end_line)` on `CandidateVerdict.book_evidence`, resolved against the supplied,
   digest-bound `BookContext`. Its existing node/path binding supplies the path.
5. Prediction and red test: the actual extraction/graph/packet producers can supply
   signature-only coverage without changing candidate/claim counts, even while claim
   review remains unresolved. Before implementation the producer-packet test failed
   with `candidates.0.book_evidence: Extra inputs are not permitted`; seven rendered
   prompt cases also failed, for **8 failed, 49 deselected**. After implementation,
   the same case records the span, keeps two candidates and one claim, and rejects
   the receipt after a signature-only edit while source and normative claims stay
   unchanged. This tests the terminal prevention rather than duplicating a signature
   as a new obligation.
6. Validation rejects absent/foreign or ambiguous nodes, out-of-context, reversed,
   unseen, blank-only, and duplicate spans. Only `covered` may carry book evidence;
   implementation details carry neither kind of link. Covered requires a supported
   or partial claim link or valid book evidence. Existing claim links remain reciprocal
   and packet-local, and all digest checks remain intact. Persisted receipts without
   the new field deserialize with an empty tuple. No waiver, semantic oracle, runtime
   change, retry extension, or duplicated normative proposition was added.

### Actual single-case measurement

The requested command ran unchanged, with the same captured default configuration
as v5: OpenCode `openai/gpt-5.6-terra`, effort omitted. One packet was assessed in
**one model turn, no retry, 46.35 seconds** CLI wall time. Four candidates and five
claims were selected, with zero packet omissions, exactly as in v5.

Candidate `evidence:174f3174ed9d5357bb05c8858ce67d1828ba2e90b59f8a93888c55131463dab3`
changed from **unresolved** to **covered**, with `claim_ids: []` and this actual
model-produced evidence, accepted by the deterministic validator:

```json
{"node":"docs/features/workflows/concepts/coder-review-shared-review.md#check_feedback","start_line":80,"end_line":80}
```

The referenced line is `- sig: \`check_feedback(logger, run_dir="") -> Feedback\``.
The model's explanation is: "The same-node signature documents the optional run_dir
parameter and its empty-string default." No manual receipt alteration or prompt
change after observing the response was made.

All findings and other judgment changes:

- All five normative claims remain **supported**, including the repaired return shape.
- Both return candidates remain **covered** through reciprocal claim links.
- The decorator candidate `evidence:9802101702b43f65adbfd6b04d8ed90df0dcf3edf8e126ecb280b6255b23b1f6`
  changed from covered to **implementation_detail**, explained as framework registration
  rather than a separate observable contract. Its former polling/consumption claim
  links moved to the found-message return candidate. This is a separate model judgment,
  not signature-fix detection credit.
- Repairs, unresolved IDs, adverse findings, unmatched adverse findings, contradictions,
  and partial claims are all empty. Repaired ground truth has no expected defects;
  empty caught/missed lists are not a detection-rate estimate.
- Slice doctor reports **0 errors, 0 warnings**. The seven unrelated builder-template
  skill-reference warnings from the empty context manifest still occurred. No full-book
  doctor or other service measurement was performed in this round.

### Input identity and usage

V5/v7 `scope.json` full-file hashes and `trials.json` witness hashes match exactly:

| Input | Identical SHA-256 |
| --- | --- |
| Full workflow source `coder/shared/review.py` | `8b413c3466c1bc1b1b3d6c215175281d9c5ac4a0706e53c29994867d12595d42` |
| Selected source witness | `749ba06a2764e35e52fbf93e10eadcf0dd46bb0b437efb738a8fbfa0f4a20b39` |
| Full workflow book | `0a0a446880a47d2c5bbe427e3197c540900b10e36bec88bb5b33119536a3f760` |
| Selected book witness | `8dfdfa64eeb93fbf88aae45ea19295f1152a127f10a1af1203c9681f2bef36d6` |
| Support `coder/shared/schemas/review.py` | `2f54962a87702a4387dbbafa4da66f4c801b3d5c9ca1f119f924403dce6ea2b4` |
| Support `kit/inbox.py` | `2dec891dbb97916d19aded8ad0372d00d96baed13da1f2bc9b224291d0d89c46` |

Even the packet digest is unchanged:
`629264380c34758fbfadde3674cd1352b52bb38e86a963a92fb96abf9f3270f9`.
The run records `unchanged: true` after review. The extractor and audit-flow Python
hashes also match v5; only the receipt models, validator, and audit prompt changed.
The explanatory documentation-versus-QA limitation is added to the returned report,
not the packet, preserving packet identity. Source, book, ground truth, and runtime
were not edited for this measurement.

Usage: 16,796 input, 1,117 output, 516 reasoning, and 7,680 cache-read tokens;
backend categories may overlap. Reported subscription cost is $0, with API-equivalent
cost unknown, not free usage. This is one unpinned working-tree sample, not a release
measurement or a statistical accuracy estimate.

### Residual scope and verification

**Source-only functions and nodes with zero normative claims can still have no
BookContext.** Current extraction attaches context to extracted normative claims,
and packet construction retrieves it from those claims. This change makes already
supplied document evidence representable; it does not repair context retrieval for
all signatures. Functions with no extracted candidates, non-Python sources, explicit
rather than automatic helper selection, and packet-only semantic judgment remain
limitations. Validating a span confirms a resolvable reference, not whether the model
correctly interpreted it, and documented source coverage is **not QA proof**.

Root `make lint` passed ruff, ty, and basedpyright with zero findings. The relevant
Ostler behavior/CLI, full okf-builder, and evaluator selection passed **196 tests**.
An earlier combined run hit its 120-second bound and exposed a test assertion using
Python tuple output where JSON list output was intended; the assertion was corrected
to `model_dump(mode="json")`, and the complete selection then passed in 25.89 seconds.
No production behavior was changed to accommodate that test. `git diff --check` passed.
All new test sandboxes and measurement artifacts are workspace-local. No commit or push.

```bash
uv run --no-sync pytest ostler/tests/test_behavior.py workflows/tests/okf_builder/test_audit_prompt.py -q -k 'signature_span or rendered_audit' --basetemp=/mnt/data/workspace/stablemate/.cache/signature-v7-red
make lint
uv run --no-sync pytest ostler/tests/test_behavior.py ostler/tests/test_behavior_cli.py workflows/tests/okf_builder paddock/data/tests/test_behavior_eval.py -q --basetemp=/mnt/data/workspace/stablemate/.cache/signature-v7-final
uv run --no-sync paddock --data-dir paddock/data --store /mnt/data/workspace/stablemate/.cache/behavior-paddock run okf-behavior-audit --label stablemate-signature-v7 --no-pin-project --no-seal --param cases=stablemate-workflows --param book_state=repaired --param support_context=true --param max_turns=2
git diff --check
```

V7 stage: `.cache/behavior-paddock/work/okf-behavior-audit/stablemate-signature-v7/stage/`.
Inspect `score.json`, `artifacts/cases/toolchain.json`, `artifacts/cases/trials.json`,
the case's `scope.json` and `preparation.json`, and
`artifacts/cases/stablemate-workflows/runs/okf-builder-behavior-stablemate-signature-v7-stablemate-workflows/behavior-audit.json`.
Comparisons use the corresponding `stablemate-repaired-v5` artifacts. Earlier entries
in this evaluation remain historical and unchanged.

## Review-contract receipt binding, 2026-09-06

### Numbered root-cause chain

1. Why needed? A resumed v5 run could retain the unresolved signature judgment
   after the v7 upgrade: its evidence packet digest was identical and its old
   unresolved receipt still passed validation. The upgraded review was never run.
2. What decision caused it? `assess_audit` selected reusable receipts by packet
   digest and structural validity alone, excluding the audit instructions and
   response schema from the reuse decision.
3. How prevented? Record and reuse a judgment only when both its evidence and its
   review contract match. Core property: judgment depends on the evidence and the
   instructions/output contract under which it was produced. That remains true
   in a rewritten reviewer; artificial source edits, skips, and retries do not
   supply the missing observation.
4. Terminal prevention: fingerprint the actual bundled audit prompt bytes and
   canonical UTF-8 JSON from `AuditVerdicts.model_json_schema()` (sorted keys,
   compact separators). Capture the contract and schema before dispatch in the
   assessment work, render with that captured schema, and pass the captured
   contract to recording. The same absolute package-resolved prompt path is used
   for fingerprinting and rendering, rather than a cwd-relative or flavor lookup.
5. Persist `review-contract.json` beside the existing packet artifacts only after
   validation and a current-contract comparison. Its typed policy includes both
   fingerprints and a hash binding it to the exact validated `verdicts.json`
   bytes. Remove the prior sidecar before replacing verdicts, so interrupted
   writes cannot attach a previous policy to a new reply. Missing legacy bindings
   require review; they are not assigned an inferred prompt/schema version.
6. If the prompt or schema changes before rendering or while the turn is in
   flight, recording retains the raw reply but rejects it and the flow parks at
   an operator gate without an automatic retry. The invalid report retains the
   captured policy, not a claim that the reply used the new policy. Explicit
   resumption under a stable contract produces a new validated receipt. This is
   an attribution failure, not a waiver or a verdict-validation relaxation.
7. Shape checks: the fix records the missing observation at the receipt producer
   and checks it at reuse. Workflow-owned typed sidecars and report fields admit
   that provenance without changing Ostler's verdict contract. Both inputs to the
   distinction are present; there is no exception list or assumed historical
   policy. No bypass hatch was added. The existing invalid-verdict retry budget
   and operator gate remain unchanged.

### Regression evidence

Ten new real-flow regression cases use producer-built packets, the actual audit
state machine, prompt rendering, strict verdict validation, receipt persistence,
and checkpoint resume. Only the agent boundary is scripted; no model/provider
was called. Prompt mutations affect a workspace-local temporary copy, never the
installed source. Schema mutations use a test-scoped schema-producer seam.

- Same-contract resume reuses the prior unresolved receipt without another turn.
- Prompt-only and schema-only upgrades each cause exactly one new review while
  packet and preparation digests remain unchanged.
- Canonical schema key reordering alone does not invalidate a receipt.
- An absent legacy binding and replacement of a still-valid receipt each require
  a new review. The sidecar must bind the actual verdict bytes, not just exist.
- Four in-flight cases cross prompt/schema changes with before/after rendering:
  each preserves one raw reply, parks after one call, records no accepted policy
  sidecar, retains captured provenance, and accepts a fresh reply after an
  explicit stable-contract restart of the state machine.

Before implementation, the four initial resume cases reported **4 failed,
12 deselected**: the same-contract case lacked the required sidecar, and prompt,
schema, and legacy cases failed with `assert 1 == 2` agent calls. The four
in-flight cases reported **4 failed, 16 deselected**, each with
`DID NOT RAISE <class 'InterruptedError'>`: the old flow completed instead of
parking. These failures directly exposed missing binding and attribution checks.
The added replacement-receipt test initially tried to mutate a frozen Pydantic
value; the fixture was corrected to copy it, without changing production code.

Final verification: **22 focused audit tests passed**, **117 full okf-builder
tests passed**, and root `make lint` passed ruff, ty, and basedpyright with zero
findings. The prediction holds independently of the original signature case:
schema-only changes invalidate unchanged evidence, whereas schema key ordering
does not. Existing source/claim/context invalidation and strict invalid-verdict
tests remain green.

```bash
uv run --all-packages pytest workflows/tests/okf_builder/test_audit.py -q -k resume_binds --basetemp=/mnt/data/workspace/stablemate/.cache/audit-policy-red
uv run --all-packages pytest workflows/tests/okf_builder/test_audit.py -q -k in_flight_contract --basetemp=/mnt/data/workspace/stablemate/.cache/audit-policy-flight-red
make lint
uv run --all-packages pytest workflows/tests/okf_builder/test_audit.py -q --basetemp=/mnt/data/workspace/stablemate/.cache/audit-policy-focused-final
uv run --all-packages pytest workflows/tests/okf_builder -q --basetemp=/mnt/data/workspace/stablemate/.cache/audit-policy-full-final
git diff --check
```

### Provenance and limits

New workflow reports explicitly use `schema_version: 2`, with the captured
`review_contract` and aggregate `policy_digest`; the sidecar contract format is
version 1. Unversioned historical workflow reports deserialize as version 1 with
no observed contract and no policy digest. Neither version denotes a model
version, a semantic accuracy claim, or a guessed v5/v7 policy. Ostler packet and
verdict/report versions are untouched.

Packet digests and `behavior-audit/<packet-digest>/` artifact paths, including
`raw-*.json`, are unchanged, preserving deterministic preparation scoring and
existing artifact globs. `validate_verdicts` is unchanged. No runtime source,
feature book, measured receipt, or historical evaluation result was edited.
This patch changes only the workflow audit implementation/tests and appends this
evaluation. No model run, commit, push, or live-run operation was performed.

The reuse policy binds bundled audit instructions and response schema, not
model/provider configuration, effective effort, backend versions, ambient agent
instructions, or validator implementation changes that leave the schema intact.
Existing run/toolchain records remain the provenance source for configuration;
this change neither captures those settings in the policy nor claims that their
changes invalidate receipts. The tests establish cache correctness at the stated
contract boundary, not improved semantic accuracy or a new v5/v7 measurement.

## Captured observations repair, 2026-09-06

### Numbered root-cause chain (before editing the prompt)

1. Why needed? The restarted workhorse builder log, lines 9-30, refuses checks
   for `assert_file_contains` and `assert_json_file` and records partial items as
   done. The restarted groom log, line 10, similarly says `SKIP` cannot be
   observed. These are `.agents/runs/okf-builder-stablemate-{workhorse,groom}/restart-goal.log`.
2. What decision caused it? The repair prompt treats a closed assertion vocabulary
   as a closed set of ways to acquire evidence, and even contradicts its rendered
   registry by declaring registered `persists` and `emitted` checks unavailable.
3. How could it have been prevented? Separate documented comparison arguments from
   scenario-owned observations. Show a real helper invocation capturing only its
   expected `AssertionError`, with type and `str(exc)` diagnostic, then call the
   existing `json_path` verifier outside that handler. No exception leaves an empty
   exception mapping; unexpected exception types and verifier errors propagate.
4. Why is that prevention needed? An assertion compares evidence; naming the
   assertion cannot acquire evidence, and pre-filling its expected answer cannot
   distinguish working behavior from a no-op. This is a core property even after
   rewriting the harness. The terminal change is the repair prompt's concrete
   capture/comparison example, tested through real `Qa` ledger records and the
   unchanged helper, including a no-op mutation that must record red.
5. Legal in the target? `json_path` admits `path` plus `equals`, `matches`, or
   `absent`; `Qa.verify(check, observed, *, covers, **args)` accepts the observed
   mapping separately. The book's `verify:` contains comparison arguments only;
   adjacent scenario prose specifies acquisition. No verifier name, argument,
   waiver, fallback, or runtime behavior is added. The source of the misleading
   instruction is repaired rather than routing the refusal elsewhere.
6. Prediction: the same capture works for both a missing file and wrong file
   content, including the actual diagnostic, without changing the helper. It also
   explains how to test `assert_json_file` rejection using mismatched JSON input;
   a dedicated exception check is unnecessary. Only the exercised cases will be
   claimed as verified.

This corrects the earlier **verification unavailable** interpretation in v6:
there is no first-class exception check, but generic captured observations can
express exception behavior. An observation is a scenario-owned value acquired
from execution, never an invented product output or an expected answer copied
into evidence. No live book, run, historical receipt, or benchmark metric is
changed by this correction. Live improvement remains unmeasured.

### Executable evidence and limits

The two prompt regressions ran red before the prompt edit: **2 failed, 23
deselected**. Failures were the stale `they are not in the list` assertion and
`AssertionError: Repair needs an executable evidence-acquisition example`.
The executable cross-package test extracts the Python body from the real rendered
repair prompt, parses its markdown declaration with `checks.parse_check`, executes
that body against unchanged `workhorse.testing.assert_file_contains`, and uses
`load_harness_module("ostler_qa")` with the real `Qa` and file-backed `_Recorder`.
It does not duplicate the scenario into a test-only implementation.

Six cases record the following evidence (counts are assertions/failures):

| Case | Counts | Actual evidence |
| --- | --- | --- |
| Missing file | 2/0 | `AssertionError`; `Expected file 'sample.txt' to exist in sandbox, but it does not` |
| Wrong content | 2/0 | `AssertionError`; `Expected 'sample.txt' to contain 'required text'\nActual content:\ndifferent content\n` |
| No-op mutation | 1/1 | `passed: false`, `actual: {"present": false}`, `expected: {"path": "exception.type"}` |
| Unexpected product `TypeError` | 0/0 | Error propagates; empty ledger |
| Verifier `AssertionError` | 0/0 | Error propagates; empty ledger |
| Verifier `ValueError` | 0/0 | Error propagates; empty ledger |

The ledger schema is unchanged: `type`, `id`, `label`, `passed`, `actual`,
`expected`, `covers`, `check`, `check_args`. The type assertion's `check` is
`json_path`, and `check_args` is exactly
`{"path": "exception.type", "equals": "AssertionError"}`. The diagnostic is
checked and recorded separately at `exception.message`; its actual value comes
from `str(exc)`, not a synthesized result. No audit output schema, score metric,
historical benchmark, or runtime helper changed. The prediction passes for wrong
content as well as absence; JSON-helper and stdout/stderr generalizations are
explained, not claimed as newly executed scenarios.

Final affected selection: **392 passed in 39.82s** (329 workflow/prompt/QA-core,
63 Paddock evaluator/seed-freshness). Root `make lint` passes ruff, ty, and
basedpyright with zero findings; `git diff --check` passes. A broader selection
including `test_prompts_exist.py` reported **418 passed, 1 failed**: the existing
concurrent audit flow at `audit/flow.py:54` uses `str(prompt_path)`, while that
guard requires a literal string. That unrelated flow and guard were not edited;
this is not a claim of a fully green workspace test suite.

Reproduce the affected selection from the root:

```bash
uv run --all-packages pytest workflows/tests/okf_builder workflows/tests/test_prompt_variables.py workflows/tests/test_prompt_output_shape.py ostler/tests/test_checks.py ostler/tests/test_qa_verifiers.py ostler/tests/test_qa_harness.py paddock/data/tests/test_behavior_eval.py paddock/data/tests/test_seed_freshness.py -q --basetemp=/mnt/data/workspace/stablemate/.cache/captured-observation-evidence -o tmp_path_retention_policy=all --junitxml=/mnt/data/workspace/stablemate/.cache/captured-observation-tests.xml
make lint
```

JUnit evidence: `.cache/captured-observation-tests.xml`. The retained real ledgers
are `.cache/captured-observation-evidence/test_repair_capture_example_reN/records.jsonl`,
where N=0 through 5 follows the table order. In particular N=2 is the executed
no-op mutant's red check, not a claimed sensitivity result.

Next verification command for the remaining, separately owned prompt-path gate:
`uv run --all-packages pytest workflows/tests/test_prompts_exist.py -q`.
After any parent-authorized at-boundary reload, inspect new repair prompts and
logs for an actual repaired obligation before claiming live improvement. No
external private filesystem, live book edit, model call, commit, push, restart,
or reload was performed for this change. No new waiver or runtime hatch remains.

## Packet sizing before and after context trimming, 2026-09-06

Measured with `ostler audit ostler --json --no-index` on the `ostler` package from a clean
checkout of `d0fca5d6` (before) and the same tree with plan step 8 applied (after). Sizes are
characters of packet JSON, summed across packets.

| Run | Packets | Candidates | Selected claims | Total chars | Limitations | Claims | Book context | Source context |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before, tier 1 | 336 | 2,261 | 9,203 | 17,017,663 | 8,900,000 | 4,260,000 | 3,560,000 | 70,000 |
| before, tier all | crashed: `oversized packet for ostler/ostler/doctor.py` | | | | | | | |
| after, tier 1 | 20 | 2,265 | 55 | 517,208 | 288,000 | 25,000 | 47,500 | 67,000 |
| after, tier all | 25 | 3,903 | 55 | 763,360 | | | | |

After trimming, tier 1 also reports 1,638 deferred candidates, 9,148 out-of-scope claims and
83 undocumented files. Three changes account for the reduction:

1. **Out-of-scope claims.** Before, every claim whose citations resolved to no selected file
   was treated as ungrounded and attached to every packet — 318 of the 336 packets carried
   the whole book. With `root` passed, a claim whose citations all name existing files
   outside the selection is counted and skipped instead. A citation to a file that does not
   exist stays ungrounded, since that is a defect a reviewer should see.
2. **Per-file limitations.** A `path::symbol` extraction note now rides only the packet for
   that file; the generic notes still ride every packet.
3. **Windowed book context.** Each node's section is cut to forty lines either side of the
   packet's claims, which is what let the `doctor.py` pair fit under `max_chars`.

Same-file binding excerpts, the plan's other candidate for a cap, measured about 2,500
characters across all packets before trimming and were left uncapped. The remaining bulk
per packet is the limitations list, dominated in a whole-repository audit by the
duplicate-heading skips of other services' books; the okf-builder scopes those to the
service it audits, so its packets do not carry them.
