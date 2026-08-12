# Authoring a `qa_plan.py`

A story's QA plan is a Python module at `<spec_dir>/qa_plan.py`. `ostler` imports it under the
**project's own interpreter** — not ostler's — and runs one scenario per subprocess, streaming
assertion records back on a dedicated fd. So the plan may import the project's client library,
its fixtures, its test helpers; it may not import `ostler`, which is not installed there.

The format is code because the failures worth catching are the ones a runtime catches for free.
A wrong key raises on the line that read it. A wrong type raises. The traceback names both. The
previous format was YAML wrapping shell, and every silent-failure mode had to be caught by a
regex bolted onto the validator — including a `jq` filter over a missing field, which reads as
an empty stream and passes vacuously. That defect class does not exist here.

## The module

```python
import json

from ostler_qa import Qa, background, input_file, plan, scenario, secret, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python", base_url="http://localhost:8090")
web = target("web", driver="playwright", base_url="http://localhost:3000", browser="chromium",
             recording={"required": True, "mode": "window"})
mobile = target("mobile", driver="maestro", app_id="com.example.app",
                recording={"required": True, "mode": "device"})

background("api-server", cmd="cd api && go run ./cmd/server", timeout=60,
           ready_cmd="curl -sf http://localhost:8090/healthz", ready_contains="ok")
secret("ADMIN_TOKEN", from_env="QA_ADMIN_TOKEN")
input_file("seed", "qa-inputs/seed.json")


@scenario(
    target=api,
    mechanism="live",
    covers=["ac:1", "okf:docs/features/demo/http/api.md#publish:does:1"],
    preconditions=["the service health check reports ready"],
    checkpoints=["the publish request is accepted", "the stored object carries the token uid"],
    forbid=["the author field is taken from the request body"],
)
def publish_records_the_real_author(qa: Qa) -> None:
    """Publish ignores a spoofed author and persists the verbatim message."""
    uid = qa.http.post("/v1/session", json_body={"token": qa.secret("ADMIN_TOKEN")}).json()["uid"]
    qa.http.post("/v1/publish", json_body={"author": "attacker", "message": "hello"})
    stored = qa.http.get("/v1/objects/live/page").json()
    qa.check("author is the token uid, not the request body",
             stored["metadata"]["author"] == uid,
             actual=stored["metadata"]["author"], expected=uid)
    qa.check("message is verbatim", stored["metadata"]["message"] == "hello")
    json.dump(stored, qa.artifact("steps/publish-stored.json", kind="json").open("w"))
```

A scenario's **id is its function name** with underscores turned into dashes, and its
**objective is its docstring**. `mechanism` is provenance (`live`, `synthetic`, `fixture`);
`driver` is execution (`python`, `playwright`, `maestro`). Never use a driver name as a
mechanism.

## Declarations

| call | what it declares |
| --- | --- |
| `plan(run_id=…, story=…)` | the run. Exactly one call per module. |
| `target(name, driver=…, interpreter=…, base_url=…, app_id=…, browser=…, viewport=…, recording=…, permissions=…)` | where scenarios execute |
| `background(name, cmd=…, ready_url=… \| ready_cmd=…+ready_contains=…, cwd=…, timeout=30)` | a daemon the runner starts before scenario 1 and stops after the last |
| `secret(name, from_env=…)` | a value read from the environment at run time and redacted from the ledger |
| `input_file(name, path)` | a static fixture; validation checks it exists and sits outside disposable `qa/` |
| `@scenario(target=…, mechanism=…, covers=…, preconditions=…, checkpoints=…, forbid=…, timeout=…, id=…)` | one executable scenario |

`covers` is the machine-checkable link to the story's acceptance criteria and OKF obligations.
`ostler qa validate` set-diffs it against the obligation packet and fails closed on anything
uncovered, so it is the one declaration that cannot move into the body — validation runs before
anything executes.

Readiness belongs on `background`, not in a scenario. A scenario that waits for its own stack
turns a startup failure into a product failure. `ready_url` is fetched and must answer 200 — use
it only when the service really has a `GET` that does; a service whose only route is a `POST`
needs `ready_cmd` + `ready_contains`, which is ready when the command exits 0 and its stdout
contains the needle.

The **heavyweight stack** — docker compose, emulators, the DB and its baseline seed — is not the
plan's to start. It belongs to the workflow's `ensure_stack` step and the repo's `qa-stack.yml`,
is up before the plan runs, and stays up. `background` is for per-run services pinned to the
working tree.

## What a scenario receives

