# Resumed builder measurements

The original three Stablemate builders resumed their existing checkpoints, not
new builds. Two private-repository builders also resumed after explicit permission
to operate outside the Stablemate workspace. Private evidence stays in that
repository and is not copied into this public tree.

## Stablemate baseline and first observation

| Book | Before errors | After errors | Before warnings | After warnings |
| --- | ---: | ---: | ---: | ---: |
| groom | 16 | 16 | 1338 | 1329 |
| workhorse | 48 | 48 | 118 | 111 |
| workflows | 131 | 132 | 316 | 316 |
| Whole tree, including other books | 195 | 196 | 1773 | 1757 |

Snapshots are `.cache/behavior-paddock/restart-before-doctor.json` and
`.cache/behavior-paddock/restart-after-doctor.json`. The after snapshot was taken
while turns were editing books, not at a clean workflow checkpoint. The additional
error is `missing-required-bullet` for `kind:` on the `agent-turn-contract` step
in `docs/features/workflows/flows/coder-main.md`. Do not classify this as a durable
regression until the producing turn and checkpoint have finished.

All three control sockets responded after resume. Their logs subsequently
confirmed at-boundary reloads into `record_item`, replacing the workflow and
Ostler packages without another process restart. These confirmations establish
that the updated code was loaded, not that its semantic audit has run. The runs
are still draining the existing investigation and structural-repair queues.

## Observation-authoring defect

1. Why needed? The resumed repair turns declined exception and file-content
   obligations, claiming the closed vocabulary had no suitable check. One such
   partial response was nevertheless recorded as a completed worklist item.
2. What decision caused it? Authoring guidance conflated evidence acquisition with
   the comparison vocabulary and incorrectly excluded two registered checks.
3. Prevention: show how the scenario invokes the real helper, captures only the
   expected exception and its actual message, then verifies that observation
   outside the capture handler using the existing `json_path` check.
4. Core property: a predicate cannot establish behavior without an observation
   produced by exercising that behavior. Evidence acquisition and comparison are
   distinct even when no domain-specific check name exists.
5. Prediction executed: the real helper's missing-file and wrong-content outcomes
   produce two passing recorded assertions. A no-op fails, an unexpected product
   exception escapes, and verifier failures are not swallowed. The affected
   selection passed 392 tests; this is executable guidance evidence, not yet a
   measured improvement in the original live runs.

## Prompt-discovery regression

1. Why needed? The static packaging gate failed on the audit's computed prompt
   argument after review-contract binding was added.
2. What decision caused it? Dispatch replaced a known packaged path with a
   computed expression that the package's prompt discovery cannot inspect.
3. Prevention: restore the literal relative path at dispatch while retaining
   fingerprinting of the same file. The real-flow tests render and hash the same
   fixture, including prompt changes before and after dispatch.
4. Core property: a required packaged resource must be enumerable independently
   of the runtime branch that eventually uses it. No exemption or weaker gate
   was added.
5. Red: prompt discovery had 1 failure and 89 passes. Green: discovery plus audit
   contract tests passed 112 tests. Root `make lint` and `git diff --check` passed.

## Next observation

Compare checkpoint-stable findings and actual repaired claim/check contents,
especially the initial partial refusals. Worklist completion counts are not
coverage or correctness scores. The semantic audit has not yet produced a
whole-book result for any resumed run. Initial Python-only extraction and explicit
helper selection remain limitations, particularly for non-Python services; those
must be addressed rather than treated as waived coverage.

## Go evidence and later observation

Go evidence now uses the existing tree-sitter parser and supplies enclosing
function/method context. It does not execute source or infer semantic truth.
The controlled Go experiment detected four of four curated defects with zero
adverse findings on the correct control. Three overlapping adverse IDs on mutant
cases remain in the raw score, not hidden as extra detections. Five backend
attempts were required. See `../okf-behavior-go/GO-EVALUATION.md` for the oracle,
receipts, and limitations. This is not a measurement of the live API books.

All five original builder control sockets were verified live before requesting
at-boundary reloads for Go support. Requests were acknowledged without cutting
active turns; the acknowledgement is not itself proof of completed reload.

The subsequent snapshot `.cache/behavior-paddock/restart-go-doctor.json` reports:

| Book | Errors | Warnings |
| --- | ---: | ---: |
| groom | 16 | 1265 |
| workhorse | 66 | 82 |
| workflows | 123 | 311 |
| Whole tree, including other books | 205 | 1659 |

Against the pre-restart baseline that is ten more errors and 114 fewer warnings.
This is mixed progress during active edits, not a clean checkpoint or evidence of
semantic improvement. The growing Workhorse error set includes dictionary values
passed to scalar `json_path.equals`, nonliteral arguments, and presence-only
checks rejected as weak.

### Newly observed causes

1. Why is earlier validation needed? Repair turns add verification declarations
   that cannot be parsed or discriminate no behavior, while reporting documented
   items. What decision permits accumulation? Generated declarations reach the
   book/worklist before the later checkpoint rejects them. The declaration is a
   typed executable contract, not arbitrary prose; acquisition examples alone
   cannot enforce its argument grammar. Next prevention to test: validate generated
   calls against the actual registry and counterexample rules before accepting
   each repair, without re-reading the entire repository. The existing gates
   remain intact; no unsupported values were made legal to hide the errors.
2. Why did the combined Go gate fail before running tests? Both new suites used
   the basename `test_behavior_go.py`. Pytest's import mode assigns those files
   the same module identity. The filename producer must provide unique identities
   in a shared test namespace. Renamed the benchmark module to
   `paddock/data/tests/test_behavior_go_eval.py`, rather than clear caches or
   exclude a suite. The identical combined selection then passed 177 tests,
   including actual Go execution. Root lint also passed after the earlier
   timeout and transient unrelated finding; no unrelated source was modified.

Nodes without normative claims, automatic helper retrieval, and languages beyond
Python/Go remain unaddressed. The main builders are still in structural repair
or investigation, so none of these snapshots certifies whole-book completeness.
