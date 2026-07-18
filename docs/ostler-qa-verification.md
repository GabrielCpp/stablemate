# Ostler QA as the verification control plane

> **Status:** implemented (2026-07-14). This document extends the
> command-oriented `ostler qa` design in
> [`ostler/docs/QA-RUN.md`](../ostler/docs/QA-RUN.md) into the common, OKF-aware
> runner for command, Playwright, and Maestro verification. It also defines how
> the coder workflow derives QA scope from the maintained OKF library. Section
> 5 supersedes the older design's placement of the plan and pre-run payloads
> inside the disposable `qa/` directory.

## 1. Problem

The coder workflow currently plans and executes QA primarily from story
acceptance criteria. Its prompts mention `ostler qa run` for command-driven
backend work, but they do not use the OKF feature graph to determine which
existing contracts and end-to-end flows a code change may have affected.

This creates two independent gaps:

1. **Narrow scope.** A story can satisfy its acceptance criteria while breaking
   an adjacent state, sibling field, event consumer, persistence path, or
   complete user journey.
2. **Agent-owned execution.** UI and mobile verification are driven directly by
   an agent. The agent both performs actions and narrates what happened, while
   `ostler qa run` only owns command-based execution.

The desired model is:

```text
maintained OKF contracts + story ACs + implementation diff
                         |
                         v
                verification obligations
                         |
                         v
             one reviewed qa-plan.yml
                         |
                         v
     ostler qa run (command | Playwright | Maestro)
                         |
                         v
        append-only log + fresh run evidence
                         |
                         v
          deterministic evidence coverage gate
```

Ostler becomes the verification control plane. Playwright and Maestro remain
the specialized UI execution engines.

## 2. Goals

- Derive QA scope from the story, the implementation diff, and the affected OKF
  graph rather than from acceptance criteria alone.
- Express command, browser, and mobile QA in one reviewable YAML plan.
- Make Ostler own execution, assertion verdicts, process lifecycle, artifact
  capture, and the append-only run log.
- Make Ostler continuously record each browser window or mobile device used for
  primary QA so the complete interaction sequence can be reviewed independently
  of the agent's report.
- Require every impacted OKF obligation to be covered by an executed scenario.
- Delete the complete story `qa/` directory before every run so evidence from
  different runs can never mix.
- Keep plans and pre-run inputs outside the disposable evidence directory.
- Preserve `mechanism` as evidence provenance while introducing `driver` as the
  execution vehicle.
- Give the QA agent a smaller role: author the plan, investigate failures, and
  perform explicitly recorded exploration. The agent does not supply primary
  pass/fail assertions.

## 3. Non-goals

- Ostler does not replace Playwright, Maestro, or shell tools.
- Ostler does not reproduce the complete Playwright or Maestro APIs in a custom
  YAML language.
- An OKF code reference is not runtime evidence. It identifies verification
  scope; only execution against the system proves behavior.
- A changed implementation fingerprint does not prove that an OKF contract is
  outdated. It invalidates prior verification and requires revalidation.
- The diff mapper does not use an LLM, embeddings, or fuzzy text matching.
- `ostler doctor` does not decide whether observed product behavior is correct.

## 4. Two distinct Ostler roles

The workflow must keep two uses of Ostler separate.

### 4.1 Graph and impact role

Before QA planning, deterministic tooling maps changed code to OKF nodes and
expands those nodes to affected contracts and journeys. It writes a scoped
context packet for the planner, executor, evidence gate, and auditor.

### 4.2 Execution role

After planning, `ostler qa validate` validates the complete plan and its OKF
coverage. `ostler qa run` executes every scenario through the selected driver,
records action-level results, captures artifacts, and supplies assertion
verdicts.

An agent must not be able to omit graph retrieval or bypass the runner merely by
forgetting a prompt instruction. Both roles are explicit workflow nodes.

## 5. Artifact and directory contract

The complete `qa/` directory is disposable run output. Full deletion before a
run is intentional and required.

