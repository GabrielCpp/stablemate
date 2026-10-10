## The plan contract

Hand this section to the planner, and to every seat that edits the plan. The checks after
your turn enforce it.

### What to read

- The story and its acceptance criteria.
- The OKF impact packet, through `ostler qa context-show` and not by reading it whole. On a
  large book the packet runs to hundreds of kilobytes, and a plain read truncates. Start with
  what the story owes:

  ```bash
  ostler qa context-show --spec <spec_dir> --required
  ostler qa context-show --spec <spec_dir> --required --ids-only
  ostler qa context-show --spec <spec_dir> --context-only --node <surface>
  ```

  `--node` matches a substring of the node path, `--kind` an exact obligation kind, and
  `--offset`/`--limit` page a long section. `--json` emits the same slice as records.
  `<spec_dir>/qa-okf-context.json` is the impact authority, and `qa-okf-context.md` renders
  it.
- The implementation plans, the review results and the QA skills this repo installs.
- `docs/qa/lessons.md` and `<spec_dir>/qa-inputs/`, when present.

The verification contract is the union of the story's acceptance criteria and every required
OKF obligation. That covers journey completion, consistency groups, persistence,
producer-to-consumer events, concurrency and idempotency. Never drop an obligation because it
is inconvenient or because a nearby assertion looks similar.

An acceptance criterion in universal language (`every`, `all`, `throughout`, `any other`,
`each`, `whole app`, or a parenthesized category list) needs a coverage inventory first. List
every named category in `qa-plan.md` and map each one to an assertion or a fixture case. A
representative sample proves only the category it exercises. For a document, PDF or print
story, "every word" means a complete normalized text inventory compared against each output,
"every heading" includes the page H1 and each generated subsection heading, and "inspect by
eye" means an artifact-backed visual assertion with explicit accept and reject criteria.
Producing the PDF is setup for that observation, not the observation.

### The two files

Write both directly under the spec dir:

1. `qa_plan.py`, mandatory for every surface and every run.
2. `qa-plan.md`, the rationale and the AC/obligation-to-scenario map. Create it with
   `timeout 30 ostler create spec <story-name> qa-plan.md`, where `<story-name>` is the spec
   dir's folder name. That stamps the `type: spec.qa-plan` frontmatter. Write below the `---`
   block and leave it in place.

There is no UI or mobile escape from the plan module. Playwright and Maestro are drivers a
target selects, not tools an agent operates instead. Inputs a run needs before it starts
belong in `qa-inputs/`, never under the disposable `qa/`.

### The module

A plan is a Python module, and each scenario is a function ostler executes under the
project's own interpreter. A wrong key raises on the line that read it, and the traceback
names it.

```python
import json

from ostler_qa import Qa, background, plan, scenario, secret, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python", base_url="http://localhost:8090")
web = target("web", driver="playwright", base_url="http://localhost:3000", browser="chromium",
             recording={"required": True, "mode": "window"})
mobile = target("mobile", driver="maestro", app_id="com.example.app",
                recording={"required": True, "mode": "device"})

background("api-server", cmd="<this repo's own command to start the service>", timeout=60,
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
             qa.field(stored, "metadata.author") == uid,
             actual=qa.field(stored, "metadata.author"), expected=uid)
    qa.check("message is verbatim", qa.field(stored, "metadata.message") == "hello",
             actual=qa.field(stored, "metadata.message"), expected="hello")
    json.dump(stored, qa.artifact("steps/publish-stored.json", kind="json").open("w"))
```

Declare only the targets the story needs. Every scenario has a target, a mechanism, an
objective (its docstring), preconditions, checkpoints, `covers`, and at least one `qa.check`.
`mechanism` is provenance: `live` drives the running product, and `fixture` drives it from a
canned input. A test suite standing in for the product is not evidence about the product.
`driver` is execution: `python`, `playwright` or `maestro`. A scenario's id is its function
name with underscores turned into dashes.

