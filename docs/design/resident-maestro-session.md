# One resident Maestro session per phone scenario

Disclosure: the existing harness was read before this note. The probe, the hierarchy reader,
the flow runner and commit 3674f221d were all read first. Every design decision they carry is
listed as a claim in 1b and re-derived or rejected in section 4.

## 1. Problem

- A book writer proving a phone book waits about 34 s on every check before the phone does
  anything the check asked for. A whole-book pass of about 300 checks spends about 3.3 h, and
  about 2.8 h of it is process start-up, not the app.
- Done: a check's wall time minus its in-flow time drops by at least 20 s, and the whole-book
  pass on kappa drops by at least 45 min, with the same verdict on every scenario.
- Out of scope: the cost of `clearState` relaunches, scrollUntilVisible failures, the adb link
  fault, and the web and HTTP surfaces.

## 1b. Claims

1. Each check flow runs as its own `maestro test` process (the harness runner).
2. The device is released before every flow, so the resident reader never holds it while a
   flow runs (`release_device`).
3. The screen read after a check boots its own `maestro hierarchy` (scan).
4. A resident `maestro mcp` session answers a read in 0.14 to 0.22 s after a 6 s start, and
   rebuilds the JSON tree from CSV (3674f221d).
5. A failing check leaves its command log, junit file and screenshots under the run's output
   folder (`--test-output-dir`).

## 2. Parts and concepts

Level 1:

- **Session**: one live connection to the phone's automation driver. It owns start, health
  and stop. It never knows what a check asks.
- **Running a check**: hands a flow to the phone and reports pass or fail with its evidence.
  It never knows how the screen is read afterwards.
- **Reading the screen**: returns the element tree and the screenshot after a check. It never
  knows which flow ran.
- **Evidence**: what a failed check leaves for the writer. It never knows the transport.

Flow: the scenario opens one Session. Each check is run through it, then the screen is read
through it. Evidence is kept from whatever the run wrote. The Session closes at scenario end.

| Part | Concept | Owns | Never knows |
|---|---|---|---|
| Session | Driver session | the one connection and its restart on death | flows, reads |
| Running | Flow runner (role) | run one flow, return verdict and evidence paths | the transport behind it |
| Running | One-shot runner (variant) | a fresh `maestro test` per flow | sessions |
| Running | Resident runner (variant) | the flow sent through the Session | process start |
| Reading | Screen reader (role) | the element tree now on screen | the transport |
| Evidence | Evidence folder | the files a failed check leaves | which runner wrote them |

## 3. Invariants

- A read and a flow never hold the device at once. Owner: Driver session.
- The resident reader's element set equals the one-shot reader's element set on the same
  screen. Owner: Screen reader, checked by a parity test.
- A failed check leaves a command log and a screenshot. Owner: Flow runner.

## 4. Forces and patterns

- Start-up dominates: 12.8 s per `maestro test`, 12.4 s per `maestro hierarchy`, measured
  2026-10-29 on kappa. Pattern: one session held across a scenario.
- Two runners must coexist while the resident one is proved, and a one-shot fallback is needed
  when the Session dies. Pattern: Flow runner role with two variants, chosen where the harness
  is assembled.
- Claim 1 is kept as the one-shot variant. Claim 2 is re-derived: release is needed only
  because two processes compete for the driver. With one Session it becomes "flows and reads
  share the Session". Claim 3 is rejected: no force needs a second process for the read.
  Claim 4 is kept. Claim 5 is kept as an invariant.
- Open lookups: whether mcp `run_flow_files` leaves claim 5's evidence, and the resident read's
  element parity. Both need the device.

## 5. Mapping onto the existing system

- Driver session: exists as `ResidentReader` in `ostler_qa_hierarchy.py`. Reshape: it serves
  reads only.
- Screen reader: exists as `scan` with source `maestro`. Mismatch: it calls
  `maestro_elements`, which releases the Session and boots a one-shot read. 3674f221d moved
  settle to the resident reader and gives no reason scan stayed on the one-shot.
- One-shot runner: exists as `qa.maestro.run` in `ostler_qa.py`.
- Resident runner: new, beside it.
- Evidence folder: exists as `keep_evidence` in the okf-book exercise command.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Writer reading a failure | command log, junit, screenshots in `evidence:` | keep_evidence test | present on every failed run | present |
| Layout and regions artifacts | `.layout.json`, `.regions.json` per check | nothing | one per vetted check | one per vetted check |
| Element-set parity | same elements a check's assertions read | nothing | unmeasured (A1) | equal sets on 10 screens |
| Verdicts | pass or fail per scenario | the run | last kappa pass | identical |

## 6. Slices

1. Scan reads through the resident Session. Done when the parity test passes on 10 kappa
   screens, a check's read drops by at least 6 s, and every 5b row holds. The session still
   restarts after each flow, so the read stays at 5 to 10 s until slice 2.
2. Flows run through the Session's `run_flow_files`, behind the Flow runner role, one-shot as
   fallback. Done when a check's start cost drops below 2 s, a failed check still leaves its
   evidence, and every 5b row holds.

## 7. Assumptions

1. The CSV tree carries every element and attribute the parsers read. Decided: slice 1 gates on
   a parity test. Basis: none measured. If wrong: slice 1 converts or keeps the one-shot.
2. `run_flow_files` honours the same flow YAML and can write evidence. Decided: slice 2 behind a
   role with fallback. Basis: the tool's schema only. If wrong: slice 2 is dropped.
3. The device is free for the measurements only between run_book turns, or under
   `exercise.lock`. Decided: measure while holding the lock. Basis: the exercise command.
