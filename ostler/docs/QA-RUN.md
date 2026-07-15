# `ostler qa` — deterministic QA run bookkeeping

Status: **implemented** (2026-07-14).

This document describes the original version-1 command runner. The universal
version-2 plan, OKF impact packet, Playwright and Maestro adapters, recording
contract, and coder-workflow integration are specified in
[`../../docs/ostler-qa-verification.md`](../../docs/ostler-qa-verification.md).
That document supersedes this one where the contracts differ, especially the
placement of `qa-plan.yml` and static inputs outside disposable `qa/`.

## Why this exists

The `epic-coder` QA workflow currently asks an agent to drive live services (curl, aws CLI,
lambda invoke), collect evidence files, and write a narrative report. That arrangement has a
structural trust problem: the agent is both the executor and the narrator. A reviewer reading
`qa/jira-comment.md` has no way to verify that the narrated sequence of events is what actually
ran — the agent may have issued different commands, gone back and forth investigating, or written
artifacts that look like outputs of commands it never ran.

Two incidents on CASE-4352 surfaced this concretely:

- The `ttl-invoke-response.json` and `modify-overwrite-invoke-response.json` files returned
  `null` from the agent's own read-back — the files were either empty or fabricated rather than
  captured from a real `aws lambda invoke` response.
- A synthetic session item (`app_installation_id=1283ef79`) with no traceable originating login
  was silently reused across the TTL and MODIFY scenarios; this was only discovered by manually
  cross-referencing raw JSON artifacts.

The deeper problem is that there is no append-only record the agent _cannot_ retroactively edit.
CloudWatch Logs proved the two Lambda invokes really happened — but only because a human
independently queried them after the fact, using the agent's own `EventID` strings as search
terms. That check should be automatic, and the log that drives it should be written _by the
infrastructure the human owns_, not by the agent.

Long-running background processes (`eventbridge-tail`, `dynamo-stream-tail`) compound the
problem: the agent currently starts them, manages their lifecycle, and decides when to stop
reading from them. Their output is whatever the agent quotes back; there is no independent
capture.

`ostler qa` solves this by making ostler the deterministic intermediary:

- ostler starts and owns all background daemons; it tees their stdout directly into the run log.
- every action the agent takes against live services is recorded by an `ostler qa step` call —
  not by the agent writing a file.
- assertions (CloudWatch confirmation, event presence, field equality) are _executed_ by ostler
  and recorded with a PASS/FAIL — the agent cannot supply a verdict, only a check specification.
- the run log is append-only NDJSON written by ostler; the agent has no write path to it.

The result: a reviewer can open one file (`qa-run.ndjson`) and see the complete, ordered, typed
record of every action and every check, with timestamps, raw outputs, and verdicts — all written
by the intermediary, not by the agent. If a step is not in the log, it did not happen through
`ostler qa`. If the sequence does not make sense, the agent has a reasoning defect to explain.

---

## Principles

1. **The log is not writable by the agent.** Only `ostler qa step`, `ostler qa assert`, and
   `ostler qa stop` append to `qa-run.ndjson`. The agent calls these commands; it does not write
   the file directly. Evidence JSON files produced by steps are also written by ostler (captured
   from real command stdout), not by the agent's `create_file` call.

2. **Daemons are owned by the session, not the agent.** Background processes declared at
   `ostler qa start` are started, monitored, and killed by ostler. Their stdout is piped into
   the run log automatically. The agent never manages process PIDs or reads daemon output
   directly.

3. **Assertions are checks, not verdicts.** `ostler qa assert` receives a check _specification_
   (what to look for, in which system) from the agent and executes the check itself, writing the
   raw result and PASS/FAIL. The agent cannot pass a `--result PASS` flag.

4. **The log is the evidence.** `qa-run.ndjson` supersedes the scattered `ac1-publish-on-session-end/`
   folder pattern. Individual captured JSON files may still be written as sidecars for human
   browsing, but they are generated _from_ the log, not the primary record.