- **`preconditions`** state what must already be true for the observation to mean anything,
  as a fact about the product, not as the calls that produced it.
- **`checkpoints`** state what an observer would see the scenario prove, in order. Each one
  has an assertion behind it.
- **`forbid`** names the weaker or wrong behaviour this scenario must be able to catch: the
  cheaper implementation that would satisfy your checkpoints if you were careless.

### Arrange so that a violation would show

Choose the setup state so that every `forbid` entry would change something you observe. Ask
it of each entry: if the product did this instead, which value in my arrangement would come
back different? When the answer is "none", the arrangement is wrong, not the assertion. The
example posts `author: "attacker"` so a product that took the body's author shows a different
value.

A write that must leave its neighbours alone shows this most clearly. A release endpoint must
free one held seat and touch nothing else. Reset the showing, hold `A1`, release it, and
compare: every other seat was already free at version 0, so a product that rebuilds the map
empty passes. Book `B2`, hold `C3` and bump `E5`'s version first, and the same comparison
goes red. Give every entity the assertion ranges over a distinct value on the field the
forbidden behaviour would flatten.

When the declared fixtures and the documented operations cannot reach a state in which a
`forbid` entry would show, name the missing arrangement and the behaviour it would catch in
`qa-plan.md` under that obligation, and repeat it in `notes`. Return `blocked` only when that
obligation is the story's central claim and no reachable state discriminates at all.

### What the module may do

- **Module level is declarations only.** `ostler qa validate` imports the module to read the
  plan, so a request, a subprocess or a file write at module scope runs on every validation.
- **Read product data with `qa.field`, never by subscript.** `payload["items"][0]["id"]`
  raises when the product spells the key differently, the scenario aborts, and every
  obligation it covered comes back `unproven`. `qa.field(payload, "items.0.id")` yields
  `MISSING`, which satisfies no assertion, so the check goes red where it can explain itself.
  A `.get("items", [])` default makes a broken response pass. `ostler qa lint` rejects a
  named-key subscript anywhere in the plan, helpers included. Indexing what the plan itself
  built (`rows[0]`, `stderr[-2000:]`) is fine.
- Everything a scenario needs is on `qa`: `qa.dir` is the evidence directory of this run,
  `qa.root` the repo root, `qa.spec_dir` the spec dir. Never rebuild them from a literal path.
- `ostler qa lint` allowlists the plan's AST. There is no `subprocess`, no `os.system`, no
  `pathlib`, and no importing a helper beside the plan. A command runs through
  `qa.tool(name)` for a tool this repo opted into, or `qa.fixture(name)` for a book fixture
  node. Prefer `qa.http` for HTTP: it binds the target's `base_url` and raises `HttpError` on
  any status outside `expect_status=`.
- A value two scenarios use is generated inside one scenario and asserted there.
- **Write for the reader of `qa-report.md`.** The runner renders it from the ledger, one
  section per criterion and per obligation, with the step each assertion ran in, its label,
  and its observed and expected values. Phrase `qa.step("...")` as what a person would do.
  Phrase a label as the claim it proves. Always pass `actual=` to `qa.check`, `qa.require`
  and `qa.eventually`: an assertion with no observed value lands under `## Warnings`. Put in
  `covers=` exactly the ids that assertion proves. Wrap a scenario's work in `qa.step()`
  blocks.

