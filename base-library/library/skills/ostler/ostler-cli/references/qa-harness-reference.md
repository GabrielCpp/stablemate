# The QA harness, call by call

This page and `ostler checks` together are the whole harness contract a plan author needs.
[qa-plan-authoring.md](qa-plan-authoring.md) says how a plan is shaped. This page says what
each `qa.*` call takes, returns and raises, and how the validator reads what you wrote.

## Each check's observed value

`ostler checks <name>` prints one check's signature, the defect it excludes, and the line
`in a plan, qa.verify observes …`. That line names what `qa.verify(name, observed, …)` takes
as `observed`. `ostler checks` alone prints every check. `--json` gives the same as data.

```bash
ostler checks emitted
ostler checks http_status --json
```

## How the validator reads a `qa.verify` call

`ostler qa validate` reads the plan's source. It never runs it. So every `qa.verify` call
must say its claim in a form a reader of the source can see:

- The check name and each argument are literals, or module-level constants bound once.
  A constant bound twice at module level is dropped, and reads as computed.
- `qa.resolve("<text>")` as an argument reads as the text inside it. That is how a check
  argument names `@node.key` or `$name` and still matches the book.
- Any other computed value reads as `*`, and `*` matches no declared argument.
- `covers=` is a literal list of obligation ids, or a constant holding one.
- `label=` is free text. It takes no part in matching.
- A call counts wherever the scenario reaches it, including a helper function the scenario
  calls.
- The call matches the obligation's declared check exactly: the same name and every
  declared argument with the same value. When a call all but matches, the refusal names
  each argument that differs, as "declared X, invoked Y". Change what the scenario
  observes until the declared arguments hold. The declared arguments are the claim.
- When the plan already invokes the exact declared call for another obligation, the
  refusal says so. Add the id to that call's `covers=`.

## `qa.http`

`qa.http.get/post/put/patch/delete(path, json_body=, data=, headers=, expect_status=,
timeout=, follow_redirects=True)` sends to the target's `base_url`. A relative path
needs a `base_url`.

- A status of 400 or more raises `HttpError` unless `expect_status=` names it.
  `expect_status=` takes one int or a list.
- A scenario that proves a refusal names the refusal: `expect_status=409`. The response it
  returns is what `http_status` and `conflict_on_stale` observe.

## The address book

A target's `base_url` may name a service as `{name}`, such as `http://{gateway}/api`. The
run's address book gives the value:

- The harness reads the JSON object at `$STABLEMATE_ADDRESS_BOOK`, a map of name to URL.
- With the variable unset, `{name}` stays as written.
- A name the book does not give fails the plan with that name.
- A plan that writes `{gateway}` stays valid on every run, whichever port the run's stack
  holds. Write the name, never the port one run happened to get.

The harness fills `{name}` in a target's `base_url` and nowhere else. A tool, a fixture step
or a scenario that needs another service's URL reads the book itself. Each inherits
`$STABLEMATE_ADDRESS_BOOK`, so `json.loads(Path(os.environ["STABLEMATE_ADDRESS_BOOK"]).read_text())["api"]`
gives the `api` address in a scenario.

## `qa.fixture(name, *args)`

It puts the product into a state the book or the repo declared, and records that it did.

- A book `fixture` node runs its own steps. Its arguments are `key=value` strings:
  `qa.fixture("seeded-report", "owner=alice")`.
- One scenario calling it twice with the same arguments gets the first result back.
- It is built once per lap and reused by every scenario after, unless the node declares
  `lifetime: scenario`. A fixture with a `serve` step needs `lifetime: scenario`, because
  the process it starts ends with the scenario.
- A name with no book node is read from `agents.yml`'s `qa: {fixtures: …}` and runs
  through the tool it names.
- It returns a `ToolResult(command, stdout, stderr, exit_code)` with `.ok` and `.json()`.
- It raises `RuntimeError` when a step fails. The message names the step and the state
  that is missing.
- Each step runs in the step's `cwd`, or the repo root. It inherits the run's environment,
  so `$STABLEMATE_LEASE` names the run's copy and `$STABLEMATE_ADDRESS_BOOK` its book. A step
  that runs a command inside a service of that copy goes through `ostler env compose`, as
  ostler-okf's `stack.md` shows.

The fixtures a story may stand up are the ones its `## Fixtures` section and the context
packet name. The QA prompt lists them.