| call | what it does |
| --- | --- |
| `qa.check(label, condition, actual=…, expected=…, covers=…)` | record one claim; returns the verdict, never raises |
| `qa.require(label, condition, …)` | record one claim and stop the scenario if it fails |
| `with qa.step("label"):` | group a phase under a named step in the ledger |
| `qa.capture(key, value)` / `qa.get(key)` | publish a value into the ledger and read it back |
| `qa.artifact(path, kind=…)` | register a file as evidence; relative paths resolve inside `qa.dir` |
| `qa.secret(name)` | a declared secret's value |
| `qa.http.get/post/put/patch/delete(path, json_body=…, headers=…, expect_status=…)` | HTTP bound to the target's `base_url` |
| `qa.dir`, `qa.root`, `qa.spec_dir`, `qa.scenario_id`, `qa.covers` | the paths and identity, already resolved |
| `qa.goto`, `qa.by_role/by_label/by_test_id/by_text/by_css`, `qa.screenshot`, `qa.page` | the browser |
| `qa.diagnostics.console_errors/page_errors/failed_requests/responses()` | the live console and network record |
| `qa.maestro.flow([...])`, `qa.maestro.run(flow)` | build and run a Maestro flow |

`qa.dir` is the single most important attribute: **the** evidence directory, already resolved
against `--out-dir`. Under the old format the same relative string meant the spec directory in
one place and the repo root in another, and one run lost 38 of 66 assertions to it. There is one
spelling now, and it is a `Path`.

`qa.http` is loud on purpose: any status ≥ 400 raises `HttpError` carrying the body unless the
call named it in `expect_status=`. That is the `curl -fsS` behaviour every shell scenario had to
remember to ask for, made the default.

## Rules the validator enforces

- **Module level is declarations only.** `ostler qa validate` imports the module to read the
  plan without running it, so a request, a subprocess or a file write at module scope turns
  every validation into a run. And a plan that does not import fails validation — which is a
  static check the YAML format could never offer.
- **A scenario that claims coverage must assert.** `count_checks` walks the source with `ast`
  and refuses a scenario whose body contains no `qa.check`/`qa.require`; the runtime refuses
  again if a scenario finishes having recorded none. Coverage rides on assertion records, so a
  bare `assert` is invisible to `qa-evidence.json` and proves nothing to the gate.
- **Browser locators come from the book.** `qa.by_role(...)` and its siblings exist so
  `describe` can read their constant arguments out of the parsed tree and check them against
  the OKF node's documented `role`/`name`/`selector`. A locator written as
  `qa.page.get_by_text(...)` is invisible to that check — use `qa.page` directly only for
  interactions the helpers do not cover.
- **`input_file` paths must exist and stay out of `qa/`**, which the runner deletes and
  recreates each run.

## Doctrine

- **Do not defend against a wrong key.** `payload["items"][0]["id"]` is the correct spelling;
  `payload.get("items", [])` converts a broken response into a scenario that passes over
  nothing. Let it raise. A reviewer who sees the defensive form should file it as a finding.
- **Assert on what the behaviour produced, not on an exit code.** A process exiting zero is the
  same evidence a suite that skipped every case produces. When a scenario shells out to a test
  runner, name the case (`-run TestPublishAuthor`, `-k test_publish_author`) and pass the flag
  that defeats the result cache (`go test -count=1`, `gradle --rerun-tasks`) — a cached replay
  prints the same words a real run does, and its cache key does not track the environment
  variables that decide which service was actually tested.
- **A browser scenario asserts on `qa.diagnostics`.** The diagnostics *file*
  (`qa/traces/<scenario>-diagnostics.json`, `schema: browser-diagnostics/1`) is written after
  the scenario has returned its verdict, so only the post-run audit reads it. For the scenario
  to fail *itself* on a 5xx or an uncaught exception, it asserts on the live accessors.
  `failed_requests()` already excludes `net::ERR_ABORTED` — exclude by *reason* like that, never
  by count, since "allow one failure" tolerates a refused connection too.
- **Generate a shared value inside one scenario**, not at module scope. Module-level randomness
  or `time.time()` is a module-level side effect, and it re-evaluates on every describe.

## Running one scenario

```bash
ostler qa validate <spec_dir>/qa_plan.py --spec <spec_dir> --json
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> --json
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> --scenario <scenario-id> --out-dir DIR
```

`--out-dir` is how a rehearsal stays out of the scored ledger: a scenario tuned until it passed
must not be able to leave its own proof where the evidence gate reads it.
