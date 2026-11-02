# Ostler surface completeness

Status: implementation handoff. The user requested decomposition followed by dispatch to
Kimi through OpenCode when ready to implement; this authorizes that handoff without a
second approval round. No claim is made that the implementation is already complete.

Prior exposure: the investigation preceding this design read the current book, checker,
compiler and harness. Sections 1–4 re-derive responsibilities from the verification
problem; inherited implementation choices are claims below, not constraints by default.
Each part and concept passes the counterfactual naming test: it would still be needed in
a different verification system.

## 1. Problem

An author needs to know whether the promised behavior of a surface can actually be
verified. Today a successful health check can coexist with untested promises, unavailable
observations, or an experiment that never ran. The operator cannot reliably distinguish
an invalid promise from missing tooling or missing execution inputs.

Done means an operator can select a surface and see every required behavioral obligation
accounted for exactly once, with evidence for what is supported, what was executed, what
detects a defect, and who owns each gap. A surface is complete only relative to an explicit
contract and evidence snapshot: zero unaccounted obligations, zero outstanding required
capabilities, and zero required checks lacking applicable execution and sensitivity
evidence. Inventory omissions remain visible as a separate dimension (A1).

The first delivery makes one real CLI surface assessable end to end. Subsequent deliveries
close a demonstrated sensitivity gap and a journey spanning two HTTP services. Broader
driver support is admitted only for an observed obligation that needs it (A2).

Out of scope: proving arbitrary prose correct, proving the inventory exhaustive without
review, automatically repairing all existing book debt, implementing every possible
driver, blanket severity promotion, rewriting the whole repository, remote publication,
or treating a declaration of non-exercise as proof. Existing baseline counts may decrease
only for explained repairs; preserving the exact count after a deliberate repair is not
a goal. Human-reviewed claims stay explicitly reviewed, never machine-proven.

## 1b. Claims inherited from the investigation

1. Prior assistant: “a per-surface capability report” should be the first improvement.
2. Prior assistant: “declared → compilable → arrangeable → executable → observable →
   sensitivity assessed” should describe completeness.
3. Prior assistant: missing compiler support and missing runtime observation need different fixes.
4. Prior assistant: journeys crossing services need multiple targets in one scenario.
5. Prior assistant: a witness-generation failure needs a harness improvement, not a weaker claim.
6. Current catalog, as read during investigation: mechanical repairs are errors; authoring
   judgments are warnings.
7. Current behavior, as read during investigation: normal health checking and compilation
   report different subsets of problems.

## 2. Parts and concepts

### Level 1: responsibilities

| Part | Owns | Never knows | Hands to |
| --- | --- | --- | --- |
| Contract accounting | The set of promises owed for a selected surface | Execution machinery | Obligations and exclusions to assessment |
| Verification assessment | Whether each promise has sufficient evidence | Transport implementation | Assessment to operator reporting; missing capability to execution |
| Experiment execution | Attempts to exercise the promised behavior | Gate policy | Observations and refusals to assessment |
| Operator reporting | The actionable verdict for the selected scope | Browser or transport mechanics | Scoped findings and completion verdict to the operator |

Flow: accounting supplies a fixed obligation set. Assessment first checks whether an
experiment can be constructed; execution supplies evidence when explicitly requested.
Assessment evaluates that evidence and reporting explains the verdict. A later run uses
a new snapshot rather than silently treating an old success as current.

Plain-language split: list what is promised, establish how to test it, perform the test,
and tell the author precisely what remains. These responsibilities fit different code
bases; none depends on a particular existing module layout.

### Level 2: contract accounting

| Concept | Owns | Never knows |
| --- | --- | --- |
| Surface scope | Membership of the assessment | Experiment implementation |
| Obligation | Identity of one required observation | Report formatting |
| Exclusion | An explicit non-required obligation with its reason | Passing evidence |
| Contract snapshot | Identity of the assessed contract | Runtime session handles |

### Level 2: verification assessment

