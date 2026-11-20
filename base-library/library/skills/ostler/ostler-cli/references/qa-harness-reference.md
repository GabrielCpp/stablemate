# The QA harness, call by call

[qa-plan-authoring.md](qa-plan-authoring.md) says how a plan is shaped. This page says what
each `qa.*` call takes, returns and raises.

## `qa.http`

`qa.http.get/post/put/patch/delete(path, json_body=, data=, headers=, expect_status=,
timeout=, follow_redirects=True)` sends to the target's `base_url`. A relative path
needs a `base_url`.

- A status of 400 or more raises `HttpError` unless `expect_status=` names it.
  `expect_status=` takes one int or a list.
- A scenario that proves a refusal names the refusal: `expect_status=409`. The response it
  returns is what the scenario asserts on.

`HttpError` is importable from `ostler_qa`. It carries the method, the URL, the status and
the first 500 characters of the reply in its message, and no response object. A request that
cannot connect raises it too.

- With `expect_status=` given, a status outside it is first written down as a failed
  assertion, "`<METHOD> <url>` answers [the expected statuses]", against the current covers.
- An `HttpError` the scenario does not catch ends the scenario as errored, and the report
  quotes the request that raised it. The harness still closes the browser and stops each
  served process.
- Inside `with qa.claim([ID]):` it fails that claim alone, against `ID`, and the scenario
  goes on to its next claim. Use a claim when one scenario proves several criteria in
  turn, so one refusal does not hide the rest.

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

It puts the product into a state the repo declared, and records that it did.

- A name is read from `agents.yml`'s `qa: {fixtures: …}` and runs through the tool it names.
  Its arguments are `key=value` strings: `qa.fixture("seeded-report", "owner=alice")`.
- One scenario calling it twice with the same arguments gets the first result back.
- It returns a `ToolResult(command, stdout, stderr, exit_code)` with `.ok` and `.json()`.
- It raises `RuntimeError` when a step fails. The message names the step and the state
  that is missing.
- Each step runs in the step's `cwd`, or the repo root. It inherits the run's environment,
  so `$STABLEMATE_LEASE` names the run's copy and `$STABLEMATE_ADDRESS_BOOK` its book. A step
  that runs a command inside a service of that copy goes through `ostler env compose`, as
  the `ostler-cli` skill's `references/stack.md` shows.

## References: `$name`

- `$name` is a value captured earlier with `qa.capture(name, value)` or
  `qa.capture_field(name, data, path)`. It fails with "nothing has captured it" before then.
- `qa.resolve(text)` returns `text` with each `$name` substituted.

## The browser's observation window

`qa.window()` opens a window at this point of the scenario. It reads only what the page
does after it opens. Only a target with `driver='playwright'` has one. Any other driver
raises.

```python
seen = qa.window()
qa.by_role("button", name="Calculate").click()
calls = seen.requests_to("/api/reports/{id}/calculate", method="POST")
qa.check("the page sent one calculate request", len(calls) == 1,
         actual=len(calls), expected=1, covers=["claim:1"])
response = seen.response_for("/api/reports/42/calculate", method="POST")
qa.check("the calculate request succeeded", response.status == 200,
         actual=response.status, expected=200, covers=["claim:1"])
```

| call | returns |
| --- | --- |
| `response_for(path, method=, initiator=)` | the one response on exactly that path, as a `RecordedResponse` with `.status`, `.url`, `.text` and `.json()`. It raises `LookupError` naming the paths the page did request when none match, and raises when several match |
| `requests_to(path, method=, initiator=)` | every request on that path, once the page has gone quiet. `{name}` in the path matches one whole segment. `initiator` defaults to `"page"`, so a service worker's own requests are skipped. `initiator=None` returns all and `"worker"` only the worker's |
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

Read the tree before and after the action, and compare the pair:

```python
before = qa.tree("out")
qa.tool("exporter").run("--to", "out")
after = qa.tree("out")
qa.check("the export wrote report.csv", "report.csv" not in before and "report.csv" in after,
         actual=sorted(after), expected="report.csv present", covers=["claim:2"])
```

## `qa.tool(name).run(*args, cwd=, env=, timeout=)`

It runs a command found on PATH. A command that is not on PATH raises `qa tool '<name>' is not on PATH`.
It returns a `ToolResult`. A non-zero exit does not raise. Assert on its
`exit_code`, `stdout` or `stderr`.

- It runs from the repo root. `cwd=` moves it under `qa.dir`: a relative path is read from
  `qa.dir`, the folder is created when missing, and a path outside `qa.dir` raises.
- It inherits the run's environment. `env=` overlays it, and each name it sets must be
  declared once at module level with `tool_env("NAME")`. An undeclared name raises.
- `timeout=` defaults to 60 seconds. A command that runs past it returns exit code 124.

## Browser requests

`page.route` and other Playwright calls on `qa.page` are allowed. The plan lint has no rule
against them. Locators still come from `qa.by_role` and its siblings.

## The browser stays clean

Every scenario on a `driver='playwright'` target ends with one more assertion, "the browser
stayed clean", bound to the scenario's `covers=`. Nothing waives it. It fails
on any of these:

- an uncaught page error;
- any response of status 500 or higher, including one that `page.route` fulfils;
- a dialog the page opened with no answer declared, which the harness dismissed;
- `qa.answer_dialogs(...)` called when no dialog opened.

`qa.answer_dialogs("accept")` or `qa.answer_dialogs("dismiss")` answers every dialog the page
opens after the call, as the user clicking OK or Cancel.

A 500 is an engineering failure in the product. The check exists to catch it, so a plan never
fakes one and never asserts one as expected. A scenario that proves the page's error path
uses a failure the product is built to return: a 4xx the route documents, or a
network failure with `route.abort()`.