5. **Replayable by default.** `ostler qa replay` emits the exact sequence of shell commands
   logged during the run, in order, suitable for a human to re-execute in a fresh terminal. If
   re-execution produces different results, the original run is suspect.

---

## Log format (`qa-run.ndjson`)

One JSON object per line, appended in real time, never rewritten. The file lives at
`docs/specs/<story>/qa/qa-run.ndjson` alongside the existing `qa/` directory.

All records share:

- `ts` — ISO 8601 UTC timestamp at the moment ostler wrote the record
- `kind` — the record type (see below)

### Record kinds

**`session_start`**

```json
{
  "ts": "2026-07-10T17:09:10Z",
  "kind": "session_start",
  "run_id": "CASE-4352",
  "story": "CASE-4352",
  "env": { "aws_profile": "dev-case-management", "region": "us-east-2" }
}
```

**`daemon_start`**

```json
{
  "ts": "2026-07-10T17:09:17Z",
  "kind": "daemon_start",
  "name": "eventbridge-tail",
  "pid": 12345,
  "cmd": "go run ./tools/eventbridge-tail --event-bus api-service-dev --port 7890",
  "ready_check": "http://localhost:7890/events"
}
```

**`step`** — one atomic action against a live service

```json
{
  "ts": "2026-07-10T17:15:02Z",
  "kind": "step",
  "id": "login",
  "label": "Create session via mobile-gateway",
  "mechanism": "live",
  "cmd": "curl -s -X POST https://mobile-gateway.example.com/auth/login ...",
  "exit_code": 0,
  "http_status": 200,
  "stdout_file": "qa/steps/login-response.json",
  "captured": { "session_id": "t3lM...", "app_installation_id": "0541fd65..." }
}
```

`mechanism` is one of:

- `live` — a real HTTP call to a real service with a real authenticated token
- `synthetic` — a direct invocation of a handler (e.g. `aws lambda invoke`) with a
  hand-crafted payload that stands in for an event the real system would produce
- `fixture` — a DynamoDB seed or other state setup that does not itself trigger the behavior
  under test

The distinction is **required and enforced** — ostler refuses a `step` call without a `mechanism`.
This is the machine-readable version of the `[LIVE]`/`[SYNTHETIC]`/`[FIXTURE]` tags that
were previously only visible by reading the agent's prose.

**`assert`** — a check ostler executes, not a verdict the agent supplies

```json
{
  "ts": "2026-07-10T17:16:45Z",
  "kind": "assert",
  "id": "ttl_cwlogs_confirm",
  "label": "Lambda execution log confirms synthetic TTL invoke ran",
  "check": "cloudwatch_filter",
  "params": {
    "log_group": "/aws/lambda/dynamo-stream",
    "filter": "qa-synth-ttl-1",
    "window_seconds": 3600
  },
  "raw_result_file": "qa/asserts/ttl_cwlogs_confirm.json",
  "result": "PASS",
  "match_count": 2
}
```

Check types for `ostler qa assert`:

- `cloudwatch_filter` — runs `aws logs filter-log-events` with a relative window; records match
  count; PASS if ≥ 1 match (or `--min-matches N`).
- `event_present` — queries the local `eventbridge-tail` HTTP API; PASS if ≥ 1 event matching
  the filter appears within the timeout.
- `field_equal` — compares two captured values from `step.captured`; PASS if equal.
- `http_status` — compares a step's recorded HTTP status to an expected value (usually already
  implied by the step's `exit_code`, but can be declared explicitly for review clarity).
- `no_duplicate` — counts events matching a filter; PASS if count == 1 (the "no double-publish"
  check).

**`daemon_stop`**

```json
{
  "ts": "2026-07-10T17:22:00Z",
  "kind": "daemon_stop",
  "name": "eventbridge-tail",
  "pid": 12345,
  "exit_code": -15
}
```

**`session_stop`**

```json
{
  "ts": "2026-07-10T17:22:01Z",
  "kind": "session_stop",
  "run_id": "CASE-4352",
  "step_count": 7,
  "assert_count": 5,
  "pass_count": 5,
  "fail_count": 0
}
```