| Concept | Owns | Never knows |
| --- | --- | --- |
| Capability assessment | Support evidence for one obligation | Concrete driver operations |
| Evidence assessment | Applicability of supplied observations | How observations were collected |
| Sensitivity trial | Whether a specified defect is detected | Operator gate settings |
| Gap | One unmet requirement with its responsible party | Report rendering |

### Level 2: experiment execution

| Concept | Owns | Never knows |
| --- | --- | --- |
| Experiment | Ordered actions needed for one observation | Gate policy |
| Target binding | Identity of an action's execution destination | Verdict severity |
| Observation role | The evidence acquisition contract | Which implementation is selected |
| Process observation | Evidence from a command invocation | HTTP client internals |
| HTTP observation | Evidence from a service request | Process launch internals |
| Experiment assembly | Selection of observation implementations | Rendering details |
| Witness | A valid accepted input for a sensitivity trial | Completion aggregation |

Observation variants are peers implementing the role, never subclasses of each other.
Existing browser/mobile observations remain existing variants; this design introduces no
replacement hierarchy for them (A6).

### Level 2: operator reporting

| Concept | Owns | Never knows |
| --- | --- | --- |
| Completion verdict | The all-required-obligations decision | Concrete observation implementations |
| Finding policy | Whether an assessed condition blocks the selected gate | Tool invocation details |
| Report view | Human or machine presentation of the same result | Execution ordering |

Obligation identity, scope identity, snapshot identity and observation evidence are shared
immutable values. Each has one producing owner above; consumers receive values rather
than separately reconstructing them.

## 3. Invariants

| Invariant | Sole enforcing owner | Supporting concepts |
| --- | --- | --- |
| Every selected required obligation has exactly one assessment row | Completion verdict | Surface scope, Obligation |
| Unknown, unavailable, excluded and failed are never counted as passed | Completion verdict | Gap, Exclusion |
| Capability support never implies that execution took place | Evidence assessment | Capability assessment |
| Evidence is current only for its recorded contract and relevant input identity | Evidence assessment | Contract snapshot |
| A sensitivity success names both an accepted witness and a rejected relevant defect | Sensitivity trial | Witness |
| Each action reaches its declared target; captures retain identity across actions | Experiment | Target binding |
| Every gap names book, tooling, or environment ownership, with a reason | Gap | Capability assessment |
| Existing doctor results retain their meaning unless a slice explicitly repairs a rule | Finding policy | Report view |
| JSON and human output describe the same obligation set | Report view | Completion verdict |
| Read-only assessment performs no product action and adds no required network dependency | Experiment assembly | Capability assessment |

Required evidence dimensions are independent facts, not an ordered status enum. A later
dimension cannot be used to fabricate an earlier one. Assessment with no execution
evidence says not-run even when every capability is present.

## 4. Forces and patterns

F1: contract edits invalidate evidence independently of tool availability. Use immutable
snapshot identities and applicability checks, not a mutable progress counter.

F2: commands and network requests acquire evidence differently. At the execution boundary
use a small observation role with peer implementations, selected by experiment assembly.
Reuse an existing equivalent boundary at mapping time; do not add a parallel framework.

F3: many obligations need an auditable aggregate. Use plain typed assessment rows and a
pure completeness predicate. Identity-based joins prevent denominator loss.

F4: a healthy declared contract can exceed tooling support. Keep cause/owner separate from
blocking policy. Use data tables for known gap classifications, refusing an unclassified
gap rather than silently passing it.

F5: observation and perturbation can be expensive or side-effectful. Separate read-only
capability assessment from explicitly requested execution. Consume existing evidence where
its identity is sufficient; never launch experiments merely to display health.

F6: a user journey can cross service boundaries while preserving one subject. Use an
ordered experiment with per-action target bindings and explicit capture flow.

F7: operators already automate the current gate. Keep that interface compatible; expose a
separate explicit completeness gate before changing legacy severity behavior.

