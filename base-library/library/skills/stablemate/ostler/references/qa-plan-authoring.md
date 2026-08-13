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
             actual=stored["metadata"]["author"], expected=uid,
             covers=["ac:1"])
    qa.check("message is verbatim", stored["metadata"]["message"] == "hello",
             covers=["okf:docs/features/demo/http/api.md#publish:does:1"])
    json.dump(stored, qa.artifact("steps/publish-stored.json", kind="json").open("w"))
```

A scenario's **id is its function name** with underscores turned into dashes, and its
**objective is its docstring**. `mechanism` is provenance (`live` — drive the running product — or `fixture` — drive it
from a canned input). There is no third: a test suite standing in for the product is not
evidence about the product. `driver` is execution (`python`,
`playwright`, `maestro`). Never use a driver name as a mechanism.

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

The scenario-level `covers` is a *promise about the function*. The `covers=` on each
`qa.check`/`qa.require` is what discharges it, and validation now requires every id in the
scenario's list to be claimed by at least one assertion, written literally. Both exist because
they answer different questions: which obligations this scenario is responsible for, and which
line proves each one. Collapsing them is what let a scenario keep `covers=["ac:4"]` after its
AC4 assertions were deleted, with the remaining unrelated check reporting AC4 proven.

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
| `qa.verify(check, observed, covers=…, **args)` | make the observation the book declares, and record it |
| `with qa.step("label"):` | group a phase under a named step in the ledger |
| `qa.capture(key, value)` / `qa.get(key)` | publish a value into the ledger and read it back |
| `qa.artifact(path, kind=…)` | register a file as evidence; relative paths resolve inside `qa.dir` |
| `qa.secret(name)` | a declared secret's value |
| `qa.http.get/post/put/patch/delete(path, json_body=…, headers=…, expect_status=…)` | HTTP bound to the target's `base_url` |
| `qa.dir`, `qa.root`, `qa.spec_dir`, `qa.scenario_id`, `qa.covers` | the paths and identity, already resolved |
| `qa.goto`, `qa.by_role/by_label/by_test_id/by_text/by_css`, `qa.screenshot`, `qa.page` | the browser |
| `qa.vet(screen, name=…)` | photograph the state and register what rendered against the screen document |
| `qa.diagnostics.console_errors/page_errors/failed_requests/responses()` | the live console and network record |
| `qa.diagnostics.layout()` | the viewport, the laid-out document, and each structural region's box as a share of it |
| `qa.maestro.flow([...])`, `qa.maestro.run(flow)` | build and run a Maestro flow |

### `qa.verify` — the assertion whose strength is not yours to choose

An obligation whose OKF node carries a `verify:` bullet declares *the observation that
fulfils it*, as a named check with arguments:

```markdown
- verify: json_path(path="item.id", equals="abc")
- verify: keys_unchanged(subject="pages")
- verify: http_status(code=409, title="Manifest Conflict")
```

Those calls arrive on the obligation row in `qa-okf-context.json` as `checksDeclared`, and
`ostler qa validate` refuses a plan that claims the obligation without invoking each of them
with **those arguments**, bound to **that id**:

```python
payload = qa.http.get("/items/abc").json()
qa.verify("json_path", payload, path="item.id", equals="abc", covers=[OBLIGATION])
```

`observed` is what you went and got — a response, a parsed document, a locator, or the
`(before, after)` pair a differential check compares. The comparison itself is the harness's,
which is the entire point: `qa.check` takes an already-collapsed bool, so it lets the scenario
decide what "the manifest is unchanged" means and decide it weakly — mask the object before
diffing, compare three entries but never the key inventory, read back through the session that
wrote. Here the assertion cannot be weaker than the claim, because the assertion *is* the
claim. `qa.check` stays for everything the book did not declare.

A wrong-shaped `observed` raises rather than recording red. A scenario handing `unchanged` a
single value has a defect of its own, and filing that against the product is how a QA run
reports a bug nobody has.

`qa.dir` is the single most important attribute: **the** evidence directory, already resolved
against `--out-dir`. Under the old format the same relative string meant the spec directory in
one place and the repo root in another, and one run lost 38 of 66 assertions to it. There is one
spelling now, and it is a `Path`.

`qa.screenshot(name)` writes three files, not one: the image, a `.layout.json` beside it, and a
`.regions.json`. Both JSON files come from one `ostler vet` DOM scan of the same instant — the
layout digest is the viewport, the laid-out document and every *structural* region's box as a
share of it, and the regions file is that scan undigested, in the shape `ostler vet --regions`
replays to register the screen's documented components. They are the only layout evidence
anything downstream can read, and the independent audit refutes a pass from them. A browser
assertion cannot stand in for it: `by_role` finds an element in the accessibility tree whether
the page lays it out across the window or crushes it into a column against one margin.

`qa.vet("docs/features/web-app/gui/screens/reference.md", name="loaded")` is `qa.screenshot`
plus the verdict: it registers each scanned region against the `placement:` band the book gives
that component, and every disagreement becomes a failed assertion in the ledger quoting the
measured share. A UI scenario must call it — `validate` rejects a `playwright` or `maestro`
scenario that vets nothing, and the runtime refuses one that reached the end having vetted
nothing. On a `maestro` target it photographs the device and reads the regions from the view
hierarchy (`maestro hierarchy`, or `uiautomator` on Android via
`qa.device_screenshot(name, source="uiautomator")`) instead of from a DOM; the sidecars it
writes are the same two documents, stamped `device-layout/1`. The screen path is written literally, and must be a document this story's obligation
packet names; there is no exemption list, because the run this exists to stop was a run whose
every assertion was true.

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
- **A UI scenario must vet.** `extract_vets` walks the source the same way and refuses a
  `playwright`/`maestro` scenario with no `qa.vet` call, a computed screen path, or a screen
  the story's packet does not name. Presence is not placement: every assertion can hold while
  the page renders as a sliver against one margin.
- **Browser locators come from the book.** `qa.by_role(...)` and its siblings exist so
  `describe` can read their constant arguments out of the parsed tree and check them against
  the OKF node's documented `role`/`name`/`selector`. A locator written as
  `qa.page.get_by_text(...)` is invisible to that check — use `qa.page` directly only for
  interactions the helpers do not cover.
- **Every obligation is claimed by an assertion.** An id in the scenario's `covers` that no
  `qa.check(..., covers=[...])` in the body names is a failed validation, not a warning. The
  ids must be literal: the binding is recovered statically by `extract_check_covers`, and a
  computed list claims nothing.
- **A declared check must be invoked.** If the obligation's row carries `checksDeclared`, a
  `qa.verify` with that name, those arguments and `covers=[<id>]` has to appear somewhere in
  the plan — not necessarily in one scenario, since a success path and a conflict branch may
  live in two. The refusal quotes the expected call and the defect a weaker assertion would
  let through.
- **`input_file` paths must exist and stay out of `qa/`**, which the runner deletes and
  recreates each run.

## Doctrine

- **Every acceptance criterion and every OKF obligation is tested. There is no exception.**
  Not "covered by a unit test elsewhere", not "deferred", not "unobservable from here". If an
  obligation is genuinely unprovable through the target, that is a finding to escalate — the
  story is either mis-specified or missing a seam — not a line to delete. `validate` fails
  closed on an uncovered obligation precisely so the decision reaches a human.
- **Prove it live.** The scenario exercises the running product through its real target — the
  HTTP surface, the browser, the device. Asserting that a unit test exists, shelling out to a
  suite, or re-checking a fixture the product never touched is wasted motion: it proves the
  test file, not the behaviour, and the whole reason this plan runs against a live stack is
  that the unit suite already ran and said nothing about integration.
- **Removing an assertion is never a repair.** A failing check is a result. Deleting it,
  loosening it until it cannot fail, or moving its obligation onto a cheaper claim converts a
  red run into a green one without touching the product — which is the single most expensive
  mistake available here, because everything downstream then treats the story as done. If an
  assertion is *wrong* (it asserts something the story never promised), say so and fix the
  assertion. If it is right and failing, the product is broken: report it. When the repair is
  a coverage trade, stop and escalate rather than deciding it inside the lane.
- **Read state that can still be changing with a retrying API.** `expect(locator).to_*` polls;
  `.count()`, `.is_disabled()`, `.inner_text()` and `evaluate()` sample once, immediately. A
  bare read against a UI that is still resolving a promise, an animation or a re-render is a
  race, and it fails in exactly the shape of a product defect — intermittently, with a
  plausible actual value. Await the condition first (`expect(...).to_be_visible()`,
  `locator.wait_for(state="visible")`, `wait_for_selector`), then read — and await *the locator
  you are about to sample*. A wait for something else is not a wait for this: `wait_for_url()`
  returns when the navigation commits, which says nothing about an element the route renders two
  frames later, and the sample that follows it reads as absent. Two round trips are two instants,
  so a `wait_for` followed by a separate `evaluate()` snapshot can observe the state *after* the
  one it waited for. A state that is transient by nature — a spinner between two
  fast operations — needs the transition held (block the response, throttle the route) or it
  needs to be asserted through something durable it leaves behind; sampling faster does not
  fix it.
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
