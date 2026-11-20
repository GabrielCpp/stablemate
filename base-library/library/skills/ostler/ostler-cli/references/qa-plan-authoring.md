# Authoring a `qa_plan.py`

A story's QA plan is a Python module at `<spec_dir>/qa_plan.py`. `ostler` imports it under the
**project's own interpreter** — not ostler's — and runs one scenario per subprocess, streaming
assertion records back on a dedicated fd. So the plan may import the project's client library,
its fixtures, its test helpers; it may not import `ostler`, which is not installed there.

The format is code because the failures worth catching are the ones a runtime catches for free.
A wrong key raises on the line that read it. A wrong type raises. The traceback names both.

## The module

```python
import json

from ostler_qa import Qa, background, input_file, plan, scenario, secret, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python", base_url="{gateway}")
web = target("web", driver="playwright", base_url="{web}", browser="chromium",
             recording={"required": True, "mode": "viewport"})
mobile = target("mobile", driver="maestro", app_id="com.example.app",
                recording={"required": True, "mode": "device"})

background("api-server", argv=["go", "run", "./cmd/server"], cwd="api", timeout=60,
           ready_url="http://localhost:8090/healthz")
secret("ADMIN_TOKEN", from_env="QA_ADMIN_TOKEN")
secret("DB_PASSWORD", from_file=".qa-secrets/db-password")   # a file the trial wrote
tool_env("TZ", "APP_HOME")                                   # names qa.tool(...).run(env=) may set
input_file("seed", "qa-inputs/seed.json")


@scenario(
    target=api,
    mechanism="live",
    covers=["claim:1", "claim:2"],
    preconditions=["the service health check reports ready"],
    checkpoints=["the publish request is accepted", "the stored object carries the token uid"],
    forbid=["the author field is taken from the request body"],
)
def publish_records_the_real_author(qa: Qa) -> None:
    """Publish ignores a spoofed author and persists the verbatim message."""
    uid = qa.field(qa.http.post("/v1/session", json_body={"token": qa.secret("ADMIN_TOKEN")}).json(), "uid")
    qa.http.post("/v1/publish", json_body={"author": "attacker", "message": "hello"})
    stored = qa.http.get("/v1/objects/live/page").json()
    qa.check("author is the token uid, not the request body",
             qa.field(stored, "metadata.author") == uid,
             actual=qa.field(stored, "metadata.author"), expected=uid,
             covers=["claim:1"])
    qa.check("message is verbatim", qa.field(stored, "metadata.message") == "hello",
             actual=qa.field(stored, "metadata.message"), expected="hello",
             covers=["claim:2"])
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
| `background(name, argv=[…], ready_url=…, ready_method=…, ready_status=…, cwd=…, reset_paths=…, timeout=30)` | a daemon the runner starts before scenario 1 and stops after the last. `argv` is a program and its arguments — there is no shell, so no `&&`, no pipeline; a plan that wants two processes declares two daemons |
| `secret(name, from_env=…)` / `secret(name, from_file=…)` | a value read at run time — from the operator's environment, or from a root-relative file the trial wrote before the run (outside disposable `qa/`; one trailing newline stripped) — and redacted from the ledger. Exactly one source; a missing variable or an empty file blocks the run |
| `tool_env("TZ", "APP_HOME", …)` | the environment variable names a scenario may set on `qa.tool(name).run(env=…)`; anything outside the list raises, and `QA_*`/a secret's variable are refused at validation |
| `input_file(name, path)` | a static fixture; validation checks it exists and sits outside disposable `qa/` |
| `@scenario(target=…, mechanism=…, covers=…, preconditions=…, checkpoints=…, forbid=…, restart=…, timeout=…, id=…)` | one executable scenario. `restart=["api-server"]` has the runner stop and start that declared daemon again immediately before this scenario — the seam a persistence criterion needs; a daemon's `reset_paths` are *not* re-applied on a restart |

`covers` is the machine-checkable link to the criteria the plan is scoped to. When every
service of the story has an executable book and the book's own play judged the story, the
criteria are the claims no call of a book can show, each named `claim:<n>`. When no book judged
the story, they are the story's Acceptance Criteria, each named `ac:<n>`, numbered from 1 in the
order the story lists them. `covers` holds only those ids. `ostler qa validate` fails closed on
a criterion no scenario covers, so the declaration cannot move into the body: validation runs
before anything executes.

A criterion the story's own words make universal (`every`, `all`, `each`, `throughout`, a
parenthesized category list) needs a coverage inventory first: list each named category in
`qa-plan.md` and map each to an assertion. A representative sample proves only the category it
exercises. Write no scenario against anything the criteria do not name.

The scenario-level `covers` is a *promise about the function*. The `covers=` on each
`qa.check`/`qa.require` is what discharges it, and validation requires every id in the
scenario's list to be claimed by at least one assertion, written literally. Both exist because
they answer different questions: which criteria this scenario is responsible for, and which
line proves each one. Collapsing them lets a scenario keep `covers=["ac:4"]` after its AC4
assertions were deleted, with the remaining unrelated check reporting AC4 proven.

`recording={"required": True, "mode": "window"}` films a display the runner starts for the
target, at the viewport's exact size, and launches the browser onto it — it does **not** grab
whatever screen `$DISPLAY` names, because on a developer machine that files a valid mp4 of
someone's desktop as proof the app worked. Xvfb is therefore required, not a fallback. Add
`"display": ":99"` only for an image that runs one as a service, and know that you have taken
responsibility for what is on that screen.

`recording` has two modes and the default is `viewport`: Playwright films its own page,
headless, with no display involved, so the artifact is the app under test by construction and
the run behaves identically on Linux and macOS. Its files land in `qa/videos/<scenario>/`.

`mode: "window"` is the opt-in alternative — ffmpeg grabbing an X display that the runner
starts at the viewport's exact size and launches a headed browser onto. Take it only when the
evidence must include browser chrome or an OS-level dialog, and know what it costs: it is
**Linux-only** (no Xvfb on macOS, no `x11grab` there, and avfoundation films the physical
desktop), and it needs Xvfb installed. It does *not* grab whatever screen `$DISPLAY` names —
that shipped once, and on a developer machine it files a valid mp4 of somebody's terminal as
proof the app worked. Add `"display": ":99"` only for an image that runs one as a service, and
know that you have taken responsibility for what is on that screen.

Readiness belongs on `background`, not in a scenario. A scenario that waits for its own stack
turns a startup failure into a product failure. `ready_url` is fetched and must answer 200; a
service whose only route is a `POST` says so with `ready_method="POST", ready_status=201`. The
probe is HTTP and nothing else. A daemon that *exits* before its probe passes is reported with its exit code
and log tail straight away, not after the timeout.

A **restart seam** is the runner's, for the same reason readiness is: it holds the PID and the
probe. Write the value in one scenario, declare `@scenario(..., restart=["api-server"])` on the
next, and read it back there — the process went away and came back between the two, so the read
observes survival rather than process memory. A plan that reads through the session that wrote
proves nothing about persistence, however many times it reads.

The **heavyweight stack** — docker compose, emulators, the DB and its baseline seed — is not the
plan's to start. It belongs to the workflow's `ensure_stack` step and the book's `stack.yml`
([stack.md](stack.md)), is up before the plan runs, and stays up. `background` is for per-run services pinned to the
working tree.

## What a scenario receives

| call | what it does |
| --- | --- |
| `qa.check(label, condition, actual=…, expected=…, covers=…)` | record one claim; returns the verdict, never raises |
| `qa.require(label, condition, …)` | record one claim and stop the scenario if it fails |
| `qa.field(data, "a.b.0")` | read observed data along a dotted path; a missing key yields `MISSING` |
| `with qa.step("label"):` | group a phase under a named step; the report lists each assertion and screenshot under the step it ran in |
| `qa.capture(key, value)` / `qa.get(key)` | publish a value into the ledger and read it back |
| `qa.artifact(path, kind=…)` | register a file as evidence; relative paths resolve inside `qa.dir`. A directory is filed file by file (every file under it, one manifest row each, `directory` naming the root); an empty directory is a problem |
| `qa.secret(name)` | a declared secret's value |
| `qa.tool(name).run(*args, cwd=…, env=…, timeout=…)` | an external command found on PATH; `cwd` must stay inside `qa.dir`, `env` keys must be declared with `tool_env(...)`; returns `ToolResult(stdout, stderr, exit_code)` |
| `qa.eventually(label, lambda: …, covers=…)` / `qa.require_eventually(...)` | the retrying forms of `check`/`require`: hand them a callable — a lambda, a bound method, a nested function — and the sampler re-evaluates it until it holds or the timeout passes. A bare `wait_for*` statement is refused by plan lint |
| `qa.http.get/post/put/patch/delete(path, json_body=…, headers=…, expect_status=…)` | HTTP bound to the target's `base_url` |
| `qa.dir`, `qa.root`, `qa.spec_dir`, `qa.scenario_id`, `qa.covers` | the paths and identity, already resolved |
| `qa.goto`, `qa.by_role/by_label/by_test_id/by_text/by_css`, `qa.screenshot`, `qa.page` | the browser |
| `qa.diagnostics.console(level=…, contains=…)` / `console_errors()` / `page_errors()` | the live console: every message with its structured `args`, not just DevTools' rendering |
| `qa.diagnostics.requests(url_contains=…)` / `responses(status_at_least=…, url_contains=…)` / `failed_requests(ignore=…)` | the live network: headers, request payload, response body, status and `durationMs` |
| `qa.diagnostics.layout()` | the viewport, the laid-out document, and each structural region's box as a share of it |
| `qa.maestro.flow([...])`, `qa.maestro.run(flow)` | build and run a Maestro flow |

`qa.dir` is the single most important attribute: **the** evidence directory, already resolved
against `--out-dir`. It is a `Path`, and a file a scenario writes goes under it through
`qa.artifact(...)`.

`qa.screenshot(name)` writes three files, not one: the image, a `.layout.json` beside it, and a
`.regions.json`. Both JSON files come from one `ostler vet` DOM scan of the same instant — the
layout digest is the viewport, the laid-out document and every *structural* region's box as a
share of it, and the regions file is that scan undigested, in the shape `ostler vet --regions`
replays to register the screen's documented components. They are the only layout evidence
anything downstream can read, and the independent audit refutes a pass from them. A browser
assertion cannot stand in for it: `by_role` finds an element in the accessibility tree whether
the page lays it out across the window or crushes it into a column against one margin.


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
- **Every criterion is claimed by an assertion.** An id in the scenario's `covers` that no
  `qa.check(..., covers=[...])` in the body names is a failed validation, not a warning. The
  ids must be literal: the binding is recovered statically, and a computed list claims nothing.
- **A status of 500 or higher is a product defect.** `expect_status=` lists only the statuses
  the product owes, and a plan never asserts a 5xx as the expected outcome.
- **Arrangement is declared.** State a scenario needs is reached by driving the product's
  documented operations inside a `qa.step`, never by writing rows behind the product's back.
- **The plan has a companion `qa-plan.md`.** Create it with
  `ostler create spec <story-id> qa-plan.md` so the frontmatter is stamped, then write below it
  the preflight, one section per criterion, and each scenario's objective, preconditions,
  checkpoints and forbidden bypasses.
- **`input_file` paths must exist and stay out of `qa/`**, which the runner deletes and
  recreates each run.

## What a reviewer reads

A run ends with `ostler` rendering `<spec-dir>/qa-report.md` from the ledger — no agent prose
in it. For every criterion it gives a verdict (PASS,
FAIL, or UNPROVEN when nothing looked), and under it the step each covering assertion ran
in, the assertion's label, check, observed and expected values, the assertion file, and the
screenshots taken in that step; then every scenario step by step;
then a `## Warnings` list naming what would let a rubber stamp through — a criterion no
assertion covers, an assertion with no observed value, a scenario that stopped early. That
file is what a peer reads to decide whether the work is real, and every string in the plan
ends up in it. So:

- phrase `qa.step("…")` as what a person does — `"sign in with the seeded editor"`, not
  `"step 2"` — and wrap the scenario's work in steps: an assertion outside any step is
  attributed to none, and a screenshot taken inside one is embedded under it;
- phrase an assertion label as the claim it proves — `"the tree lists the two nested
  pages"`, not `"check count"`;
- **always pass `actual=`** — an assertion with no observed value is a claim nobody can check,
  and the report lists it under `## Warnings`;
- put in `covers=` exactly the ids *this* assertion proves, one assertion per claim, so a
  criterion's table holds the assertions that prove it and nothing else.

`ostler qa report --spec <spec-dir>` re-renders the file from the ledger at any time;
`--out-dir LABEL` renders a dry run's to `qa/<LABEL>/report.md`. When the target was
recorded, each step in the report says where it sits in the video, and
`ostler qa frames --spec <spec-dir> --step <step-id>` writes the frames around it to
`qa/frames/<step-id>/` (`--around`, `--fps` widen or thicken the window) — a step phrased as
what a person does is also the step a reviewer can find in the footage.

## Doctrine

- **Every criterion the plan is scoped to is tested. There is no exception.**
  Not "covered by a unit test elsewhere", not "deferred", not "unobservable from here". If a
  criterion is genuinely unprovable through the target, that is a finding to escalate: the
  story is either mis-specified or missing a seam. It is not a line to delete. `validate` fails
  closed on an uncovered criterion precisely so the decision reaches a human.