Between parts: direct typed calls and returned values; no event bus, plugin system or new
database. Within parts: the observation role addresses F2; all other concepts are plain
values or functions. A registry is justified only where the existing assembly already
selects named drivers. No cache is introduced without a measured cost.

Claim decisions: C1 re-derived by F3/F7; C2 revised to independent dimensions by F1/F5;
C3 re-derived by F2/F4; C4 re-derived by F6 for genuine cross-service journeys; C5
re-derived by F4 and the sensitivity invariant; C6 rejected as a complete severity rule
because repair difficulty does not determine whether verification is possible; C7 retained
as separate execution responsibilities but rejected as a reason to omit gaps from the
surface assessment.

SOLID review: each concept owns one responsibility; observation variants add at the
assembly boundary; each variant satisfies the role rather than extending a peer; the
role exposes only observation acquisition; assessment depends on returned evidence, not
driver types. Existing broader interfaces are preserved where a new abstraction would
add no necessary variation (A6).

Open lookups for section 5: identify the authoritative obligation set; identify supported
report/API entry points; inspect evidence identity and sensitivity failures; confirm a
real multi-target refusal; measure a small repeatable baseline and identify existing
compatibility checks. Missing measurements become explicit pre-implementation gates.

## 5. Mapping onto the existing system

Revision log:

- R1: section 3 evidence applicability requires claim-content identity. The existing
  packet digest hashes obligation IDs, which can stay fixed when a claim changes.
- R2: section 2 retains existing driver boundaries rather than introducing a second
  observation framework; dispatch already supplies several peer implementations.
- R3: section 1 limits capability implementation to demonstrated cases. The supported
  driver vocabulary already includes gRPC; an older book description omitted it.

### Parts

| Part | Verdict | Mapping |
| --- | --- | --- |
| Contract accounting | Reshape | `ostler/ostler/qa/context.py:339` already supports `whole_book` and `books`; reuse it to select a surface without pretending a story diff is the whole surface. |
| Verification assessment | Reshape | `qa/compile.py:511`, `qa/sensitivity.py:955` and `qa/report.py:51` hold complementary evidence; join by obligation identity without replacing their semantics. |
| Experiment execution | Reshape | `qa/compile_journey.py:120` refuses multiple HTTP origins; `qa/harness/ostler_qa.py:252` binds a scenario to a target. Extend these together in slice 5. |
| Operator reporting | New | Add `ostler/ostler/qa/assessment.py` with thin wiring in `cli.py` and `api.py`; preserve `doctor`'s ordinary contract. |

### Concepts

Paths below are relative to `ostler/ostler/`.

| Concept | Verdict | Location and boundary |
| --- | --- | --- |
| Surface scope | Exists | `qa/context.py:339`, `whole_book=True, books=[...]`; selection is separate from driver execution. |
| Obligation | Exists | `qa/obligation.py`, consumed by `qa/packet.py:21`; reuse IDs and requiredness. |
| Exclusion | Reshape | `qa/dispatch.py:55` determines live-evidence obligations; assessment must report exclusions with reasons, not silently shrink its input set. |
| Contract snapshot | Reshape | `qa/packet.py:46` digest hashes only owed IDs; keep that existing plan-binding digest and add an explicitly versioned assessment content fingerprint. |
| Capability assessment | New | `qa/assessment.py`; consume actual compile results, not an independent support table that can drift. |
| Evidence assessment | New | `qa/assessment.py` joins existing run evidence through `qa/report.py:51`; old evidence without sufficient identity remains unknown. |
| Sensitivity trial | Exists | `qa/sensitivity.py:147` already records witness, flipped and survived mutations; a sensitive result is limited to those mutations. |
| Gap | Reshape | `qa/plan_source.py` and `qa/compile.py:111`; retain existing codes, add assessment owner classification with exhaustive tests. |
| Experiment | Reshape | `qa/compile_journey.py:175` currently refuses different target/service pairs; retain action order while widening HTTP destinations. |
| Target binding | Reshape | `qa/harness/ostler_qa.py:200,252,323,413`; keep existing single-target callers valid while binding individual HTTP actions in a journey. |
| Observation role | Exists | Runtime observation contracts plus `qa/compile_support.py:46`; reuse these boundaries (R2). |
| Process observation | Exists | `qa/compile_cli.py` and the harness command runtime; keep process invocation behind its current boundary. |
| HTTP observation | Reshape | `qa/compile_http.py` plus harness HTTP runtime; choose the declared destination per request, without mutable shared base-URL switching. |
| Experiment assembly | Exists | `qa/dispatch.py:81` and compiler backends; selection already happens apart from assessment. |
| Witness | Reshape | `qa/sensitivity.py:267,290,450`; extend generation only against observed unsupported expressions. |
| Completion verdict | New | `qa/assessment.py`; a pure aggregation of fixed required IDs and assessed evidence. |
| Finding policy | New | Assessment-local blocking rule, leaving `doctor.py:49` and `cli.py:1385` compatible. |
| Report view | New | Human and JSON renderers for assessment; use existing `QaOutcome` facade conventions at `api.py:379`. |