```text
docs/specs/<story>/
  qa-plan.md                 human-readable runbook and rationale
  qa-plan.yml                machine-executable plan
  qa-okf-context.json        generated impact and obligation packet
  qa-okf-context.md          human-readable rendering of the packet
  qa-inputs/                 optional static, versioned run inputs
  qa/                        output from exactly one execution
    qa-run.ndjson            append-only action and assertion ledger
    run-manifest.json        artifacts created by this run
    payloads/                payloads generated during this run
    steps/                   command stdout sidecars
    asserts/                 raw assertion results
    screenshots/             browser and device captures
    traces/                  Playwright traces and diagnostic bundles
    videos/                  runner-owned browser or device recordings
    generated/               transient Playwright/Maestro runner files
```

The load-bearing rule is:

```text
Everything under qa/ is run output and may be deleted.
Nothing required to start a run may live under qa/.
```

Static inputs belong under `qa-inputs/`. Dynamic inputs are produced by fixture
actions after the run starts and may then be written under `qa/payloads/`.

The runner lifecycle is:

```text
validate plan, OKF context, and static inputs
-> delete qa/
-> create an empty qa/
-> write the run manifest and session-start record
-> start declared services and drivers
-> generate runtime payloads and driver files
-> execute scenarios and assertions
-> capture evidence
-> stop drivers and services in a finally block
-> write the terminal run summary
```

Validation reads no required input from `qa/`. Playwright specifications and
Maestro flows generated from the plan are created under `qa/generated/` only
after cleanup.

## 6. Diff-to-OKF context

The workflow adds a deterministic `build_qa_okf_context` node before QA
planning. It receives:

- the base revision;
- the implementation revision or working tree;
- the story and plan context;
- affected repository roots;
- the OKF features root; and
- the source roots associated with each OKF surface.

It computes impact against both base and head:

```text
base source + base OKF --\
                         +-> union of impacted behavior
head source + head OKF --/
```

Using both revisions ensures that deleted, moved, or renamed code remains tied
to its previous behavioral contract and that removing a head `code:` reference
cannot hide impact.

### 6.1 Deterministic mapping

The mapper performs:

1. Parse diff hunks and file renames.
2. Map removed lines through the base symbol index.
3. Map added lines through the head symbol index.
4. Resolve canonical `path::qualified-symbol` references to OKF nodes.
5. Fall back from symbol owner to file owner, then configured surface owner.
6. Include containing OKF nodes and directly grounded flow nodes.
7. Include flows that directly link to impacted contracts.
8. Include the direct contract closure of each impacted flow.
9. Include explicit consistency-group, persistence, event, consumer, and
   concurrency relationships.
10. Emit every mapping and traversal reason; never return a silent empty result
    for changed production code.

The mapper does not infer ownership from lexical similarity. A changed symbol
without an exact symbol, file, or surface owner is an `unmapped-change`
finding.

### 6.2 Health handling

OKF health conditions are independent:

| Condition | Meaning | Workflow behavior |
|---|---|---|
| Graph orphan | Node has no valid path from a declared surface or flow | Include if directly impacted; route graph repair to the author |
| Dangling grounding | `code:` points to a missing file or symbol | Use base mapping when available; route grounding repair to the coder |
| Unowned code | Changed production unit has no OKF owner | Broaden to file/surface and block a final pass until grounded |
| Changed grounding | Referenced implementation changed | Require revalidation; do not assume the prose is wrong |
| Contract drift | Runtime behavior contradicts normative OKF | Fail QA and require an author decision or implementation fix |
| Missing verification | Contract has no executable evidence | Add a required coverage obligation |

An unhealthy graph broadens verification or blocks completion. It never reduces
reported impact.

### 6.3 Context packet

`qa-okf-context.json` has a stable, machine-readable shape:

```json
{
  "version": 1,
  "available": true,
  "base": "abc123",
  "head": "def456",
  "changedCode": [],
  "directNodes": [],
  "contracts": [],
  "journeys": [],
  "journeyNodes": [],
  "verificationRefs": [],
  "verificationIndex": [
    {
      "node": "docs/features/groom/flows/operator-answers-blocked-gate.md",
      "ref": "groom/tests/test_gates.py::test_answer_gate",
      "path": "groom/tests/test_gates.py",
      "impacted": true
    }
  ],
  "healthFindings": [],
  "obligations": [
    {
      "id": "okf:operator-answers-blocked-gate:end-state",
      "kind": "journey",
      "node": "operator-answers-blocked-gate",
      "source": "docs/features/groom/flows/operator-answers-blocked-gate.md",
      "requirement": "An accepted answer clears the gate and refreshes matching detail panes",
      "evidenceRequired": "live",
      "reasons": [
        {
          "kind": "changed-code",
          "ref": "groom/groom/gates.py::answer_gate"
        }
      ]
    }
  ]
}
```

`qa-okf-context.md` renders the same packet for humans and agents. It is not a
second source of truth.

`verificationRefs` contains executable references owned by impacted nodes.
`verificationIndex` contains references from the complete graph and marks whether
each owner is impacted. The coder regression gate uses that complete index for
diagnostic ownership only. Impact attribution never removes a failure from the
story's regression worklist; every regression remains fail-closed.

## 7. Universal QA plan

Plan version 2 adds execution targets and stateful scenarios while retaining the
existing command plan during migration.

```yaml
version: 2
run_id: item-actions-qa
story: item-actions

inputs:
  create_item: qa-inputs/create-item.json

targets:
  web:
    driver: playwright
    base_url: http://localhost:3000
    browser: chromium
    viewport:
      width: 1440
      height: 900
    recording:
      required: true
      mode: window
      fps: 30

  mobile:
    driver: maestro
    app_id: com.example.app
    device: android
    recording:
      required: true
      mode: device
      fps: 30

  api:
    driver: command

scenarios: []
```

### 7.1 Mechanism and driver

`mechanism` continues to describe evidence provenance:

- `live`: interaction with the running product through its supported surface;
- `synthetic`: direct invocation with a hand-authored event or request standing
  in for an upstream producer; and
- `fixture`: setup that establishes test state but does not itself prove the
  behavior under test.

`driver` describes execution:

- `command`;
- `playwright`; or
- `maestro`.

`playwright` and `maestro` must not be added as mechanism values.

### 7.2 Command scenario

```yaml
scenarios:
  - id: create-item-api
    target: api
    mechanism: live
    covers:
      - ac:create-item
      - okf:item-create:persists
    actions:
      - do: command
        id: create-item
        cmd: >
          curl -s -w "\n%{http_code}"
          -X POST http://localhost:8080/items
          -H "Content-Type: application/json"
          -d @{{input.create_item}}
        expect_http: 201
        capture:
          item_id: $.id
        out: qa/steps/create-item-response.json

      - do: command
        id: read-item
        cmd: curl -s http://localhost:8080/items/{{item_id}}
        assert_contains: QA item
        out: qa/steps/read-item-response.json
```

### 7.3 Playwright scenario

```yaml
scenarios:
  - id: item-menu-selection-states
    target: web
    mechanism: live
    covers:
      - ac:selection-actions
      - okf:item-actions:visibility
    actions:
      - do: goto
        url: /items

      - expect: visible
        locator:
          role: button
          name: Add

      - expect: hidden
        locator:
          role: menuitem
          name: Remove

      - do: click
        locator:
          role: checkbox
          name: Item one

      - expect: visible
        locator:
          role: menuitem
          name: Remove

      - expect: visible
        locator:
          role: menuitem
          name: Copy

      - capture: screenshot
        name: item-menu-single-selection
```

The Playwright driver uses role, label, test-id, text, and CSS locators. Role or
label locators are preferred; CSS is an explicit fallback. Validation rejects a
locator shape the driver cannot execute.

### 7.4 Maestro scenario

```yaml
scenarios:
  - id: profile-autosave
    target: mobile
    mechanism: live
    covers:
      - ac:profile-name
      - okf:profile-fields:autosave
    actions:
      - do: launch
        clear_state: false

      - do: tap
        locator:
          text: Profile

      - do: fill
        locator:
          id: display-name
        value: QA Updated Name

      - do: tap
        locator:
          text: Back

      - do: tap
        locator:
          text: Profile

      - expect: value
        locator:
          id: display-name
        value: QA Updated Name

      - capture: screenshot
        name: profile-autosave-restored
```

