# `ostler qa` — deterministic QA run bookkeeping

Status: **implemented** (2026-07-14).

This is the CLI surface, the ledger format and the plan format, as they stand. The
plan is a Python module (`qa_plan.py`); the YAML format this runner started with is
retired and `ostler qa validate` rejects it by name. Static inputs live outside the
disposable `qa/` directory.

## Why this exists

The `epic-coder` QA workflow currently asks an agent to drive live services (curl, aws CLI,
lambda invoke), collect evidence files, and write a narrative report. That arrangement has a
structural trust problem: the agent is both the executor and the narrator. A reviewer reading
`qa/jira-comment.md` has no way to verify that the narrated sequence of events is what actually
ran — the agent may have issued different commands, gone back and forth investigating, or written
artifacts that look like outputs of commands it never ran.

Two incidents on ACME-4352 surfaced this concretely:

- The `ttl-invoke-response.json` and `modify-overwrite-invoke-response.json` files returned
  `null` from the agent's own read-back — the files were either empty or fabricated rather than
  captured from a real `aws lambda invoke` response.
- A synthetic session item (`app_installation_id=0000abcd`) with no traceable originating login
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
  "run_id": "ACME-4352",
  "story": "ACME-4352",
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
  "run_id": "ACME-4352",
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
    for each daemon's ready_check (URL or {cmd, assert_contains}) before
    proceeding — a check that never passes blocks the run, and a daemon that dies
    first is reported as dead, with its exit code and log tail, rather than as slow.
    Daemons are killed on stop
    or on SIGINT/SIGTERM. Returns immediately on success; daemons run in the
    background under ostler's supervision.
    Creates <spec-dir>/qa/ with steps/ and asserts/ already in it, before the
    first daemon starts. A plan may therefore redirect a command straight into
    qa/steps/ (curl -o, a shell >) without making the directory first; curl
    cannot create a missing parent and exits 23 there, and the empty capture
    that follows reads as a product defect rather than as a layout issue.
    Fails if a session is already open for this spec-dir (prevents nesting).

ostler qa step --id <id> --label <text> --mechanism live|synthetic|fixture
               --cmd <shell-command>
               [--capture <key>=<jq-path>] ...
               [--out <spec-dir>/<file>]
    Execute <shell-command> in a subprocess. Record stdout+stderr, exit code,
    and HTTP status. The status is read from a trailing \n%{http_code}\n
    written out by curl -w; failing that, from the HTTP/x.y status line of a
    curl -D header dump (the last one, so a -L redirect chain reports the
    response that came back rather than the hop that pointed at it). The
    write-out form wins, so a body that merely begins with HTTP/ cannot
    displace the code curl was asked to report.
    If --capture is given, apply each jq-path to the stdout JSON and store the
    result under <key> in the session's capture store (available as
    {{key}} substitution in subsequent step --cmd strings).
    If --out is given, write stdout verbatim to that path as a sidecar file —
    unless the command redirected its own stdout there (curl -o/-D, a shell >),
    in which case the file it wrote is adopted as the step's stdout instead of
    being overwritten with the empty pipe the redirect left behind. qa/ is
    wiped at session start, so bytes at that path are always this run's own
    evidence. The step record carries stdout_file_written_by_cmd: true when
    this happens.
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

ostler qa run <plan-file> [--spec <spec-dir>] [--scenario <id>] [--out-dir <name>]
    Batch mode. Read a qa_plan.py module and execute its scenarios, opening the
    session, starting the declared daemons and writing the ledger around them. The
    plan is written by the agent before any live commands are issued; ostler owns
    all execution. This is the preferred invocation mode — a human can review the
    plan before it runs. See "Run plan format" below.
    --scenario runs a subset, --out-dir redirects the whole ledger; together they
    are the dry run an author uses while writing the plan, and the redirect is
    what keeps a rehearsal out of the evidence the scored run is judged on.
```

---

## Run plan format (`qa_plan.py`)

The plan is a **Python module** at `<spec_dir>/qa_plan.py`. It is not a script: importing
it must only *declare* — a `plan()` call, some targets, and one decorated function per
scenario — because `ostler qa validate` imports it to read those declarations without
running anything. A module that issues a request at import time turns every validation
into a run.

Static inputs live under `<spec_dir>/qa-inputs/`. Nothing required to start a run may live
under `qa/`, because the runner deletes that whole directory after validation and before
execution.

```python
# qa_plan.py — the agent writes this; a human reviews it before ostler executes it

from ostler_qa import Qa, background, input_file, plan, scenario, secret, target

plan(run_id="ACME-4352", story="04-publish-metadata")

api = target("api", base_url="http://localhost:8080")
web = target("web", driver="playwright", base_url="http://localhost:5173")