Mismatch decisions:

1. `qa/packet.py:46` identifies the set, not the content. The code is adequate for its
   existing purpose; the design would be wrong to reuse it as freshness proof. Add a
   separate fingerprint over canonical obligations, checks, arrangements, target bindings,
   applicable source identities and assessment schema/tool version. No credentials enter it.
2. `census.py:17` records that `gap_findings` has no product caller. Calling ordinary
   doctor is therefore insufficient for this new verdict. Consume `compile_plan_gaps`
   directly; do not turn doctor into an executor or call its gap converter speculatively.
3. `qa/compile_journey.py:129,200` rejects real cross-target journeys. The design is right
   for a two-server journey: splitting it can lose capture/state continuity. Mixed-driver
   journeys remain explicit gaps outside slice 5, rather than being incorrectly marked supported.
4. `doctor.py:2537` treats an occurrence of `inactive` as unavailable. The current book's
   dashboard mode buttons use it for unselected state. Correct this heuristic in slice 3
   before relying on stricter completeness reporting for those controls.

Existing responsibilities not newly modeled: schema validation, graph integrity,
source coverage, frozen planning records, known-defect declarations and index caching
are necessary neighboring concepts, not waste. Retain their implementations and expose
relevant findings without absorbing them into a second checker. External planning roots
must be described as context, not mistaken for selected book membership.

Claims against the mapping: C1 is new; C2 exists only as separate partial reports and is
revised to dimensions; C3 already exists in `compile_support.py:75`; C4 is currently refused
and becomes supported for HTTP in slice 5; C5 already has the truthful `unwitnessed` state
and needs better witnesses; C6 remains legacy doctor behavior, while the new gate follows
consequence and evidence; C7 remains separate internal responsibilities with one joined
assessment. No repository-wide architecture change is required (A6).

### Public contract chosen for implementation

Add `ostler qa assess --book <repo-relative-services-directory> [--spec <existing-spec-directory>]
--json` and an equivalent `Ostler` facade method. `--json` is optional. Reuse existing
argument conventions where they already name these inputs; document any spelling adjustment
in this note. Scope is explicit; an invalid or empty scope is not vacuously complete.

This command is read-only: it builds a whole-book context for the selected directory,
checks compilation capability, performs local synthetic sensitivity trials, and optionally
reads existing run evidence. It never starts the product or creates a run. Exit 0 means
complete for the declared contract and applicable evidence; 1 means incomplete; 2 means
invalid invocation or unreadable required input. Ordinary `doctor` exit behavior is unchanged.

JSON includes `schema_version`, scope, contract fingerprint, input identities, required
and excluded counts, `capabilities_complete`, `evidence_complete`, `complete`, per-obligation
dimensions and gaps. A gap carries code, owner (`book`, `tooling`, `environment`), path,
line, obligation ID and remedy. No run means execution `not-run`, not capability failure.
Unknown gap ownership is itself an assessment failure, never a default success.