## References: `@node.key` and `$name`

- `@node.key` is a value a book node provides, such as the id a fixture created. It
  resolves once that node has run in this scenario. Before then it fails with "has not
  run (or does not provide …)". Run the fixture first.
- `$name` is a value captured earlier with `qa.capture(name, value)` or
  `qa.capture_field(name, data, path)`. It fails with "nothing has captured it" before then.
- `qa.resolve(text)` returns `text` with both kinds substituted.
- `qa.resolve_body(text)` returns the whole object or list when `text` is one `@node.key`
  that names a structure, and `qa.resolve(text)` otherwise. Use it for a request body
  member.

## The browser's observation window

`qa.window()` opens a window at this point of the scenario. It reads only what the page
does after it opens. Only a target with `driver='playwright'` has one. Any other driver
raises.

```python
seen = qa.window()
qa.by_role("button", name="Calculate").click()
calls = seen.requests_to("/api/reports/{id}/calculate", method="POST")
qa.verify("emitted", calls, event="calculate", count=1, covers=[CALCULATES])
response = seen.response_for("/api/reports/42/calculate", method="POST")
qa.verify("http_status", response, code=200, covers=[CALCULATES])
```

| call | returns |
| --- | --- |
| `response_for(path, method=)` | the one response on exactly that path, as a `RecordedResponse` with `.status`, `.url`, `.text` and `.json()`. It raises `LookupError` naming the paths the page did request when none match, and raises when several match |
| `requests_to(path, method=)` | every request on that path, once the page has gone quiet. `{name}` in the path matches one whole segment |
| `console()` | every console message in the window, once the page has gone quiet |
| `downloads()` | every file the page handed the user in the window, as dicts with `name`, `text` and `failure` |

`.json()` raises `LookupError` when the body was not captured. A body never recorded is not
an empty one.

## `qa.diagnostics`

It covers the whole scenario, not one window. The browser driver alone has it.

- `console(level=, contains=)` returns the console messages that match, as dicts.
- `downloads()` returns every download in the scenario.
- `quiet()` waits until no request is in flight and none has started for a short interval.
  The window calls it for you before it reads.

## `qa.tree(where)`

It reads every file under `where` once, as a dict keyed by the path relative to `where`. A `.json` file is
parsed. Any other file is text, and `.texts` holds the raw text of every file. `where` is
relative to `qa.dir` and must stay inside it.

Read the tree before and after the action, and hand the pair to a differential check:

```python
before = qa.tree("out")
qa.tool("exporter").run("--to", "out")
qa.verify("created", (before, qa.tree("out")), subject="report.csv", covers=[EXPORTS])
```

## `qa.tool(name).run(*args, cwd=, env=, timeout=)`

It runs a command this repo opted into in `agents.yml`. The QA prompt lists the tools and
whether each is on this host. A name that is not opted in raises with the line to add.
It returns a `ToolResult`. A non-zero exit does not raise. Hand the result to
`exit_status`, `stdout` or `stderr`.

- It runs from the repo root. `cwd=` moves it under `qa.dir`: a relative path is read from
  `qa.dir`, the folder is created when missing, and a path outside `qa.dir` raises.
- It inherits the run's environment. `env=` overlays it, and each name it sets must be
  declared once at module level with `tool_env("NAME")`. An undeclared name raises.
- `timeout=` defaults to 60 seconds. A command that runs past it returns exit code 124.

## Browser requests

`page.route` and other Playwright calls on `qa.page` are allowed. The plan lint has no rule
against them. Locators still come from `qa.by_role` and its siblings, so the validator can
check them against the book.

## The browser stays clean

Every scenario on a `driver='playwright'` target ends with one more assertion, "the browser
stayed clean", bound to the scenario's `covers=`. No `qa.verify` call can waive it. It fails
on any of these:

- an uncaught page error;
- any response of status 500 or higher, including one that `page.route` fulfils;
- a dialog the page opened with no answer declared, which the harness dismissed;
- `qa.answer_dialogs(...)` called when no dialog opened.

`qa.answer_dialogs("accept")` or `qa.answer_dialogs("dismiss")` answers every dialog the page
opens after the call, as the user clicking OK or Cancel.

A scenario that proves the page's error path drives it without a 5xx: `route.abort()` for a
network failure, or a 4xx status the product treats as a failure.
