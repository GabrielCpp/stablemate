---
agent: agent
---

# Plan QA For A {{ repo.name | title }} Story

Author the complete, machine-executable QA plan for one reviewed story. Do not execute
QA. Ostler is the only primary executor for command, browser, and mobile scenarios.

## Time budget — {{ node_timeout_min }} minutes

This turn is stopped at its budget ("unbounded" = no cap). What survives is **the file on
disk**, not this turn's reply, so work in an order that leaves a usable draft at every
moment:

- Write `<spec_dir>/qa_plan.py` **incrementally**. Get a small, importable plan onto disk
  first, then add scenarios to it. A file that imports and covers the story's central
  claim is worth more than a larger one that was cut off mid-write.
- Size the scenario set to the budget rather than discovering it. If the acceptance
  criteria imply more scenarios than fit, cover each criterion once and stop; the run,
  the assessment and the audit all stand downstream of you and will name what is missing.
- A plan that is stopped short is repaired from where it stands, not re-authored — so
  every minute you spend on a draft that lands is kept.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`
- Context status: `{{ workhorse_var('context_status') }}`
{% if qa_stack %}- The stack that is **already up** for you{% if qa_stack.profile %}, profile `{{ qa_stack.profile }}`{% endif %}:
{% if qa_stack.fixtures %}  - fixtures already loaded — assert against **these**, do not re-derive a path:
{% for f in qa_stack.fixtures %}    - `{{ f }}`
{% endfor %}{% endif %}{% if qa_stack.capable_of_rendering %}  - what it can render: {{ qa_stack.capable_of_rendering }}
{% endif %}{% endif %}{% if shared_packages %}- Shared files this story's services both read, resolved by the implementation plan:
{% for p in shared_packages %}  - `{{ p }}`
{% endfor %}{% endif %}{% if qa_only_scenarios %}- Scenarios the implementation plan marked **QA-only** — no automated test was written for
  any of these, so each one is an obligation of *this* plan and nothing else in the run
  covers it. Every one of them must appear below as an obligation with its own `verify:`
  check; dropping one silently leaves its acceptance criterion unverified:
{% for s in qa_only_scenarios %}  - {{ s.title }} — AC {{ s.ac or 'none stated' }} ({{ s.level }})
{% endfor %}{% endif %}
{% if workhorse_var('context_notes') %}- Context diagnostics: `{{ workhorse_var('context_notes') }}`
{% endif %}{% if workhorse_var('plan_validation_notes') %}- Previous plan validation diagnostics: `{{ workhorse_var('plan_validation_notes') }}`
{% endif %}{% if workhorse_var('run_assessment_notes') %}- Previous execution-assessment diagnostics: `{{ workhorse_var('run_assessment_notes') }}`
{% endif %}{% if workhorse_var('audit_notes') %}- Previous independent-audit diagnostics: `{{ workhorse_var('audit_notes') }}`
{% endif %}{% if workhorse_var('evidence_notes') %}- Previous deterministic evidence diagnostics: `{{ workhorse_var('evidence_notes') }}`
{% endif %}
A diagnostics line appears only when that gate actually reported something to fix, so **no
diagnostics lines at all means no gate has complained** — author the plan fresh rather than
hunting for the finding that is missing from this brief.

Do not rediscover or substitute another story. If a gate did route back here, repair the existing
plan from its specific diagnostics instead of discarding valid scenarios. Newer semantic,
assessment, audit, or evidence findings are not superseded by an earlier structurally valid result.

## Required Inputs

Read all of:

- the story and its acceptance criteria;
- the OKF impact packet, through `ostler qa context-show` rather than by reading it whole —
  the closure is deliberately broad, so on a large book the packet runs to hundreds of
  kilobytes and a plain read of it truncates. Start with what you owe:

  ```bash
  ostler qa context-show --spec <spec_dir> --required
  ostler qa context-show --spec <spec_dir> --required --ids-only   # just the ids, for `covers`
  ostler qa context-show --spec <spec_dir> --context-only --node <surface>  # the rest, in slices
  ```

  `--node` matches a substring of the node path, `--kind` an exact obligation kind, and
  `--offset`/`--limit` page a long section. `--json` emits the same slice as records. The
  built files — `<spec_dir>/qa-okf-context.json`, the machine-readable impact authority, and
  `<spec_dir>/qa-okf-context.md`, its rendering — remain beside the spec for a targeted look;
- the implementation plans, review results, and applicable QA skills;
{% if plan_services %}
{{ plan_services }}
{% endif %}
- `docs/qa/lessons.md`, when present; and
- static inputs under `<spec_dir>/qa-inputs/`, when present.

The verification contract is the union of story acceptance criteria and every required
OKF obligation. Include impacted contract and journey completion conditions, consistency
groups, persistence, producer-to-consumer events, concurrency, and idempotency. Never
drop an obligation because it is inconvenient or because a nearby assertion looks
similar.

Acceptance criteria that use universal language — `every`, `all`, `throughout`, `any
other`, `each`, `whole app`, or a parenthesized category list — must be turned into an
explicit coverage inventory before you write scenarios. List every named category in
`qa-plan.md`, map each category to a scenario assertion or to an executable fixture case,
and do not mark the AC covered until every row has terminal evidence. A representative
sample is evidence for only the category it actually exercises; it is not evidence for
the unvisited remainder of a universal AC.

For document/PDF/print stories, universal evidence is content-shaped, not artifact-shaped:

- "every word" means derive a complete normalized source-text inventory and compare it with
  each produced output's text/OCR inventory, with only named browser headers/footers excluded;
- "every heading" means include the reader/page H1 and every generated subsection heading in
  the adjacency/page-break assertions;
- "inspect by eye", "visual inspection", or equivalent wording means record a terminal
  artifact-backed visual-review assertion with explicit accept/reject criteria for clipping,
  chrome leakage, page breaks, blank pages, and print fidelity. Producing PDFs, screenshots,
  rasters, or a manifest is setup for that observation; it is not the observation itself.

## Required Outputs

Write both files directly under the spec directory:

1. `qa_plan.py`, mandatory for every surface and every run.
2. `qa-plan.md`, the reviewable rationale and AC/obligation-to-scenario map. Create it through
   `ostler` first — `timeout 30 ostler create spec <story-name> qa-plan.md`, where `<story-name>`
   is the folder name of the spec directory — which stamps its `type: spec.qa-plan` frontmatter.
   Write the structure below **underneath that `---` block, leaving it in place** — a doc with no
   `type:` is an `okf-missing-type` error against the graph.

There is no UI/mobile escape from the plan module. Playwright and Maestro are drivers a
target selects, not agent-operated alternatives. Command/API verification uses the same
plan. Inputs required before execution belong in `qa-inputs/`; nothing required to start
a run may live under disposable `qa/`.

## Python Contract

A plan is a **Python module**, and each scenario is a function ostler executes under the
project's own interpreter. This is why the format changed: a wrong key raises on the line
that read it, a wrong type raises, and the traceback names both. The `jq` filter that read
a missing field as an empty stream — and passed — has no equivalent here.

```python
import json