Minimum verdict matrix:

| Condition | Capability | Evidence | Overall |
| --- | --- | --- | --- |
| All required checks supported; no run supplied | complete | not-run | incomplete |
| Required compiler/driver capability absent | incomplete | whatever was actually observed | incomplete |
| Required runtime input unavailable | assessed separately | unavailable | incomplete |
| Matching successful run; sensitivity unknown | complete if compilation supports it | incomplete | incomplete |
| Matching run and relevant sensitivity proof | complete | complete | complete |
| Claim changes with unchanged obligation ID | reassess | stale | incomplete |
| Empty/missing scope | invalid | invalid | invocation refusal |
| Explicitly excluded obligation | visible, not required | no success claimed | does not satisfy another obligation |

## 5b. What must not move

Measurements taken during this planning task. Large-book counts below are the earlier
investigation snapshot, not a frozen fixture: external artifacts and concurrent edits can
change them. Reproduce small inputs for exact regressions; compare a fresh book snapshot
before and after each code slice (A3).

| Receiver | Gets today | Enforced by | Before | Holds when |
| --- | --- | --- | --- | --- |
| Existing doctor callers, empty book | Success without product execution | CLI baseline probe | exit 0; 0 errors; 0 warnings; 1.042 s | same exit/counts; no execution; at most 2 s on comparable host |
| Existing doctor callers, missing-type page | A blocking structural finding | CLI baseline probe | exit 1; 1 `okf-missing-type`; 0 warnings; 1.025 s | same exit/code/count; at most 2 s on comparable host |
| Existing doctor and sensitivity consumers | Current tested behavior | `test_doctor.py`, `test_qa_sensitivity.py` | 168 passed; 5 environment/root-discovery failures; 9.84 s | isolate the five failures, then zero unexplained regressions; do not accept 168 alone as green |
| Authors of multi-target journeys | Explicit refusal rather than partial success | two selected tests in `test_qa_compile.py` | 2 passed, 405 deselected in 0.19 s | until slice 5, refusal; after slice 5, HTTP case executes both targets and retains capture; mixed-driver case still refuses |
| Book maintainers | Every existing defect remains visible unless repaired | previous JSON report | 1,500 errors; 1,192 warnings; 1,322/1,148 under services | all count changes attributed to specific rule/content changes; no disappearance due to accidental scope narrowing |
| Operators running read-only assessment | No product actions from health reporting | invariant in section 3; new sentinel test required | 0 actions in the empty-book CLI probe | 0 product actions and 0 required external requests |

No measured memory budget exists. Assessment overhead and full-book runtime are not yet
measured; slice 1 records them before choosing any performance claim or optimization (A4).
The planning-time root `make lint` attempt passed ruff and ty but basedpyright reported
4,544 errors and 52 warnings, including missing third-party imports and unknown local
imports. This used `UV_NO_SYNC=1` and the existing environment; it is not a valid clean
workspace installation baseline. First run `uv sync --all-packages` and rerun the exact
gate with the intended interpreter before attributing any finding to source. Do not
suppress findings or broaden configuration to make this count disappear. This document
is intentionally not committed while that required gate remains unresolved.
The legacy baseline probe is reproducible with a temporary repository containing
`docs/services/`, a separate temporary `STABLEMATE_ARTIFACTS_DIR`, and then a single page
`broken.md` with frontmatter `title: Broken` and no `type`. Run root `.venv/bin/ostler -C
<repo> doctor --no-index --json`. Do not use real external planning artifacts for that probe.

## 6. Slices

Each slice is a complete operator-visible path. Every slice reruns the section 5b baseline
on the same isolated inputs, recording before/after values and explanations. Also run
`make lint` at the repository root and affected tests. A failed receiver bound fails the
slice. Extend the OKF book in the same commit via scaffold/fmt/doctor and stamp touched
citations as the repository requires. Use explicit staging, local conventional commits,
the existing branch, no invented Story trailer, and no PR or push.