| call | what it does |
| --- | --- |
| `qa.field(data, "a.b.0")` | read observed data along a dotted path; missing yields `MISSING` |
| `qa.check(label, condition, actual=..., expected=..., covers=...)` | record one claim; never raises |
| `qa.require(label, condition, ...)` | record one claim and stop the scenario if it fails |
| `qa.eventually(label, lambda: ..., covers=...)` | a claim the page may arrive at; re-samples until it holds |
| `qa.require_eventually(label, lambda: ..., ...)` | the same, stopping the scenario when it never arrives |
| `qa.verify(check, observed, covers=..., **args)` | an observation the book declared; ostler owns the comparison |
| `with qa.step("label"):` | group a phase under a named step |
| `qa.capture(key, value)` / `qa.get(key)` | publish a value into the ledger and read it back |
| `qa.artifact(path, kind="...")` | register a file as evidence, resolved inside `qa.dir` |
| `qa.secret("NAME")` | a declared secret's value, redacted from the ledger |
| `qa.http.get/post/put/patch/delete(path, json_body=..., headers=..., expect_status=...)` | HTTP against `base_url` |
| `qa.goto(url)`, `qa.by_role/by_label/by_test_id/by_text/by_css`, `qa.screenshot(name)`, `qa.page` | the browser, on a `playwright` target |
| `qa.vet("docs/.../screen.md", name="loaded")` | photograph the screen and check it against the book's placement |
| `qa.diagnostics.console_errors/page_errors/failed_requests/responses()` | the page's live console and network record |
| `qa.diagnostics.layout()` | each region's box as a share of the viewport |
| `qa.maestro.flow([...])` / `qa.maestro.run(flow)` | build and run a Maestro flow |

Anything the page has to reach is `eventually`, and anything later lines depend on is
`require_eventually`. `qa.check` receives a collapsed bool, so hand over a sampler instead.
When a precondition is a plain `eventually` and never arrives, the next line dereferences a
missing locator, the scenario aborts, and every assertion that had passed inside it stops
counting. `require_eventually` stops on purpose and keeps what was proven. If a line reads a
locator that exists only when a check above passed, that check is a `require`.

- **Wait for the element you read.** `.count()`, `.get_attribute()`, `.inner_text()`,
  `.is_visible()` and `qa.page.evaluate()` sample once. Await the specific locator first. A
  wait for a navigation does not wait for the badge the next line samples.
- **Vet every documented state a UI scenario reaches.** Validation rejects a `playwright` or
  `maestro` scenario that never calls `qa.vet`. The screen argument is a literal path to a
  document the packet names. For a mutually exclusive state, pass `components=[...]` naming
  only what that screenshot shows.
- **Screenshot every documented state a browser scenario reaches.** `qa.screenshot(name)`
  writes a `.layout.json` beside it, and the audit reads it to judge whether the page is laid
  out at all.
- **Do not invent CLI flags, routes or output shapes.** Check `--help`, the source or the
  layer's QA skill.
- **Defeat the test runner's result cache.** A cached runner replays an old pass in the same
  words. Pass the runner's flag that forces execution on every invocation the evidence
  depends on.
- When a scenario shells out, assert on what the command printed about the behaviour, not on
  `returncode == 0`.
- `qa.diagnostics` is the only way a scenario fails itself on what the page did.
  `console_errors()` already drops the `/favicon.ico` 404. `page_errors()` is uncaught
  exceptions. `responses(status_at_least=500)` is the server-error gate. `failed_requests()`
  already drops `net::ERR_ABORTED`. Exclude by reason, never by count. Assert on what the page
  sent and received, not on a call re-issued through `qa.http`.
- `background(...)` declares foreground services scoped to the run. The heavyweight stack is
  the runbook's, already up before the plan runs. Give `background` either `ready_url=` or
  `ready_cmd=` with `ready_contains=`. `timeout=` is in seconds.
- Files a scenario writes go under `qa.dir` through `qa.artifact(...)`. Never spell the
  `qa/` path out: a pinned path writes into the scored ledger during a dry run.
- **Arrangement is declared, not improvised.** State two scenarios share is a fixture node in
  the book (`docs/features/<surface>/fixtures/<name>.md`), reached with
  `qa.fixture("name", arg=value)` by its exact name. A static input is
  `input_file("name", "qa-inputs/thing.json")`. State one scenario needs is reached by driving
  the product's documented operations inside a `qa.step`. Writing rows behind the product's
  back is not.
- **Name the fixtures in the story.** Every fixture the plan uses belongs under `## Fixtures`
  in `story.md`, one `- Fixture: <name>` bullet each, or `(none)`:
  `ostler update story <slug> --title ... --covers ... --depends ... --fixtures '<a>, <b>'`.