from ostler_qa import Qa, background, plan, scenario, secret, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python", base_url="http://localhost:8090")
web = target("web", driver="playwright", base_url="http://localhost:3000", browser="chromium",
             recording={"required": True, "mode": "window"})
mobile = target("mobile", driver="maestro", app_id="com.example.app",
                recording={"required": True, "mode": "device"})

background("api-server", cmd="cd api && go run ./cmd/server", timeout=60,
           ready_cmd="curl -sf http://localhost:8090/healthz", ready_contains="ok")
ADMIN = secret("ADMIN_TOKEN", from_env="QA_ADMIN_TOKEN")


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

Only declare targets the story needs. Every scenario has a target, a mechanism, an explicit
objective (its **docstring**), asserted causal preconditions, observable checkpoints,
`covers`, and at least one `qa.check`. `mechanism` is provenance (`live` — drive the running product — or `fixture` — drive it
from a canned input). There is no third: a test suite standing in for the product is not
evidence about the product. `driver` is execution (`python`,
`playwright`, or `maestro`). Never use a driver name as a mechanism. A scenario's id is its function name with underscores turned into
dashes, so the function name is the id — no separate uniqueness bookkeeping to get wrong.

### What the module may do

- **Module level is declarations only.** `ostler qa validate` imports the module to read the
  plan without running it, so a request, a subprocess or a file write at module scope turns
  every validation into a run. Put all of it inside scenario functions.