- **Prove it live.** The scenario exercises the running product through its real target — the
  HTTP surface, the browser, the device. Asserting that a unit test exists, shelling out to a
  suite, or re-checking a fixture the product never touched is wasted motion: it proves the
  test file, not the behaviour, and the whole reason this plan runs against a live stack is
  that the unit suite already ran and said nothing about integration.
- **Removing an assertion is never a repair.** A failing check is a result. Deleting it,
  loosening it until it cannot fail, or moving its criterion onto a cheaper claim converts a
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
- **Read product data with `qa.field`, never by subscript.** `qa.field(payload, "items.0.id")`
  yields `MISSING` where a key is absent, which satisfies no assertion, so the check goes red
  where it can explain itself. A `.get("items", [])` default converts a broken response into a
  scenario that passes over nothing. `ostler qa lint` rejects a named-key subscript anywhere in
  the plan.
- **Assert on what the behaviour produced, not on an exit code.** A process exiting zero is the
  same evidence a suite that skipped every case produces. When a scenario shells out to a test
  runner, name the case (`-run TestPublishAuthor`, `-k test_publish_author`) and pass the flag
  that defeats the result cache (`go test -count=1`, `gradle --rerun-tasks`) — a cached replay
  prints the same words a real run does, and its cache key does not track the environment
  variables that decide which service was actually tested.