### Slice 1 — assess one real CLI surface without claiming it ran

Parts: all four. Concepts: Surface scope, Obligation, Capability assessment, Sensitivity
trial, Gap, Completion verdict, Report view; reuse execution's existing compiler.

Deliver `qa assess` and the facade for a small CLI book built with the existing scaffolder.
Use one command with a real invocation and observable stdout; compilation is real, with
no mocked compiler. Without evidence, show supported capability but execution not-run and
exit 1. A missing check and a missing fixture stay in the denominator with distinct causes.
An empty scope refuses. Human/JSON outputs account for the same IDs. A sentinel proves
assessment invokes no product command. Record runtime/peak memory on this fixture and the
selected real book; do not promise full-book speed from the tiny fixture.

### Slice 2 — complete a surface from current run evidence

Depends on slice 1. Concepts: Contract snapshot, Evidence assessment, Experiment,
Completion verdict. Reuse existing compile/run/report paths to execute the CLI experiment.

Record the versioned content fingerprint with evidence produced by the normal run. The
same book assessed against that run becomes complete; alter a claim while preserving its
ID and observe stale evidence and exit 1. A failed, interrupted, missing or legacy run
without adequate identity cannot pass. No whole-surface verdict may be assembled from a
run that proves only a diff-selected subset. Add explicit cases for duplicate/missing IDs,
excluded records and malformed evidence. Do not redefine the existing plan ID-set digest.

### Slice 3 — make an incomplete surface actionable and precise

Depends on slice 1; retain slice 2 evidence semantics. Concepts: Gap, Finding policy,
Report view. Include doctor structural findings relevant to the selected scope without
flattening them into unsupported-tooling gaps. Display skipped checks as unavailable.

Prove three actual paths: a missing declaration routes to the author, a compiler refusal
routes to tooling, and a missing checkout/input routes to the environment. Classify every
current compile gap through an exhaustive test. Group counts by cause/code while retaining
path:line and remedies. Repair the unselected-button/disabled-button confusion: unselected
`aria-pressed=false` must not suggest `inert`, while a genuinely disabled control lacking
verification must still be reported. Preserve ordinary doctor's severity contract except
this demonstrated false-positive correction. Audit catalog lifecycle severity with actual
returned milestone reports rather than only literal constructor inspection.

### Slice 4 — close the observed sensitivity gaps

Depends on slice 2. Concepts: Witness, Sensitivity trial, Evidence assessment.

The investigation found seven unwitnessed expressions: five stdout/file regex cases and
two filtered JSON paths. Reproduce each from the current source book before changing
generation. Start with `stdout(matches="\\A\\n\\Z")`, then inline-dotall patterns,
anchored multiline file content and filtered JSON arrays. For every genuine harness gap,
make a valid witness accepted by the production verifier and a relevant mutated observation
rejected by it. If an expression is itself impossible or weak, report that measured result;
never force it into sensitive. The same surface assessment must reflect the new evidence.
Bound regex generation; unsupported constructs remain explicitly unwitnessed, never a hang.

### Slice 5 — verify a journey across two HTTP services

Depends on slice 2. Concepts: Experiment, Target binding, HTTP observation, Experiment
assembly, Completion verdict. Extend existing harness/compiler contracts together.

Use two real local HTTP servers on allocated ports: create a record on the first, capture
its ID, read or act on the corresponding record through the second, and verify identity
and outcome. The compiled book journey must run both requests in order and appear complete
with applicable evidence. Route the second request to the wrong service and prove failure;
lose the capture and prove failure. Cover second-service failure, cleanup after interruption,
and two concurrent journeys without target/capture leakage. Keep single-target callers
working. Mixed web/mobile/CLI journeys continue to report unsupported until separately
designed; do not claim all multi-target execution is solved by two HTTP servers.