- **Do not defend against a wrong key.** `payload["items"][0]["id"]` is the correct spelling;
  `payload.get("items", [])` converts a broken response into a scenario that passes over
  nothing. Let it raise — the traceback is the finding, and it names the line.
- Everything a scenario needs is on `qa`, already resolved. `qa.dir` is **the** evidence
  directory (this run's, including a dry run's `--out-dir`), `qa.root` the repo root,
  `qa.spec_dir` the spec directory. Never rebuild any of them from a literal path.
- Ordinary Python is available: `subprocess.run` for a CLI, the project's own client library,
  a helper module beside the plan in the spec directory. Prefer `qa.http` for HTTP — it is
  bound to the target's `base_url` and raises `HttpError` on any status outside
  `expect_status=`, which is the `curl -fsS` behaviour every shell plan had to remember.
- A value used by two scenarios is generated **inside one scenario** and asserted there.
  Module-level randomness or `time.time()` is a module-level side effect; a helper function
  the scenario calls is not.

### The `qa` object

| call | what it does |
| --- | --- |
| `qa.check(label, condition, actual=…, expected=…, covers=…)` | record one claim; returns the verdict, never raises |
| `qa.require(label, condition, …)` | record one claim and stop the scenario if it fails |
| `qa.verify(check, observed, covers=…, **args)` | make an observation the book *declared*; ostler owns the comparison |
| `with qa.step("label"):` | group a phase under a named step in the ledger |
| `qa.capture(key, value)` / `qa.get(key)` | publish a value into the ledger and read it back |
| `qa.artifact(path, kind="…")` | register a file as evidence; a relative path resolves inside `qa.dir` |
| `qa.secret("NAME")` | a declared secret's value, redacted from the ledger |
| `qa.http.get/post/put/patch/delete(path, json_body=…, headers=…, expect_status=…)` | HTTP against the target's `base_url` |
| `qa.goto(url)`, `qa.by_role/by_label/by_test_id/by_text/by_css`, `qa.screenshot(name)`, `qa.page` | the browser, for a `playwright` target |
| `qa.vet("docs/…/screen.md", name="loaded")` | photograph the screen and register what rendered against where the book places it |
| `qa.diagnostics.console_errors/page_errors/failed_requests/responses()` | the live console and network record for that page |
| `qa.diagnostics.layout()` | where the page put its content: the viewport, and each region's box as a share of it |
| `qa.maestro.flow([...])` / `qa.maestro.run(flow)` | build and run a Maestro flow; the result is yours to assert on |

### QA tools

`{{ repo.name }}` has opted the following tools into `agents.yml`, resolved for this host
(`ostler qa tools list`):

{% if qa_tools %}
| tool | command | on this host |
| --- | --- | --- |
{% for tool in qa_tools -%}
| `{{ tool.name }}` | `{{ tool.command }}` | {{ "available" if tool.available else "NOT on PATH" }} |
{% endfor %}
{%- else %}
None. This repo's `agents.yml` declares no `qa: {tools: [...]}` opt-in.
{% endif %}

`qa.tesseract.ocr(image)` and `qa.convert.resize(image, width, height)` are typed wrappers over
the two built-ins; call anything else opted in above with `qa.tool("name").run(*args)`. A tool
not in this table is not reachable — `qa.tool("whatever")` raises before it runs anything.