# Started before the first scenario, killed at stop. `ready_url` is polled for HTTP 200;
# `ready_cmd` + `ready_contains` is ready when the command exits 0 and its stdout carries
# the needle — the only option for a service with no GET that answers 200 (an API whose
# sole route is a POST). The check runs in the daemon's own cwd, which is the repo root.
# `timeout` (default 30s) bounds the poll. A daemon that *exits* before its check passes
# does not wait that out: ostler reports the exit code and the tail of
# `qa/daemon-<name>.log` straight away, because "timed out" describes a slow service and
# says nothing about one that never started (a taken port, a build error).
background("api-server", cmd="cd api && go run ./cmd/server",
           ready_cmd="curl -s -o /dev/null -w '%{http_code}' -X POST "
                     "http://localhost:8080/links -d '{\"longUrl\":\"https://example.com\"}'",
           ready_contains="201", timeout=60)

ADMIN_TOKEN = secret("admin_token", from_env="QA_ADMIN_TOKEN")
PAYLOAD = input_file("payload", "qa-inputs/login-payload.json")


@scenario(target=api, mechanism="live", covers=[
    "ac:1",
    "okf:docs/features/links/http/links.md#create:does:1",
])
def create_records_the_real_author(qa: Qa) -> None:
    """Creating a link ignores a spoofed author and persists the token's own UID."""
    uid = qa.http.post("/auth", json={"token": qa.secret("admin_token")}).json()["localId"]
    created = qa.http.post("/links", json={"longUrl": "https://example.com/a",
                                           "author": "attacker"})
    qa.check("the request was accepted", created.status == 201,
             actual=created.status, expected=201)
    stored = qa.http.get(f"/links/{created.json()['id']}").json()
    qa.check("author is the token UID, not the request body",
             stored["author"] == uid, actual=stored["author"], expected=uid)
```

### What a scenario is given

`Qa` is the whole surface. Every affordance the shell format got by accident is an
explicit attribute here, and the two that used to cost the most are the first two:

| Attribute                          | What it is                                                              |
| ---------------------------------- | ----------------------------------------------------------------------- |
| `qa.dir`                           | the evidence directory, already resolved against `--out-dir` — one spelling, a `Path` |
| `qa.root`, `qa.spec_dir`           | the repo root and the story's spec directory                            |
| `qa.http`                          | a session bound to the target's `base_url`; `.get/.post/.put/.patch/.delete`, each returning a `Response` with `.status`, `.text()`, `.json()` |
| `qa.check(label, condition, …)`    | record one claim; returns the verdict, never raises                     |
| `qa.require(label, condition, …)`  | record one claim and stop the scenario when it does not hold            |
| `qa.step(label)`                   | a context manager grouping a phase's work under one step record         |
| `qa.capture(key, value)` / `qa.get` | publish a value into the ledger so a later report can name it          |
| `qa.artifact(path, kind=…)`        | register a file as evidence; a relative path resolves inside `qa.dir`   |
| `qa.secret(name)`                  | the runtime value of a declared secret — redacted everywhere it is written |
| `qa.page`, `qa.diagnostics`, `qa.by_role(…)`, `qa.goto(…)`, `qa.screenshot()` | the browser, for a `playwright` target |
| `qa.maestro.run(flow)`             | a Maestro flow, for a `maestro` target                                  |

`covers=` on the decorator is the machine-checkable link to the obligations
`qa-okf-context.json` lists, and it is what `qa-evidence.json` is aggregated over. A
single `qa.check` may narrow it with its own `covers=`.

**Do not defend against a wrong key — let it raise.** A missing field is a `KeyError` on
the line that read it, with a traceback in `qa/steps/<scenario>-stdout.txt`. This is the
whole reason the format changed: `jq` answered a missing field with an empty stream, so
`[.responses[] | select(.status >= 500)] | length == 0` passed on every run including the
ones serving 500s, and four separate reviews found that defect by reading.

A scenario that raises fails, and its obligations are not credited. A scenario that
records no assertion at all fails validation before it ever runs — `covers` with nothing
proving it is the defect the old `_exit_sentinel` regex was guessing at.

### Browser diagnostics (`qa/traces/<scenario>-diagnostics.json`)

The Playwright driver writes one diagnostics file per scenario, registered in the manifest
under kind `browser-diagnostics`. It is the whole console and the whole network for that
scenario — every message at every level, every request, every response, every uncaught
exception — each stamped with `atMs`, the same run-relative offset the NDJSON records
carry, so the console and the network can be read against each other and against the step
that was executing:

```json
{
  "schema": "browser-diagnostics/1",
  "consoleErrors": ["<console message text>"],
  "console": [{ "atMs": 1500, "type": "warning", "text": "<text>", "location": "<url>:12:4" }],
  "consoleCount": 1,
  "pageErrors": [{ "atMs": 900, "name": "TypeError", "message": "<message>" }],
  "requests": [{ "atMs": 200, "url": "<url>", "method": "GET", "resourceType": "fetch" }],
  "requestCount": 1,
  "failedRequests": [{ "atMs": 3300, "url": "<url>", "method": "GET", "errorText": "net::ERR_ABORTED" }],
  "responses": [{ "atMs": 4200, "url": "<url>", "status": 200, "method": "GET" }],
  "responseCount": 1
}
```

`schema` names the shape of the file. A trace stays on disk after the run that wrote it, so a
plan repaired later is often verified against one an older driver produced — and the shapes
differ (`failedRequests` was once a list of bare url strings). Without the key that mismatch
surfaces only as a `TypeError` deep in whatever read it, which reads as "the assertion is
wrong" and gets repaired toward the stale shape. Check
`data["schema"] == "browser-diagnostics/1"` before trusting a trace on disk to prove
anything about the plan.

`console` is every message, `consoleErrors` only the `error` ones and by **text** alone —
it predates `console` and is kept because plans assert on it. Prefer `console`: the warning
that explains a failure (a React hydration or key warning is levelled `warn`) is invisible
in `consoleErrors`, so a scenario failing with an empty `consoleErrors` looks like it had a
clean console when it did not.

`pageErrors` is uncaught exceptions, which is a **different event** from the console — an
exception nothing catches reaches `pageerror`, and the console only as a side effect. A
page that threw during hydration is invisible in every other key here.

`requests` is every request issued, `responses` every response received, `failedRequests`
every request that never completed. A request in `requests` with no matching `responses`
entry and no `failedRequests` entry was still in flight when the scenario ended — which is
the shape of a hung endpoint, and is in none of the other keys.

`failedRequests` is one record per request
that never completed — `requestfailed` never fires for a completed response, whatever its
status. Read `errorText` before gating on it: an app cancelling its own in-flight fetch (a
React effect cleanup, a StrictMode double-invoke, a superseding navigation) fires
`requestfailed` with `net::ERR_ABORTED` exactly as a refused connection does, so gating on
the bare list goes red on healthy behaviour. Exclude the aborts the app is expected to make
and keep failing on the rest — `failed_requests` takes the exclusion for you:

```python
qa.check("no request failed unexpectedly",
         qa.diagnostics.failed_requests(ignore=["net::ERR_ABORTED"]) == [])