---

## CLI surface

```
ostler qa start <run-id> --story <story-id> --spec <spec-dir>
                [--daemon <name>:<cmd>] ...
    Open a QA session. Write session_start record. Start declared daemons, wait
    for each daemon's ready_check before proceeding. Daemons are killed on stop
    or on SIGINT/SIGTERM. Returns immediately on success; daemons run in the
    background under ostler's supervision.
    Fails if a session is already open for this spec-dir (prevents nesting).

ostler qa step --id <id> --label <text> --mechanism live|synthetic|fixture
               --cmd <shell-command>
               [--capture <key>=<jq-path>] ...
               [--out <spec-dir>/<file>]
    Execute <shell-command> in a subprocess. Record stdout+stderr, exit code,
    and HTTP status (from a trailing \n%{http_code}\n convention on curl calls).
    If --capture is given, apply each jq-path to the stdout JSON and store the
    result under <key> in the session's capture store (available as
    {{key}} substitution in subsequent step --cmd strings).
    If --out is given, write stdout verbatim to that path as a sidecar file.
    Append a step record to the run log. Exits non-zero and appends a failed
    step record if the command exits non-zero, unless --allow-fail is set.

ostler qa assert --id <id> --label <text> --check <check-type> [check-params]
    Execute the named check against a live system (CloudWatch, eventbridge-tail
    HTTP API, or the session capture store). Write the raw result to
    qa/asserts/<id>.json. Append an assert record with PASS or FAIL.
    Exit 0 on PASS, 1 on FAIL (so the agent can detect failures without reading
    the log). The agent supplies check parameters; ostler executes the check.

ostler qa stop
    Kill all session daemons. Write daemon_stop records and session_stop summary.
    Print a one-line verdict: PASS (all asserts passed) or FAIL (≥1 assert failed).

ostler qa report [--spec <spec-dir>]
    Read qa-run.ndjson and render a human-readable action ledger to stdout:
    one line per step (timestamp, mechanism tag, label, result),
    followed by a per-assert summary table.
    Designed to be pasted into a Jira comment as a verifiable trace.

ostler qa replay [--spec <spec-dir>]
    Read qa-run.ndjson and emit the exact shell commands from all step records,
    in order, with inline comments showing what each step captured. Output is a
    valid shell script a human can run in a fresh terminal to reproduce the run.
    Does not re-execute anything.

ostler qa run <plan-file> [--spec <spec-dir>]
    Batch mode. Read a qa-plan.yml file and execute it as if the agent had called
    start / step / assert / stop in sequence. The plan file is written by the
    agent before any live commands are issued; ostler executes it, writes the run
    log, and prints the final PASS/FAIL verdict. This is the preferred invocation
    mode — the agent authors a plan, a human can review it before execution, and
    ostler owns all execution. See "Run plan YAML format" below.
```

---

## Version-1 run plan YAML format (`qa-plan.yml`)

The plan file is written to `<spec_dir>/qa-plan.yml` before `ostler qa run` is
called. Static inputs live under `<spec_dir>/qa-inputs/`. Nothing required to
start a run may live under `qa/`, because the runner deletes that complete
directory after validation and before execution. A human can inspect and abort
the plan before Ostler executes it.

Assertions are **inline** on the step that produces the evidence. This keeps the proof
co-located with the action: you read one step block and see both what was called and how
it was confirmed, without cross-referencing a separate `asserts:` section.