**There is no other way to shell out.** `ostler qa lint` statically allowlists the plan's AST
before it is ever imported: `subprocess`, `os.system`, `os.popen`, and any other module not on
that allowlist fail lint, whether or not the command they would have run is one of the tools
above. A tool this story needs and that is missing from the table is a gap in this repo's
`agents.yml` opt-in (or the host's `~/.config/stablemate/config.toml` if it is not a built-in),
not something to route around with a raw call.

`qa.verify` is `qa.check`'s stronger sibling and the one to reach for whenever the obligation
declares a check — see "Implement Each Obligation's Declared Checks" below. Everything true of
`qa.check`'s ledger record is true of it.

`qa.check` is the one piece of ceremony that is not optional: `qa-evidence.json` is built by
aggregating assert records over what each one `covers`, so a bare `assert` proves nothing to
the gate. A scenario that claims coverage and records no assertion fails — at validation, from
a static count of the `qa.check`/`qa.require` calls in its body, and again at runtime.

- **Wait for the thing you are about to read.** `.count()`, `.get_attribute()`,
  `.inner_text()`, `.is_visible()` and `qa.page.evaluate()` sample the page **once**, at
  whatever instant Python reached the line — none of them retry. Against a UI still resolving
  a fetch, a re-render or a transition that is a race, and a race fails in the exact shape of
  a product defect: intermittently, with a plausible actual value. That is expensive, because
  it buys a repair lap spent on the wrong hypothesis before anyone notices the plan was the
  problem. Await the specific locator first — `badge.wait_for(state="visible")` — and then
  read it. A wait for something *else* does not count: `qa.page.wait_for_url("**/editor/*")`
  waits for the navigation, not for the badge the next line samples, and a badge rendered two
  frames later still reads as absent. A state that is transient by nature — a spinner between
  two fast round trips — is not made observable by sampling faster: hold the transition (block
  the response, throttle the route) or assert on the durable thing it leaves behind.
- **Vet every documented state a UI scenario reaches — this is not optional.** A scenario on a
  `playwright` or `maestro` target that never calls `qa.vet` is rejected at validation, before
  anything runs, and fails again at runtime if it slipped through. `qa.vet(screen, name=…)`
  takes the screenshot, scans the rendered regions, and registers each one against the
  `placement:` its component carries in the book — a component that landed outside its
  documented band becomes an ordinary failed assertion quoting the measured share, so the fix
  loop repairs it inside the story. The screen argument is a **literal** path to a document
  this story's OKF packet names; a computed path is rejected, because a path assembled at run
  time cannot be checked before the run. Without `components=`, `qa.vet` checks every
  documented component on that screen; use that only for a state that should render all of
  them. For fixture variants, tab states, loading/empty/error states, or any other mutually
  exclusive state, pass `components=["component-id", ...]` naming only the components actually
  present in that screenshot.
- **Screenshot every documented state a browser scenario reaches.** `qa.screenshot(name)` also
  writes a `.layout.json` beside the image — `ostler vet`'s DOM scan of that instant — and the
  audit reads it to judge whether the page is laid out at all. Without it the audit has only
  your assertions, and an assertion cannot tell a correct page from one rendered as a narrow
  column against the margin: `by_role` finds an element in the accessibility tree either way.
  When the obligation is itself about placement, assert on it with `qa.diagnostics.layout()`
  rather than leaving it to the audit.
- **Do not invent CLI flags, REST routes, or output shapes.** Check the tool's `--help`, its
  source, or the layer's `qa_skill` — do not guess by analogy with a similar-looking tool.
- **Defeat the test runner's result cache.** A build-cached runner replays a previous PASS
  without executing anything, and prints it in the same words a real run does — `go test`'s
  `ok ... (cached)`, gradle's `UP-TO-DATE`, a `--only-changed` watcher's skip. Asserting on
  `"--- PASS" in output` cannot tell the replay from the run, so the scenario goes green while
  the code under test is never touched; worse, the cache key does not track environment
  variables, so a step that reads one (an emulator host, a base URL) replays a result recorded
  against a *different* service. Pass the flag that forces execution — `go test -count=1`,
  `gradle --rerun-tasks` — on every test invocation a scenario's evidence depends on.
- When a scenario shells out, assert on **what the command printed about the behaviour** —
  the value, the count, the status — not on `returncode == 0`. A process exiting zero is the
  same evidence a suite that skipped every case produces.
- Browser diagnostics: `qa.diagnostics` is the live console and network record, and it is the
  only way a scenario can fail *itself* on what the page did. `console_errors()` is the
  `error`-level messages; `page_errors()` is uncaught exceptions, a **different** event that
  appears in nothing else; `responses(status_at_least=500)` is the server-error gate;
  `failed_requests()` is requests that never completed, already excluding the
  `net::ERR_ABORTED` an app fires when it cancels its own fetch — exclude by *reason* like
  that, never by count, since "allow one failure" tolerates a refused connection too. The
  same records are written to `qa/traces/<scenario>-diagnostics.json` when the scenario ends
  (`schema: browser-diagnostics/2`), for the post-run audit; every record carries `atMs`, the
  run-relative offset, so console and network can be read against each other.
- The records are the DevTools panels, not a summary of them: `console(level=…, contains=…)`
  is every message with its arguments as **values** (`args`), where `text` is only the
  `{items: Array(3), …}` line DevTools prints; `requests(url_contains=…)` and
  `responses(status_at_least=…, url_contains=…)` carry `requestHeaders`, `requestBody`,
  `responseHeaders`, `responseBody` and `durationMs`. Assert on what the *page* sent and
  received rather than re-issuing the call through `qa.http`, which goes out with different
  cookies and proves a different thing. A record with no `responseBody` always carries
  `bodyOmitted` saying why (binary, a redirect, budget exhausted, still in flight) — read it
  before asserting absence, since an uncaptured body and an empty one read alike. Secrets and
  credential header values are already redacted, with the header name kept.
- Background daemons are declared with `background(...)` — the runner starts and stops them,
  and the scenario must not. It is for **foreground in-QA services** scoped to the run (a dev
  server pinned to branch source, an event tail). The **heavyweight stack** (docker compose,
  emulators, the DB + baseline seed) is NOT declared here — it is owned by the workflow's
  `ensure_stack` step via the repo's `qa-stack.yml` manifest, brought up before the plan runs
  and left up for reuse. Assume it is already serving.
- Readiness is the runner's to poll, not the scenario's: give `background` either
  `ready_url=` (fetched, must answer HTTP 200 — only when the service really has a `GET` that
  does) or `ready_cmd=` with `ready_contains=` (ready when the command exits 0 and its stdout
  contains the needle). A service whose only route is a `POST` has no 200-answering URL and
  needs the second form. `timeout=` is in seconds, default 30.
- Files a scenario writes go under `qa.dir` — `qa.artifact("steps/x.json", kind="json")`
  creates the parents and registers it as evidence in one call. Do not spell
  `{{ workhorse_var('qa_dir') }}` out by hand: a pinned path writes into the scored ledger
  even when the run was pointed somewhere else, so a dry run leaves its own proof where the
  evidence gate reads it.
- Declare a static fixture with `input_file("name", "qa-inputs/thing.json")`; validation
  checks it exists and lives outside disposable `qa/`.

**Every Playwright locator and every URL comes from the book, not from the running page and
not from your memory of it.** `ostler qa validate` enforces this statically and will reject
the plan — it is a gate, not a preference. The packet carries what you need on the
obligation itself:

- A `locators` object on an obligation holds that node's own `selector`, `role`, `name`,
  `keyboard`, `route`, `entry` and `params` bullets. Address the element by `role` + `name`
  (`qa.by_role("alert", name=…)`); use `qa.by_css` only when the node states a `selector`; fall back
  to a text locator only when the node documents neither, and say so in the scenario.
- A node's documented `role` is the *intended* semantic, not a guarantee of what the target
  engine's accessibility tree actually computes for that markup. Native disclosure elements
  (`<summary>` inside `<details>`) are the known case: several engines expose the summary as
  `group`, not `button`, so a `role: button` locator against it times out with zero matches
  even though the element renders correctly. When the node's underlying element is a native
  `<summary>`/`<details>` pair, use its `selector` (or a CSS locator scoped to a stable class
  or `:has-text(...)`) instead of `role`+`name`, and say so in the scenario — don't spend a
  repair cycle rediscovering this at review time.
- Playwright locators are strict-mode: `.is_visible()` **throws** (it does not return
  `False`) when the locator resolves to more than one element, even if every match is
  legitimately present and visible — so the scenario dies with a strict-mode violation, not
  a failed check. Before asserting visibility, check whether the book or the fixture implies
  more than one match is possible; if so, scope the locator narrower (a parent container,
  `:first-child`/`:nth-child`) or assert `.count()` at the expected number instead.
- A text locator invented by reading the implementation — or guessed from a rendered string —
  is a defect, not a shortcut. It is the thing that breaks on the next copy edit, and it is
  why a plan that "passed" proves nothing about the accessible name the book requires.
- Navigate to the `route` the screen documents, entering by its `entry` path and supplying
  its `params`. Never compose a URL the book does not state.

Build Maestro flows with `qa.maestro.flow([...])` and run them with `qa.maestro.run(...)`.
Advanced cases may point to committed native Playwright tests or Maestro flows, but Ostler
still owns invocation, timeout, cleanup, artifacts, recordings, and verdicts. Declare
services/background processes with `background(...)`; do not start them here.

Each AC and required OKF obligation must resolve in `covers` and have an executable
assertion. A source check, unit test, build, or narrative is not behavioral evidence.
An obligation marked `"required": false` — the ones `--context-only` selects, rendered under
`## Context — reached by closure, not owed evidence` —
names something this story neither built nor touched — an endpoint with no implementation
behind it, a screen no change reached. Read it for context; do not write a scenario against
it, and do not invent a route to reach it.
Stateful behavior must exercise action, persistence, reload/re-query, and isolation.
Contract consumers must use a real producer when the repository declares one.

## Markdown Contract

`qa-plan.md` must explain:

- preflight, targets, fixtures, credentials by symbolic reference, and health checks;
- one section per acceptance criterion in story order;
- one section listing every OKF obligation from the context packet;
- scenario and assertion coverage for each AC/obligation;
- each scenario's objective, causal preconditions, intermediate checkpoints, forbidden bypasses,
  and terminal proof;
- expected observable result and evidence type; and
- why omitted optional journeys are outside impact.

**State and verify the bug's causal precondition explicitly — never just assume it from fixture
construction.** Most bugs reproduce only under a specific shared condition named or implied by the
story (the same location/room, the same session, the same tenant, the same parent record). When a
fixture-discovery step picks the entities the AC will exercise, that precondition is often true
only because of _how the query happened to be built_ (e.g. scoped to one partition key) — which is
easy to get subtly wrong without anyone noticing. Don't let it stay implicit: capture the shared
value itself (not just the entity IDs) in the discovery step's own evidence output, and state in
the AC's action/pass-rule that this precondition was confirmed, not assumed. A runbook that never
surfaces this check can pass while accidentally testing two entities that don't actually share the
condition the bug depends on — which proves nothing about the bug.

Use the OKF graph as a cross-layer test specification, not as a list of titles:

- Start every impacted `flow` at its documented `start`; do not deep-link past navigation or
  setup that can expose integration failures. Assert its documented `end` and fail on any
  unexpected 5xx, crash, or browser console error during the journey.
- Exercise every emitted obligation for `when`, `does`, `states`, `keyboard`, status/error/auth,
  return/raise, and field semantics. Include happy, negative, retry, reload, role, locale, and
  accessibility cases when those requirements appear in the packet.
- Traverse linked contracts across the actual producer and consumer. A controller mock does not
  prove a pooled-session, persistence, wire-format, or rendered-consumer obligation.
- Treat `verificationRefs` — the tests the impacted nodes' `tests:` bullets cite — as leads, not
  proof. Determine whether each reference is unit, integration, mocked UI, or real-stack journey
  and whether its suite runs by default. An excluded or manually invoked test cannot stand in for
  live evidence or a default regression gate. What the book declares as *proof* is its
  `checksDeclared`, below; a `tests:` citation is provenance.
- For each scenario with `covers`, capture at least one runner-owned artifact that demonstrates
  the asserted result. A passing exit code with no criterion-specific artifact is insufficient.

A green test suite alone never decides a pass. The observable behavior and runner-owned evidence
are the oracle. Do not put verdicts in the plan or write under `qa/`.

## Implement Each Obligation's Declared Checks

`covers=` is a claim that this scenario *proves* those ids, and the book already says what
proving them looks like. Every obligation row carries `checksDeclared`: the observations the
node's `verify:` bullets declare, each with a `name`, its `args`, and the canonical `call`
text. **That list is your worklist, not a hint.** For each id a scenario claims, invoke every
check it declares:

```python
qa.verify("http_status", response, code=409, title="Manifest Conflict", covers=[OBLIGATION])
qa.verify("unchanged", (before, after), subject="manifest", covers=[OBLIGATION])
```

`ostler qa validate` refuses a plan whose claimed obligation has a declared call no scenario
invokes, and the check's comparison is ostler's rather than yours — which is the point.
`qa.check` takes an already-collapsed bool, so a scenario can decide weakly what "the manifest
is unchanged" means; `qa.verify` cannot, because the assertion *is* the claim.

The declared arguments are part of the contract. Do not rewrite them to match the shape you
happen to captured. Shape the observed value instead: if the declaration says
`json_path(path="$.blocks", ...)`, pass the object whose root has `blocks`, not a wrapper that
forces `path="$.tree.blocks"`. One `qa.verify` can list every sibling obligation that declares
the same call in `covers=`; do that instead of writing near-identical assertions per id.

**The ids in `covers=` must be literal strings** — a module-level constant holding one literal,
or the literal itself. The binding is recovered statically, before anything runs, so an id
assembled from a loop variable, an f-string, or a lookup binds to nothing and the plan is
rejected. The same goes for the check name.

An obligation whose row has no `checksDeclared` is one the book never declared an observation
for. Cover it with `qa.check`/`qa.require` as before, and say in `qa-plan.md` that the
obligation carries no declaration — that is a documentation gap someone else repairs, and
naming it is how it gets seen.

Beyond the declared calls, the claim still has to be earned. A scenario whose only assertion
is a runner's exit banner — `result.returncode == 0`, any bare `EXIT:0` — proves the suite is
green; it proves nothing about the behaviour the obligation names, and it is indistinguishable
from a suite that skipped every case. Assert something the command **prints about the
behaviour itself** — the value, the count, the status — or drive the surface and assert on what
it shows.

## Dry-Run Every Scenario You Write

The stack is up **before** this turn, precisely so you can find out whether what you wrote
resolves. After authoring a scenario, execute it on its own:

```bash
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> \
  --scenario <scenario-id> --out-dir <scenario-id>
```
`--out-dir` takes a **label**, not a path — one name, no slashes. It lands the run in
`{{ workhorse_var('qa_scratch_dir') }}/<scenario-id>/`, inside the directory the repo already
ignores, so no rehearsal is ever committed. One label per scenario, named after it: the runner
deletes its out-dir at the start of every run, so a shared scratch directory keeps only the
last scenario's evidence. The scored ledger is what you get by *omitting* the flag, and its
own files — `{{ workhorse_var('qa_dir') }}/qa-run.ndjson` and `run-manifest.json` — are what
the evidence gate reads, so a scenario tuned until it passed cannot leave its own proof. Fix what does not resolve and run it again. This is what one call answers and no
amount of re-reading does: a locator that matches zero elements, a straight `'` where the
fixture has `’`, a password constant that disagrees with the seed script, a key that is not in
the response the service actually returns. Each of those otherwise costs a full workflow lap —
and each now arrives as a traceback naming the line, not as a scenario that quietly passed.

You may repair **runner tooling** to make a dry run executable: the ostler venv and its
dependencies, harness wiring, fixture plumbing, a missing browser binary. Say what you repaired
in `notes`. You may **not** touch product code — a scenario that fails because the product is
wrong is the finding, and the fix loop owns it. Write the scenario so it fails honestly and say
so in `qa-plan.md`.

Do not validate the *plan* yourself, by any other route: not `ostler qa validate`, not a whole-plan
`ostler qa run`, and not by importing `ostler.qa` from Python. A workflow script node validates it
the moment you return and hands you its diagnostics if it fails, so a self-check can only repeat a
verdict that is one call away. The Python route is named explicitly because forbidding the commands
alone left it open, and a run took it: four Bash turns rediscovering `load_plan`'s signature, inside
a turn that spent ten minutes and a quarter of the run's whole wall-clock budget arriving where the
node arrived immediately afterwards.

## Output

Return JSON only:

```json
{
  "status": "done",
  "notes": "Wrote qa_plan.py and qa-plan.md with complete AC and OKF coverage.",
  "repaired_scenarios": []
}
```

`repaired_scenarios` belongs to the *repair* turn, which names the scenarios it changed so a
gate can check each one was dry-run green. This turn wrote the file, so leave it empty.

### When the plan cannot be written at all

Return `{"status": "blocked", ...}` instead, and **only** when no plan this stage could write
would be a real test of the story: the acceptance criteria name a surface, device, service or
credential that does not exist to drive, the story's criteria contradict each other or the code
so that no scenario can assert either reading, or the coverage demanded lives in a repo you were
not given. A hard planning problem is not a blocked one — a scenario that is awkward to express
still gets written. A `blocked` turn hands the story to an operator, so `notes` must name the
specific dependency and say what you attempted before concluding it. Do **not** write a plan of
scenarios you know cannot run and report `done`: a plan that dry-runs green by asserting nothing
is worse than no plan, because the run continues on it.