The Maestro driver translates the common actions into a native flow under
`qa/generated/` and invokes `maestro test` itself.

### 7.5 Escape hatches

The common action vocabulary covers ordinary journeys. Advanced framework work
uses committed native tests without embedding arbitrary JavaScript or a complete
Maestro DSL in the plan:

```yaml
scenarios:
  - id: concurrent-editor-updates
    target: web
    mechanism: live
    covers:
      - okf:editor:concurrent-updates
    test_file: web/e2e/concurrent-editor.spec.ts
    test_name: two editors converge after out-of-order saves
```

```yaml
scenarios:
  - id: offline-mobile-sync
    target: mobile
    mechanism: live
    covers:
      - okf:mobile-sync:offline-recovery
    maestro_flow: mobile/maestro/offline-sync.yaml
```

Ostler still owns invocation, timeout, exit classification, artifacts, and run
log records for native tests.

## 8. Common action vocabulary

Version 2 initially supports:

| Category | Actions and assertions |
|---|---|
| Navigation | `goto`, `launch`, `reload`, `back` |
| Input | `click`, `tap`, `fill`, `select`, `press`, `clear` |
| Synchronization | `wait_for`, `wait_for_response`, `wait_for_idle` |
| State assertions | `visible`, `hidden`, `enabled`, `disabled`, `selected`, `checked` |
| Value assertions | `text`, `value`, `count`, `url` |
| Evidence | `screenshot`, `trace`, `body_text`, `accessibility_snapshot`, `view_hierarchy` |
| Command | `command` with the version 1 capture and inline assertion keys |

Drivers may support additional native capabilities through committed test files.
Adding a common action requires validation and semantically equivalent behavior
for each driver that claims to support it.

## 9. Driver architecture

Ostler defines a small adapter protocol:

```python
class QaDriver:
    def validate(self, target, scenario) -> list[str]: ...
    def start(self, context) -> None: ...
    def run(self, context, scenario) -> ScenarioResult: ...
    def stop(self) -> None: ...
```

### 9.1 Command driver

The command driver preserves the current subprocess, capture, output sidecar,
and inline assertion behavior. It adds explicit action and scenario timeouts and
records command output without exposing secret values.

### 9.2 Playwright driver

The Playwright adapter invokes a stable Node runner. One scenario owns one
browser context and page so cookies, authentication, local state, and navigation
survive between actions. The adapter records:

- every action and assertion;
- screenshots at named capture points and on failure;
- a Playwright trace;
- console errors;
- failed network requests;
- continuous runner-owned video of the configured browser window; and
- requested DOM, text, geometry, or accessibility snapshots.

The agent does not communicate with Playwright directly during primary
verification.

### 9.3 Maestro driver

The Maestro adapter compiles common actions into a native flow, runs the Maestro
CLI, and records:

- every translated command;
- JUnit output;
- screenshots at named capture points and on failure;
- the view hierarchy on failure;
- command stdout and stderr; and
- continuous runner-owned recording of the device or simulator display.

Device and application availability failures are classified as `blocked`, not
as product assertion failures.

### 9.4 Lifecycle guarantee

Driver and daemon cleanup runs from a `finally` block. Timeouts, assertion
failures, invalid output, and keyboard interrupts must not leave browsers,
emulators, child processes, or background services running.

### 9.5 Continuous runner-owned video

For Playwright and Maestro targets, video is primary run evidence rather than an
agent-authored attachment. Recording is enabled and required by default. A plan
may disable it only through an explicit repository policy for a surface where
recording is prohibited; an agent cannot silently turn it off for one story.

Ostler owns the recorder lifecycle:

```text
target ready
-> start recorder
-> verify recorder is producing output
-> write video_start to qa-run.ndjson
-> execute every scenario for that target
-> stop recorder in finally
-> validate and hash the recording
-> write video_stop and artifact records
```

Recording starts before the first QA action and ends only after the final action,
assertion, failure capture, or cleanup screen for that target. A crash, timeout,
failed assertion, or interrupted scenario still produces a finalized recording
when the platform permits it.