```yaml
# qa-plan.yml — agent writes this; human reviews before ostler executes

run_id: CASE-4352
story: CASE-4352
env:
  aws_profile: dev-case-management
  region: us-east-2
  tenant: valley-view

# Daemons ostler starts before step 1 and kills on stop.
# ready_check: URL ostler polls (HTTP 200) before advancing to the first step.
background:
  - name: eventbridge-tail
    cmd: go run ./tools/eventbridge-tail --event-bus api-service-dev --port 7890
    ready_check: http://localhost:7890/events

steps:
  - id: preflight
    label: Confirm deployed image contains the fix
    mechanism: live
    cmd: >
      AWS_PROFILE={{env.aws_profile}} aws lambda get-function
      --function-name dynamo-stream --query 'Code.ImageUri' --output text
    assert_contains: acb91d11 # ostler checks stdout; agent does not supply this verdict

  - id: login
    label: Create session via mobile-gateway
    mechanism: live # required on every step: live | synthetic | fixture
    cmd: >
      curl -s -w "\n%{http_code}"
      -X POST https://mobile-gateway.example.com/auth/login
      -H "Content-Type: application/json" -d @qa-inputs/login-payload.json
    expect_http: 200
    capture: # JSONPath applied to step stdout
      session_id: $.session_id
      app_installation_id: $.app_installation_id
    out: qa/steps/login-response.json # ostler writes captured stdout here as sidecar

  - id: explicit_logout
    label: Call POST /auth/logout
    mechanism: live
    cmd: >
      curl -s -w "\n%{http_code}"
      -X POST https://mobile-gateway.example.com/auth/logout
      -H "Authorization: Bearer ..."
    expect_http: 200

  - id: wait_logout_event
    label: Confirm AppLogoutNotification published for explicit logout
    mechanism: live
    cmd: >
      curl -s
      'http://localhost:7890/events?detail_type=AppLogoutNotification+V1&n=5'
    assert_contains: "{{session_id}}" # {{key}} expands from prior capture

  - id: seed_ttl_item
    label: Seed DynamoDB sessions table with TTL-expiring item
    mechanism: fixture
    cmd: >
      AWS_PROFILE={{env.aws_profile}} aws dynamodb put-item
      --region {{env.region}} --table-name sessions
      --item file://qa-inputs/ttl-session-item.json

  - id: ttl_invoke
    label: Invoke dynamo-stream handler with synthetic TTL REMOVE event
    mechanism: synthetic
    cmd: >
      AWS_PROFILE={{env.aws_profile}} aws lambda invoke
      --function-name dynamo-stream
      --payload file://qa-inputs/ttl-invoke-payload.json /dev/stdout
    out: qa/steps/ttl-invoke-response.json
    expect_http: 200
    cloudwatch_confirm: # ostler runs filter-log-events; PASS if ≥ 1 match
      log_group: /aws/lambda/dynamo-stream
      filter: qa-synth-ttl-1

  - id: wait_ttl_event
    label: Confirm AppLogoutNotification published for TTL scenario (no duplicate)
    mechanism: synthetic
    cmd: >
      curl -s
      'http://localhost:7890/events?detail_type=AppLogoutNotification+V1&causation_id=qa-synth-ttl-1&n=5'
    assert_contains: qa-synth-ttl-1
    assert_count: 1 # exactly 1 — the no_duplicate check

  - id: modify_invoke
    label: Invoke dynamo-stream handler with synthetic MODIFY overwrite event
    mechanism: synthetic
    cmd: >
      AWS_PROFILE={{env.aws_profile}} aws lambda invoke
      --function-name dynamo-stream
      --payload file://qa-inputs/modify-overwrite-invoke-payload.json /dev/stdout
    out: qa/steps/modify-invoke-response.json
    expect_http: 200
    cloudwatch_confirm:
      log_group: /aws/lambda/dynamo-stream
      filter: qa-synth-modify-1

  - id: wait_modify_event
    label: Confirm AppLogoutNotification published for MODIFY scenario (no duplicate)
    mechanism: synthetic
    cmd: >
      curl -s
      'http://localhost:7890/events?detail_type=AppLogoutNotification+V1&causation_id=qa-synth-modify-1&n=5'
    assert_contains: qa-synth-modify-1
    assert_count: 1
```

### Inline assertion keys

All inline assertions are executed by ostler. The agent writes the check specification;
ostler runs it and records PASS/FAIL in the log.