- **A browser scenario asserts on `qa.diagnostics`.** The diagnostics *file*
  (`qa/traces/<scenario>-diagnostics.json`, `schema: browser-diagnostics/3`) is written after
  the scenario has returned its verdict, so only the post-run audit reads it. For the scenario
  to fail *itself* on a 5xx or an uncaught exception, it asserts on the live accessors.
  `failed_requests()` already excludes `net::ERR_ABORTED` — exclude by *reason* like that, never
  by count, since "allow one failure" tolerates a refused connection too.
  Capture is at the browser context, so a service worker's own requests are recorded too, each
  with `initiator` (`page` or `worker`). The readers default to page-initiated exchanges and
  take `initiator=None` for all.
- **Assert on what the app actually sent and received, not on a re-issued request.** The
  records carry `requestHeaders`, `requestBody`, `responseHeaders` and — for a text body —
  `responseBody`, so a claim about the payload the *page* got is written against that payload
  rather than against a second call `qa.http` made with different cookies. Console entries
  carry `args`, the arguments as values, where `text` is only the `{items: Array(3), …}` line
  DevTools prints.
- **Read `bodyOmitted` before asserting a body is absent.** A record with no `responseBody`
  always carries `bodyOmitted` saying why — `binary`, a redirect, `scenario body budget
  exhausted`, `request did not complete`, `still in flight when the scenario ended`. An
  uncaptured body and an empty one read alike, so `"SQLSTATE" not in r.get("responseBody", "")`
  passes on a body nobody kept. Declared secrets and credential headers are already redacted in
  these records, so an assertion about a token's *presence* reads the header name, not its value.
- **Generate a shared value inside one scenario**, not at module scope. Module-level randomness
  or `time.time()` is a module-level side effect, and it re-evaluates on every describe.

## Running one scenario

```bash
ostler qa validate <spec_dir>/qa_plan.py --spec <spec_dir> --json
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> --json
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> --scenario <scenario-id> --out-dir LABEL
```

`--out-dir` takes a **label** — one name, no slashes — and resolves it to
`<spec_dir>/qa/LABEL/`. Two things follow. A rehearsal stays out of the *scored* ledger, whose
files the evidence gate names exactly (`qa/qa-run.ndjson`, `qa/run-manifest.json`), so a
scenario tuned until it passed cannot leave its own proof. And it stays inside `qa/`, the one
directory a repo ignores: the sibling roots this replaces — `qa-dry-run/`, `qa-fix-*/`,
`qa-operator-*/` — were committed by the hundred of megabytes. `ostler qa clean --spec <dir>`
lists what an old layout already left behind, and removes it with `--yes`.

The scored ledger is what you get by *omitting* the flag; `qa`, `steps`, `asserts`, `traces`,
`videos` and `screenshots` are refused as labels, because the scored run owns those names.