Browser recording has two modes:

- `window`: record the browser's virtual display or OS window, including all
  pages, dialogs, cursor movement, and visible transitions for the complete
  target run; and
- `viewport`: use Playwright's context video when repository policy permits a
  page-only recording. This may produce one ordered segment per browser context.

`window` is the default because it captures behavior outside the page viewport,
including browser dialogs and accidental navigation. In headless environments,
Ostler owns the virtual display and its recorder. It does not rely on an agent to
start `ffmpeg` or copy a video afterward.

Mobile recording uses the platform capture tool supervised by Ostler, such as
Android device recording or iOS simulator recording. When a platform imposes a
maximum segment duration, Ostler rotates recordings and registers an ordered
segment list rather than leaving an unrecorded gap. Stitching may produce a
convenience file, but the original ordered segments remain the authoritative
artifacts.

The run log records wall-clock timestamps and monotonic offsets for video start,
every action and assertion, segment boundaries, and video stop. A reviewer can
therefore correlate an assertion directly with the visible frame range that
produced it.

Before accepting a recording, Ostler verifies:

- the recorder started before the first action;
- no expected segment interval is missing;
- the file exists, is non-empty, and has parseable media metadata;
- its duration covers the logged target interval within a small configured
  tolerance;
- its dimensions and frame rate match the target configuration; and
- its content hash is present in `run-manifest.json`.

If recording is required and cannot start, the target is `blocked` and no QA
actions run unrecorded. If execution completes but the recording cannot be
finalized or validated, the run is `invalid`; its product assertions cannot
support a pass.

The QA agent never writes a video file, invokes the recorder, edits a segment,
or supplies video metadata. Only files registered by the active Ostler driver
for the current run are accepted as recording evidence.

## 10. Validation

`ostler qa validate` performs schema and semantic validation before deleting
`qa/` or starting a service.

It checks:

- `version`, `run_id`, and `story` are present;
- every target has a known driver;
- every Playwright and Maestro target has a repository-policy-compliant
  recording configuration;
- every scenario references an existing target;
- every scenario declares `mechanism`;
- scenario and action IDs are unique;
- every action is supported by its selected driver;
- locator shapes are valid and unambiguous;
- capture references are defined before use;
- static input paths exist and remain under the spec directory;
- output paths remain under the spec directory and normally under `qa/`;
- no required input resides under disposable `qa/`;
- required recording tools are available before actions begin;
- timeouts are positive and within configured limits;
- required secrets are declared but not embedded in YAML;
- every `covers` ID resolves to an AC or an obligation in
  `qa-okf-context.json`; and
- every required AC and OKF obligation is covered by at least one scenario with
  a machine-executed assertion.

Listing an obligation in `covers` without an assertion does not satisfy
coverage.

## 11. Run log and evidence

The existing append-only `qa-run.ndjson` remains the primary ledger. Version 2
adds driver, scenario, action, coverage, recording, and artifact fields.

```json
{
  "ts": "2026-07-14T12:00:00Z",
  "kind": "assert",
  "scenario": "item-menu-selection-states",
  "driver": "playwright",
  "action": 5,
  "check": "visible",
  "locator": {
    "role": "menuitem",
    "name": "Remove"
  },
  "result": "PASS",
  "covers": [
    "okf:item-actions:visibility"
  ],
  "artifacts": [
    "qa/screenshots/item-menu-single-selection.png"
  ]
}
```

Every created artifact is registered in `run-manifest.json` with the current
run ID, producing scenario, and content hash. The evidence gate rejects files
that are absent from the current manifest even if a matching path exists.

For UI and mobile targets, the manifest also records the authoritative video or
ordered video segments, media duration, dimensions, frame rate, target ID, and
the action time range covered by each file. A screenshot or narrative report
cannot substitute for a missing required recording.

`qa-evidence.json` remains the workflow verdict artifact, but much of it can be
generated from the run log:

```json
{
  "runId": "item-actions-qa",
  "qa_run_log": "qa/qa-run.ndjson",
  "overall": "Pass",
  "criteria": [],
  "obligations": [
    {
      "id": "okf:item-actions:visibility",
      "verdict": "Pass",
      "log_refs": [
        "item-menu-selection-states:assert:2",
        "item-menu-selection-states:assert:5"
      ],
      "evidence": [
        "qa/screenshots/item-menu-single-selection.png"
      ]
    }
  ]
}
```

The evidence gate requires every mandatory obligation to have executed passing
assertions and any evidence type required by the obligation.

## 12. Outcome model

The runner returns one of four statuses:

| Status | Meaning | Example |
|---|---|---|
| `passed` | All required assertions executed and passed | Expected control state observed |
| `failed` | Product behavior or an evidence assertion was wrong | Autosaved value did not survive reload |
| `blocked` | Required execution environment could not run | Emulator or credential unavailable |
| `invalid` | Plan, mapping, or runner contract was malformed | Unknown locator or uncovered obligation |

These statuses allow the coder workflow to route product defects, setup
problems, and planning defects differently. They replace Boolean success as the
batch runner's public result while retaining a conventional process exit code.

## 13. Secrets and logging

Version 2 distinguishes public configuration from secrets:

```yaml
env:
  region: us-east-2

secrets:
  test_password:
    from_env: QA_TEST_PASSWORD
```

Secret substitutions are passed to drivers but never written to the expanded
command, run log, generated test source, screenshots, or reports. Ostler logs
the symbolic reference and applies redaction to stdout and stderr before
persistence.

Plans containing literal values in secret-designated fields fail validation.

## 14. Coder workflow integration

The QA subflow becomes:

```text
prepare_story
-> clear_qa_evidence
-> resolve_qa_context
-> detect_qa_okf
-> build_qa_okf_context
-> validate_qa_okf_context
-> plan_qa
-> validate_qa_plan
-> review_qa_plan
-> run_qa_plan
-> assess_qa_run
-> verify_qa_evidence
-> audit_qa
-> regression and completion gates
```

### 14.1 Planning

`plan_qa` reads both context files and writes one `qa-plan.yml` for all touched
layers. Its verification contract is the union of:

- story acceptance criteria;
- impacted author-owned OKF contracts;
- completion conditions of impacted journeys;
- consistency-group obligations;
- persistence obligations;
- event producer-to-consumer obligations; and
- concurrency and idempotency obligations;
- flow start preconditions and end states; and
- interaction, component, endpoint, invocation, method, and field requirements such
  as guards, effects, states, keyboard behavior, status/error/auth behavior, returns,
  raises, defaults, and semantics.

Nested OKF bullets are preserved as individual requirements. For example, each child
under `does:` or `steps:` remains visible to impact generation instead of collapsing
to an empty parent value. UI plans start at a flow's declared entry rather than
deep-linking past navigation, and assert the documented end state plus the absence of
unexpected server or console errors.

The human-readable `qa-plan.md` explains the selected scenarios and maps every
AC and OKF obligation to executable evidence.

### 14.2 Semantic plan review and execution

After deterministic validation, an independent semantic reviewer checks whether each
scenario can establish its causal preconditions, traverse the required checkpoints,
and produce terminal evidence that actually proves every `covers` claim. It does not
execute or edit the plan. Revision returns to the bounded planning loop.

The workflow, not an agent, invokes `ostler qa run`. A constructive execution
reviewer then receives the runner-produced log and artifacts for every outcome and
decides whether the run meaningfully reached its objective. It may diagnose plan or
setup repair, or append replayable exploration, but only a subsequent Ostler run can
produce evidence or a verdict.

### 14.3 Audit

The adversarial auditor reads:

- `qa-okf-context.json`;
- `qa-plan.yml`;
- `qa-run.ndjson`;
- `run-manifest.json`; and
- `qa-evidence.json`.

Coverage of required obligations is exhaustive and deterministic. Only an
objective-confirmed, evidence-valid candidate pass reaches the auditor. The auditor
treats the plan and evidence as frozen: it cannot execute, edit, repair, or request
exploration. It may sample the riskiest evidence when rejudging quality, but it may
not sample whether an obligation was omitted. A refutation is classified as a plan
defect, evidence defect, or product contradiction so routing does not confuse bad QA
design with bad product behavior.