| Key                  | Type   | What ostler checks                                                                                           |
| -------------------- | ------ | ------------------------------------------------------------------------------------------------------------ |
| `assert_contains`    | string | step stdout contains the literal string                                                                      |
| `expect_http`        | int    | last line of stdout (curl `%{http_code}` convention) equals value                                            |
| `assert_count`       | int    | stdout parsed as JSON array has exactly this many elements                                                   |
| `cloudwatch_confirm` | object | `aws logs filter-log-events` with `filter` over the last hour returns ≥ 1 match (or `min_matches:` override) |

A step with any inline assertion that fails causes `ostler qa run` to continue (recording
FAIL) but report a non-zero exit code at the end. Use `--stop-on-fail` to halt immediately.

### Substitution rules

- `{{key}}` in any `cmd` or assertion string is replaced with the value captured from a
  prior step's `capture` map. Captures are resolved in plan order; forward references
  are rejected at validation time.
- `{{env.<name>}}` expands from the top-level `env` block.
- `{{run_id}}`, `{{story}}` expand from top-level metadata.

### Validation (`ostler qa validate <plan-file>`)

Before executing, ostler validates:

- Every step has a `mechanism` of `live`, `synthetic`, or `fixture` — missing mechanism
  is a hard error.
- All `{{key}}` substitutions in a step resolve to a `capture` key defined in a previous
  step.
- All `background` daemon names cited in `assert_contains` on a `cmd` that queries a
  daemon port match a declared daemon.
- All `out:` paths are under the spec directory (no path traversal).
- `run_id` and `story` are non-empty strings.

`ostler qa run` always validates before executing. `ostler qa validate` runs validation
alone, so the agent or human can check the plan before committing.

---

## What the agent does (and does not do)

**The agent's role is reduced to:**

1. Calling `ostler qa start` once, declaring which daemons are needed.
2. For each action: calling `ostler qa step` with the exact command, label, and mechanism.
3. For each check: calling `ostler qa assert` with a check specification.
4. Calling `ostler qa stop`.
5. Calling `ostler qa report` and copying the output into the Jira comment.

**The agent does NOT:**

- Write files into `qa/` directly (except payload files the agent composes _before_ the step
  that uses them — these are inputs, not evidence).
- Start or stop `eventbridge-tail` or `dynamo-stream-tail`.
- Supply pass/fail verdicts.
- Interpret CloudWatch log output — it passes `--filter <token>` and ostler counts matches.

---

## Integration with `qa-evidence.json` and the workflow gate

The existing `qa-evidence.json` artifact (validated by `ostler artifact vet qa-evidence`) is
_not_ replaced. It remains the workflow gate's source of truth for per-AC verdicts. Instead,
`qa-evidence.json` gains a new optional field:

```json
{
  "runId": "qa-20260710T170910-CASE-4352",
  "qa_run_log": "qa/qa-run.ndjson",
  ...
}
```

When `qa_run_log` is present, `ostler artifact vet qa-evidence` adds a new semantic rule:

- Every `Pass` criterion must cite ≥1 step or assert id from the run log.
- Every cited assert id must have `result: PASS` in the log.
- Every step cited as evidence must have `mechanism` declared (rejects missing-mechanism steps
  retroactively).

This preserves the existing `qa-evidence` gate contract while giving it a verifiable backing
record for the first time.

---

## Incremental adoption

The full `ostler qa` surface can be built in three stages without breaking the existing workflow:

1. **Log writer only** (`ostler qa start/step/stop`): no daemons, no assertions. Steps record
   commands and outputs. The agent still queries eventbridge-tail manually but captures results
   via `ostler qa step --out`. This alone closes the "log what actually ran" gap.

2. **Assertions** (`ostler qa assert`): adds the CloudWatch confirm check and the event-present
   check. The agent no longer decides pass/fail for these.

3. **Daemon ownership** (`--daemon` on `ostler qa start`): transfers eventbridge-tail and
   dynamo-stream-tail lifecycle to ostler. The agent declares them; ostler starts, monitors, and
   stops them.

Each stage is independently useful and independently testable.