qa.check("nothing served a 5xx", qa.diagnostics.responses(status_at_least=500) == [])
```

Assert through `qa.diagnostics` rather than by reading the file: the diagnostics file is
written *after* the scenario returns, so a scenario that reads it is reading the previous
run's copy — and a scenario cannot fail itself on a 5xx it provoked any other way.

`console`, `requests` and `responses` are each capped at the harness's `DIAGNOSTICS_LIMIT`
(500) records, and the matching `consoleCount` / `requestCount` / `responseCount` reports
the true total — compare the two before reading a long run's list as complete. `pageErrors`
and `failedRequests` are uncapped: both are rare by construction and both are the thing
being looked for. There is no response **body** and no headers here; a scenario that needs
those should issue the request itself through `qa.http`.

### Validation (`ostler qa validate <plan-file>`)

`ostler qa run` always validates before executing; `ostler qa validate` runs validation
alone, which is what an author calls while writing the plan. Validation imports the module
under the target's interpreter and reads the declarations back, so it catches:

- a plan that **cannot be imported at all** — a syntax error, a missing dependency, a typo
  in a project import. This is the check the YAML format could never offer: a broken plan
  used to surface an hour into a run, as a driver failure against a story that was fine.
- a scenario that `covers` an obligation but **records no assertion**, found by an `ast`
  walk of its body for `qa.check` / `qa.require` calls.
- an obligation this change owes that **no asserted scenario covers**, and a `covers` ID
  that is not an obligation of this change — the message distinguishes an ID documented in
  the book but not owed here from one the book does not know at all, and names what the
  plan *could* cover either way.
- a browser scenario addressing the page by text or CSS where the book documents a role,
  or navigating to a route the book does not document.
- a `recording` a target tried to waive itself; only `ostler.yml`'s
  `qa.recordingExemptTargets` may do that.
- an input file under the disposable `qa/` directory, which is deleted before the run
  starts, and any path escaping the spec directory.
- a background daemon whose `ready_check` is neither an http(s) URL nor a runnable
  `{cmd, assert_contains}` mapping, and duplicate daemon names.
- a `qa-plan.yml`, rejected with the name of the module that replaces it.

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
  "runId": "qa-20260710T170910-ACME-4352",
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
   via `ostler qa step --out`. This alone closes the "log what actually ran" omission.

2. **Assertions** (`ostler qa assert`): adds the CloudWatch confirm check and the event-present
   check. The agent no longer decides pass/fail for these.

3. **Daemon ownership** (`--daemon` on `ostler qa start`): transfers eventbridge-tail and
   dynamo-stream-tail lifecycle to ostler. The agent declares them; ostler starts, monitors, and
   stops them.

Each stage is independently useful and independently testable.