### Locators and routes come from the book

`ostler qa validate` rejects a locator or a URL the book does not state.

- An obligation's `locators` hold its node's `selector`, `role`, `name`, `keyboard`, `route`,
  `entry` and `params`. Address an element by `role` and `name`. Use `qa.by_css` only for a
  stated `selector`, and a text locator only when the node documents neither.
- A native `<summary>` in `<details>` is exposed as `group` by several engines. Use the
  node's `selector` there.
- Playwright locators are strict: `.is_visible()` throws on more than one match. Scope the
  locator narrower, or assert `.count()`.
- Navigate to the documented `route`, through its `entry`, with its `params`.

Ostler owns invocation, timeouts, cleanup, artifacts, recordings and verdicts, also for a
committed native test a scenario points at.

### Scope

Each AC and required obligation resolves in `covers` with an executable assertion. A source
check, a unit test, a build or a narrative is not behavioural evidence. An obligation marked
`"required": false` is context: write no scenario against it. A `relation-of-required`
obligation shares a record, event or lock with a node the change reached, and it owes only
its shared bullets (`persistence:`, `consistency:`, `concurrency:`, `idempotency:`, `emits:`,
`consumes:`) and its `contract`.

The packet is also the upper bound. The budget is one scenario per coverable id, plus half
as many again for a conflict branch that needs its own run. Validation refuses a plan past
it, and a scenario whose `covers=` names nothing owed. Stateful behaviour exercises action,
persistence, reload and isolation. A contract consumer uses the real producer when the repo
declares one.

### Declared checks

Every obligation row carries `checksDeclared`: the observations its `verify:` bullets
declare. For each id a scenario claims, invoke every declared check:

```python
qa.verify("http_status", response, code=409, title="Manifest Conflict", covers=[OBLIGATION])
qa.verify("unchanged", (before, after), subject="manifest", covers=[OBLIGATION])
```

Validation refuses a claimed obligation with a declared call no scenario invokes. After the
run, `ostler qa sensitivity` perturbs each `qa.verify` observation. A call no perturbation
turns red is insensitive, and a pass there proves the assertion ran, not the product. Keep
each call narrow: name the `subject`, and list in `except_fields` only what the operation may
move. Shape the observed value to the declared arguments, never the reverse. One
`qa.verify` may cover every sibling obligation that declares the same call. The ids in
`covers=` and the check name are literal strings. An obligation with no `checksDeclared` is
covered with `qa.check`, and `qa-plan.md` names it as a book gap.

### What `qa-plan.md` explains

- Preflight, targets, fixtures, credentials by symbolic name, and health checks.
- One section per acceptance criterion in story order, and one listing every obligation.
- Each scenario's objective, preconditions, checkpoints, forbidden bypasses, the arrangement
  detail that makes each bypass observable, and its terminal proof.
- Why an omitted optional journey is outside impact.

State and verify the bug's causal precondition: the shared location, session, tenant or
parent the bug depends on. Capture the shared value itself in the discovery step's evidence.
Start every impacted flow at its documented `start`, assert its documented `end`, and fail on
a 5xx, a crash or a console error on the way. A `tests:` citation in the book is a lead, not
proof. A green suite alone never decides a pass.

### Dry runs

The stack is up, so dry-run each scenario you write or change, on its own:

```bash
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> \
  --scenario <scenario-id> --out-dir <scenario-id>
```

`--out-dir` takes a label, not a path. The run lands in
`<spec_dir>/{{ workhorse_var('qa_scratch_dir') }}/<scenario-id>/`, which the repo ignores.
Use one label per scenario: the runner clears its out-dir on every run. Return the ids you
ran green in `proved_scenarios`. The checks read each one's scratch log, and an id that did
not pass there fails them. Fix what does not resolve and run it again. Runner tooling (the
ostler environment, a browser binary, fixture plumbing) may be repaired. Product code may
not.