### 14.4 Regression attribution and re-QA

The full committed journey suite runs after story-scoped QA. Each parsed failure is
matched against `verificationIndex`:

- an impacted owner identifies a likely change-adjacent cause;
- owners exclusively outside the impacted graph identify where else to investigate;
  and
- no owner identifies an OKF grounding gap.

All three classifications remain story-blocking and go to the regression fixer.
After any regression fix makes the suite green, the workflow rebuilds OKF impact and
reruns the primary plan, evidence gate, and audit. Evidence captured before the code
fix cannot authorize the final pass. A pending re-QA marker is cleared only after that
fresh primary pass and does not reset the cumulative regression-fix budget.

## 15. Documentation ownership and timing

The OKF builder remains a one-time bootstrap for existing code. Ongoing
ownership is:

| Role | Responsibility |
|---|---|
| Author workflow | Maintains intended and normative product behavior |
| Coder workflow | Maintains implementation grounding and as-built links |
| QA workflow | Consumes contracts and records verification evidence |

Coder grounding updates must happen before QA context generation. The workflow
therefore updates implementation references after implementation and review,
then audits the OKF diff before planning QA.

A coder may not silently weaken an author-owned invariant to match its
implementation. Changes to normative behavior require an author decision or an
explicitly authorized story contract change.

## 16. Migration

### Phase 1: harden the existing command runner

- Standardize `qa-plan.yml` at `<spec_dir>/qa-plan.yml`.
- Keep full deletion of `<spec_dir>/qa/` before every run.
- Move static pre-run payloads to `<spec_dir>/qa-inputs/`.
- Generate dynamic payloads through fixture steps after cleanup.
- Add timeouts, guaranteed cleanup, status classification, run manifests, and
  secret redaction.
- Preserve all repeated `code:` and `verify:` bullets in graph output.
- Preserve nested normative bullets such as `does:` and `steps:` in graph output.

### Phase 2: OKF impact and obligation coverage

- Add base/head source symbol indexes with source ranges.
- Add deterministic diff-to-OKF mapping.
- Generate `qa-okf-context.json` and its Markdown rendering.
- Validate `covers` against required ACs and obligations.
- Extend `qa-evidence.json` and its gate with `obligations`.
- Index all `verify:` owners for scoped regression attribution.

### Phase 3: Playwright driver

- Add version 2 targets and scenarios.
- Implement the common browser action vocabulary.
- Add screenshots, traces, console, network, DOM, and accessibility evidence.
- Add continuous browser-window recording owned by the Playwright driver.
- Support committed Playwright tests as an escape hatch.

### Phase 4: Maestro driver

- Compile common mobile actions to native Maestro flows.
- Add JUnit, screenshot, hierarchy, and recording evidence.
- Add continuous device recording with deterministic segment rotation.
- Support committed Maestro flows as an escape hatch.

### Phase 5: make the runner mandatory

- Require `qa-plan.yml` for every coder QA run.
- Move primary execution out of the QA agent node.
- Require complete OKF obligation coverage before a pass.
- Retain agent exploration only when it is recorded and replayable through
  Ostler.

## 17. Acceptance criteria for this design

The design is complete when:

- a changed code symbol deterministically selects its grounded OKF contracts and
  affected flows;
- every selected obligation appears in a validated scenario;
- command, browser, and mobile scenarios execute from one plan;
- Playwright and Maestro assertions are decided by their drivers and recorded by
  Ostler;
- every Playwright and Maestro target has a continuous, runner-owned recording
  spanning its complete action interval;
- every run begins with an empty `qa/` directory;
- no pre-run dependency is stored under `qa/`;
- every evidence artifact belongs to the current run manifest;
- missing mappings, journey steps, event consumers, persistence checks, or
  concurrency checks cannot silently pass;
- a human can inspect the plan before execution and replay or inspect the
  resulting ledger afterward; and
- the coder workflow cannot report QA passed without both complete obligation
  coverage and machine-produced evidence.
