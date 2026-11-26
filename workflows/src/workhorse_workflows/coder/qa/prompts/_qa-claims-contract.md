## The plan contract

This is the contract for `qa_plan.py`, which you write by hand. The checks after your turn
enforce it.

### What you owe

{% if book_services %}Every service of this story has an executable book, and the book's own play judged the
story. The claims listed above are what the books left: the claims no call of a book can
show and the criteria no play observed. They are the whole scope of this plan. Each claim is a criterion named `claim:<n>`, and the plan covers
each one with an executable assertion.{% else %}No service book judged this story, so the story's Acceptance Criteria are the whole
scope of this plan. Each Acceptance Criterion is a criterion named `ac:<n>`, numbered from 1 in
the order the story lists them, and the plan covers each one with an executable assertion.{% endif %} A {% if book_services %}claim{% else %}criterion{% endif %} the story's own words make universal (`every`,
`all`, `each`, `throughout`, a parenthesized category list) needs a coverage inventory first:
list each named category in `qa-plan.md` and map each to an assertion. A representative
sample proves only the category it exercises.

Read the story for the wording of each {% if book_services %}claim{% else %}criterion{% endif %}. Write no scenario against anything the {% if book_services %}claims{% else %}criteria{% endif %}
do not name, and leave no {% if book_services %}claim{% else %}criterion{% endif %} uncovered. A live check is the one exception: its runbook
covers it, and no scenario does.

### The two files

Write both directly under the spec dir:

1. `qa_plan.py`, mandatory.
2. `qa-plan.md`, the rationale and the {% if book_services %}claim{% else %}criterion{% endif %}-to-scenario map. Create it with
   `timeout 30 ostler create spec <story-id> qa-plan.md`, where `<story-id>` is the story's id
   (the spec dir's folder name, passed in as `story_id`). That stamps the frontmatter. Write
   below the `---` block and leave it in place.

Playwright and Maestro are drivers a target selects, not tools an agent operates instead.
Inputs a run needs before it starts belong in `qa-inputs/`, never under the disposable `qa/`.

### The module

A plan is a Python module, and each scenario is a function ostler executes under the
project's own interpreter. A wrong key raises on the line that read it, and the traceback
names it.

```python
import json

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python", base_url="{gateway}")


@scenario(
    target=api,
    mechanism="live",
    covers=["claim:1"],
    preconditions=["the service health check reports ready"],
    checkpoints=["the publish request is accepted", "the stored object carries the token uid"],
    forbid=["the author field is taken from the request body"],
)
def publish_records_the_real_author(qa: Qa) -> None:
    """Publish ignores a spoofed author and persists the verbatim message."""
    uid = qa.http.post("/v1/session", json_body={"token": "demo"}).json()["uid"]
    qa.http.post("/v1/publish", json_body={"author": "attacker", "message": "hello"})
    stored = qa.http.get("/v1/objects/live/page").json()
    qa.check("author is the token uid, not the request body",
             qa.field(stored, "metadata.author") == uid,
             actual=qa.field(stored, "metadata.author"), expected=uid, covers=["claim:1"])
    json.dump(stored, qa.artifact("steps/publish-stored.json", kind="json").open("w"))
```

Declare only the targets the story needs. Every scenario has a target, a mechanism, an
objective (its docstring), preconditions, checkpoints, `covers`, and at least one `qa.check`
that names the same ids in its own `covers=`. `covers=` holds only {% if book_services %}`claim:<n>`{% else %}`ac:<n>`{% endif %} ids.

A target's `base_url` names the service as `{name}`, such as `{gateway}`, the name
`ostler env address` takes. The run resolves it from its copy's address book as the plan
starts, so the plan never holds a host and port. A port copied from a running copy points the
next run at a stack that is gone.
`mechanism` is provenance: `live` drives the running product, and `fixture` drives it from a
canned input. `driver` is execution: `python`, `playwright` or `maestro`. A scenario's id is
its function name with underscores turned into dashes.

- **`preconditions`** state what must already be true for the observation to mean anything.
- **`checkpoints`** state what an observer would see the scenario prove, in order. Each one
  has an assertion behind it.
- **`forbid`** names the weaker or wrong behaviour this scenario must be able to catch.
  Choose the setup state so that every `forbid` entry would change something you observe.
  When the answer to "which value in my arrangement would come back different" is "none", the
  arrangement is wrong, not the assertion.

### What the module may do

- **Module level is declarations only.** `ostler qa run` imports the module, so a request,
  a subprocess or a file write at module scope runs on every load of the plan.
- **Read product data with `qa.field`, never by subscript.** `qa.field(payload, "items.0.id")`
  yields `MISSING` where a key is absent, which satisfies no assertion, so the check goes red
  where it can explain itself. A `.get("items", [])` default makes a broken response pass.
  `ostler qa lint` rejects a named-key subscript anywhere in the plan.
- Everything a scenario needs is on `qa`: `qa.dir` is the evidence directory of this run,
  `qa.root` the repo root, `qa.spec_dir` the spec dir. Never rebuild them from a literal path.
- `ostler qa lint` allowlists the plan's AST. There is no `subprocess`, no `os.system`, no
  `pathlib`, and no importing a helper beside the plan. A command runs through
  `qa.tool(name)` for a command on PATH. Prefer `qa.http` for HTTP: it binds the
  target's `base_url` and raises `HttpError` on any status outside `expect_status=`.
- **Write for the reader of `qa-report.md`.** Phrase `qa.step("...")` as what a person would
  do and a label as the claim it proves. Always pass `actual=` to `qa.check`, `qa.require`
  and `qa.eventually`.

| call | what it does |
| --- | --- |
| `qa.field(data, "a.b.0")` | read observed data along a dotted path; missing yields `MISSING` |
| `qa.check(label, condition, actual=..., expected=..., covers=...)` | record one claim; never raises |
| `qa.require(label, condition, ...)` | record one claim and stop the scenario if it fails |
| `qa.eventually(label, lambda: ..., covers=...)` | a claim the page may arrive at; re-samples until it holds |
| `qa.require_eventually(label, lambda: ..., ...)` | the same, stopping the scenario when it never arrives |
| `with qa.step("label"):` | group a phase under a named step |
| `qa.capture(key, value)` / `qa.get(key)` | publish a value into the ledger and read it back |
| `qa.artifact(path, kind="...")` | register a file as evidence, resolved inside `qa.dir` |
| `qa.secret("NAME")` | a declared secret's value, redacted from the ledger |
| `qa.tool("name").run(*args, cwd=..., env=..., timeout=60)` | a command on PATH |
| `qa.http.get/post/put/patch/delete(path, json_body=..., headers=..., expect_status=...)` | HTTP against `base_url` |
| `qa.goto(url)`, `qa.by_role/by_label/by_test_id/by_text/by_css`, `qa.screenshot(name)`, `qa.page` | the browser, on a `playwright` target |
| `qa.diagnostics.console_errors/page_errors/failed_requests/responses()` | the page's live console and network record |
| `qa.maestro.flow([...])` / `qa.maestro.run(flow)` | build and run a Maestro flow |

This table is the short form. Read the harness contract in full in place of
ostler's own code:

{% if has_skill("ostler-cli") %}
- `{{ skill_path("ostler-cli", "references/qa-harness-reference.md") }}`: each call's
  arguments, return value and failure.
{% endif %}
- `ostler checks <name>`: one check's signature and the defect it excludes.

Anything the page has to reach is `eventually`, and anything later lines depend on is
`require_eventually`. `qa.check` receives a collapsed bool, so hand over a sampler instead.

- **Wait for the element you read.** `.count()`, `.get_attribute()`, `.inner_text()`,
  `.is_visible()` and `qa.page.evaluate()` sample once. Await the specific locator first.
- **Take every CLI flag, route and output shape from where it is defined.** A product route
  or output comes from the product's own source. A product command's flags come from its
  `--help`.
- **Defeat the test runner's result cache.** Pass the runner's flag that forces execution on
  every invocation the evidence depends on.
- When a scenario shells out, assert on what the command printed about the behaviour, not on
  `returncode == 0`.
- `background(...)` declares foreground services scoped to the run. The stack itself is
  already up before the plan runs.
- Files a scenario writes go under `qa.dir` through `qa.artifact(...)`. Never spell the
  `qa/` path out.
- **Arrangement is declared, not improvised.** State one scenario needs is reached by driving
  the product's documented operations inside a `qa.step`. Writing rows behind the product's
  back is not.

### A 500 is a defect

A status of 500 or higher is an engineering failure in the product. A plan never asserts one
as the expected outcome, and `expect_status=` lists only the statuses the product owes. A 500
on what the slice sends is a finding. The story fixes it.

### What `qa-plan.md` explains

- Preflight, targets, credentials by symbolic name, and health checks.
- One section per {% if book_services %}claim in the order listed above{% else %}Acceptance Criterion in the order the story lists them{% endif %}.
- Each scenario's objective, preconditions, checkpoints, forbidden bypasses, the arrangement
  detail that makes each bypass observable, and its terminal proof.

Start every flow at its entry, assert its end, and fail on a 5xx, a crash or a console error
on the way. A green test suite alone never decides a pass.

### Running one scenario

The stack is up, so run a scenario you write or change on its own while you debug it:

```bash
ostler qa run <spec_dir>/qa_plan.py --spec <spec_dir> \
  --scenario <scenario-id> --out-dir <scenario-id>
```

`--out-dir` takes a label, not a path. The run lands in
`<spec_dir>/{{ workhorse_var('qa_scratch_dir') }}/<scenario-id>/`, outside the repo.
Use one label per scenario: the runner clears its out-dir on every run. The scored run is the
verdict, not this one. Fix what does not resolve and run it again. Runner tooling may be
repaired. Product code may not.