### Slice 6 — establish the first real-surface acceptance result

Depends on slices 2–5. Concepts: Surface scope, Exclusion, Completion verdict, Report view.

Select a bounded existing CLI command family whose fixtures run locally, then run the real
assessment → compile → execute → assess loop. Record the obligation IDs, source inventory
coverage separately, missing capabilities, current evidence and targeted defect trials.
Fix declarations only when evidence shows them wrong. A tooling gap outside the implemented
capabilities remains named with its owner; add a concrete follow-up slice for that observed
gap rather than an invented universal backend. Do not mark the selected surface complete
until every required dimension is satisfied. Do not claim the entire repository complete.

This series is done only when slices 1–6 have their acceptance evidence and every section
5b receiver has a measured after-value. If the pilot reveals a genuine missing capability,
the series remains incomplete until its added end-to-end slice is delivered. Broad driver
coverage beyond the bounded pilot is separate future work, not hidden acceptance debt.

## 7. Assumptions

Ordered by cost of being wrong:

| ID | Assumption | Decided | Basis | If wrong |
| --- | --- | --- | --- | --- |
| A1 | Completeness is relative to a reviewed behavior contract, not proof that all possible behavior was discovered | Report source inventory coverage separately and qualify completion | User asks about tooling coverage; arbitrary behavior has no finite inferred denominator | Re-derive section 1 outcome and accounting/Completion verdict |
| A2 | A CLI pilot, the observed sensitivity expressions and two HTTP services provide a useful bounded first series | Implement these vertical paths; add capability only when the pilot demonstrates the need | Existing seven unwitnessed findings and explicit multi-server refusal | Re-rank section 6 after measuring the actual surface gap set |
| A3 | The real repository and external artifact roots can change during implementation | Exact assertions use isolated fixture books; live counts use a before/after snapshot per slice | Earlier report includes external planning artifacts; initial tree was clean for this task | Re-derive section 5b comparison scope |
| A4 | Assessment cost is acceptable only if measured, not guessed | Measure slice-1 runtime/memory; preserve current doctor rather than adding work to every invocation | Empty/missing-type probes around 1 s; full assessment not yet implemented | Re-derive section 4 F5 and slice-1 scope before adding caching |
| A5 | Local process execution and two loopback servers suffice for the initial acceptance cases | Avoid external services/credentials in tests; use allocated ports and isolated state | Current CLI/HTTP harness supports these observation classes | Re-derive execution environment and slice-5 fixture contract |
| A6 | Current compiler/harness boundaries can be extended without repository-wide restructuring | Reuse them; new assessment is a consumer, not a replacement framework | `dispatch.py`, compile backends and harness already separate observations | Record wider architecture issue; re-derive the smallest execution boundary needed |
| A7 | Existing run evidence can carry an additive versioned identity | Retain old report behavior; old evidence is insufficient for the new strict verdict | `qa/report.py` already distinguishes missing context and incomplete runs | Re-derive snapshot/evidence contract in slice 2 before claiming freshness |
| A8 | The five baseline failures are environment/root-isolation failures, not failures caused by this plan | Investigate with isolated roots before accepting the implementation gate; never suppress tests | Tracebacks attempt writing `/tmp/.agents/ids.json`; 168 other tests pass | File the existing defect separately and repair it with regression evidence before a green gate |
| A9 | The user authorized implementation dispatch once the plan is ready | Dispatch Kimi with this note, implementation gates and no extra approval round | Latest explicit user instruction | Stop implementation only if the user withdraws that authorization |

Time/input/proof limits: no implementation duration is promised. Fixture books must be
derived through the normal producers. The seven old warning examples are reproducibility
inputs, not current truth until rerun. Synthetic sensitivity proves rejection of named
mutations, not all possible bugs. Loopback acceptance is evidence for runtime composition,
not production deployment reliability. Missing tool permissions or credentials are
reported as environment blockers, never converted to a passing result.
