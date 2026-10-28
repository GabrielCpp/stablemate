---
type: concept
slug: authoring-qa-scenarios
title: Authoring QA scenarios
---
# Authoring QA scenarios

A book's `qa_plan.py` is a plain Python module written against a small authoring API, then run
by copying it (and the whole `qa/harness/` package it imports flat, as `ostler_qa`,
`ostler_qa_paths`, and so on) into a sandbox and executing it as a script — never imported as
part of the `ostler` package itself. `ostler_qa.py` is both the authoring surface a book author
writes against and the runtime that later replays what they wrote: `plan` names the run,
`target` and `secret` declare an address or a credential the scenario needs, `background`
starts a long-lived process for the scenario's duration, and `scenario` registers one check
function under an id and a human title. Each registered function receives a `Qa` instance — the
object a check calls to make an HTTP request (`Http`), run a step of the book under test, open
a browser, read a fixture, or build the environment a tool run needs (`scenario_env`) — and
raises `CheckFailed` or lets a `ClaimFault`/`FixtureFault` propagate when the book's claim does
not hold. `scenario_env` expands a `$NAME` reference in a declared value against the process
environment, then resolves any value shaped like a relative path against
`scenario_checkout_copy()`, so a compiled CLI run whose `invoke` act declares `env:` gets a
variable pointing at a file inside the scenario's own checkout rather than the harness's.

Outside a single check, `ostler_qa.py` also carries the pieces a scenario rarely touches
directly: `Target`/`Secret`/`ScenarioDecl` are the frozen records a `plan()` call accumulates;
`Response`, `Exchange` and `ExchangeEvidence` are what `Http` hands back and what a failure
report quotes; `Maestro`, `Tesseract` and `Convert` wrap the external mobile-automation, OCR and
image-conversion binaries a scenario may shell out to, through the generic `Tool`/`ToolResult`
process runner. A `Maestro` flow that exits non-zero hands back a result whose `seen` names the
step the flow stopped at and what the device screen showed afterwards, and `verify` records that
text with a failed phone check. `Maestro.pattern` renders a book name, and an optional
held text, into the Java regex a flow's `text:` selector full-matches, and `Maestro.run` passes
a flow's run-time values as `-e` variables, so a reference the plan resolves reaches the flow as
`${OKF_REF_n}`. A second, unrelated half of the module is static analysis: `count_checks`,
`extract_check_covers`, `extract_check_calls`, `extract_locators`, `extract_vets` and
`extract_instances` parse a `qa_plan.py` file's AST without running it, so a book-writing tool
can ask what a plan covers before any sandbox exists; `_run` and `main` are the actual
subprocess entry point that loads a module and executes one scenario id by its registered
function.

A check's `Qa` methods read raw results — an HTTP response, a DOM element, a file on disk — into
a typed "reading", then a verifier judges that reading against the arguments the check passed.
`ostler_qa_verdicts.py` defines the `Verdict` every judge returns and the small argument
coercions (`str_arg`, `scalar_arg`, `strings_arg`) every reader shares; `ostler_qa_verifiers.py`
supplies `_verifier`, the one combinator that pairs a reader with a judge into a callable
`Verifier`. The reader/judge pairs split by what they read: `ostler_qa_responses.py` covers an
HTTP response's status, headers, process exit status, and captured stdout/stderr streams;
`ostler_qa_documents.py` covers a response body, read as JSON for a `json-path`/`count` claim or
as rendered text for an `omits` claim; `ostler_qa_files.py` covers a file or a directory tree on
disk, including a before/after pair read for an unchanged- or created/removed/persists-style
claim; `ostler_qa_paths.py` supplies the `$.key[index][*][?(@.key==value)]` path grammar every
JSON-reading verifier walks to pick a value out of a document.

The rest of the reader/judge pairs read a browser page, and those whose check compiles on a
phone also judge a phone flow's pass or fail. `ostler_qa_dom.py` reads one element's
attribute, form value, or focus state; `ostler_qa_elements.py` reads a page or element's
visibility, actionable/inert state, focus order, emitted-event count, title, console output, or
a triggered download. The same module holds the one rendering of a book name for both drivers:
`name_pattern` and `template_pattern` for the browser, and `maestro_pattern` with `java_quote`
for the phone. `ostler_qa_browser_state.py` reads the current URL, a storage location
(cookie, local or session storage), or the clipboard. `ostler_qa_browser.py` is what drives the
browser underneath all three: `Browser` wraps a Playwright page, `RecordedResponse` and
`ResponseWindow` capture network responses as they arrive so a later check can inspect one that
already happened. `ostler_qa_settle.py`'s `settle_screen` is the polling loop every element
reader waits on before taking its reading, so a check never reads a screen mid-transition. When
that wait times out because no declared state holds, or because the busy sign never went, the
message ends with what the last look at the screen showed: the page's accessibility snapshot in
a browser, the named nodes of the view hierarchy on a device.
`ostler_qa_transfer.py` simulates OS-level file handling a browser cannot do through its own
API: pasting text or HTML onto a locator, or dragging/choosing a file onto an upload control.
`ostler_qa_hierarchy.py` is the mobile equivalent of the DOM readers, scanning a device's
accessibility tree through `maestro` or `uiautomator` instead of a browser. A phone settle reads
through one resident `maestro mcp` session per run, and `DeviceReading` and `DeviceScreen` judge
a perceivable over the screen's whole scrollable content. `ostler_qa_scan.py`
is the browser-side counterpart: it merges overlapping element rectangles into the regions
`summarize` turns into a vet manifest, the same shape `ostler vet` registers against a book's
documented components.

`ostler_qa_lap.py`'s `Arranged` and `LapRecord` carry what one scenario step produced forward to
the step that reads it, the "lap" a multi-step scenario runs. `ostler_qa_checkout.py`'s
`copy_checkout` is unrelated to any of the above: it is how the sandbox gets the book's own git
checkout in the first place, copying a working tree into the sandbox while sharing `.git`
history and skipping the checkout's own `qa/` directory so a scenario cannot read its own
harness as book content.

- code: ostler/ostler/qa/harness/ostler_qa.py::plan@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::target@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::secret@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::background@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::scenario@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Http@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::scenario_env@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::CheckFailed@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::ClaimFault@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::FixtureFault@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Response@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Exchange@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Maestro@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Tesseract@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Convert@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::Tool@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::count_checks@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_check_covers@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_check_calls@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_locators@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_vets@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_instances@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::_run@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa.py::main@3d971d498ead
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::Verdict@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::str_arg@6473ea39a89f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@f540620c6633
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_http_status@9f63d115538b
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_response_header@9f63d115538b
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_exit_status@9f63d115538b
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_printed@9f63d115538b
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::verify_json_path@c7b9f1b585d5
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::verify_count@c7b9f1b585d5
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::verify_omits@c7b9f1b585d5
- code: ostler/ostler/qa/harness/ostler_qa_files.py::read_file@1c99efa3cc05
- code: ostler/ostler/qa/harness/ostler_qa_files.py::verify_unchanged@1c99efa3cc05
- code: ostler/ostler/qa/harness/ostler_qa_files.py::verify_created@1c99efa3cc05
- code: ostler/ostler/qa/harness/ostler_qa_paths.py::resolve_path@092f327030cd
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::verify_attribute@0596499cd4fb
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::verify_value@0596499cd4fb
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::verify_focused@0596499cd4fb
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_visible@75e92895f837
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_actionable@75e92895f837
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_focusable@75e92895f837
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_console@75e92895f837
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_download@75e92895f837
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::verify_url@753b30ac1b84
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::verify_stored@753b30ac1b84
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::verify_clipboard@753b30ac1b84
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::Browser@7a9c15e1ccae
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::RecordedResponse@7a9c15e1ccae
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::ResponseWindow@7a9c15e1ccae
- code: ostler/ostler/qa/harness/ostler_qa_settle.py::settle_screen@dbcb037d3798
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::paste@02ae85efa7b7
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::drop@02ae85efa7b7
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::upload@02ae85efa7b7
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::scan@eda1b6dcc202
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::parse_maestro@eda1b6dcc202
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::parse_device_nodes@eda1b6dcc202
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::DeviceReading@eda1b6dcc202
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::DeviceScreen@eda1b6dcc202
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::parse_uiautomator@eda1b6dcc202
- code: ostler/ostler/qa/harness/ostler_qa_lap.py::Arranged@908f9ce8d348
- code: ostler/ostler/qa/harness/ostler_qa_lap.py::LapRecord@908f9ce8d348
- code: ostler/ostler/qa/harness/ostler_qa_checkout.py::copy_checkout@d2d64738e2dc
- code: ostler/ostler/qa/harness/ostler_qa_scan.py::merge_rects@71decdf2a5c3
- code: ostler/ostler/qa/harness/ostler_qa_scan.py::summarize@71decdf2a5c3
- detail: [ostler](../cli.md)

## Contract

- flat imports: every `ostler_qa*.py` module imports its siblings by bare top-level name
  (`import ostler_qa_paths`), never as `ostler.qa.harness.ostler_qa_paths`; the package is
  deployed into a sandbox and run from there, not imported from an installed `ostler`.
- reader/judge split: a verifier is always a reading function plus a judge function paired by
  `_verifier`; the reading never raises on a mismatch, only the judge does, so a failure report
  can show what was actually read even when the claim it is judged against fails.
- static analysis never runs the plan: `count_checks`, `extract_check_covers`,
  `extract_check_calls`, `extract_locators`, `extract_vets` and `extract_instances` all parse a
  `qa_plan.py` file's AST and never import or execute it, so a book tool can summarize a plan a
  sandbox has not been built for yet.
- path grammar: `resolve_path` walks `$`, `.key`, `[index]`, `[*]` and `[?(@.key==value)]` steps
  against a parsed document; an index or key absent from the document resolves to nothing rather
  than raising, so a verifier reports "not found" as a normal failed reading.
- checkout isolation: `copy_checkout` always excludes the checkout's own `qa/` directory from the
  copy it makes, so a scenario reading the book's working tree can never read the harness that is
  running it.
- whole-screen settle: a phone settle judges a perceivable over the screen's whole scrollable
  content, as a browser counts an element below the fold as visible. On a miss in the viewport the
  reading drags the largest scrollable area forward, reads after each drag, and drags back by the
  distance it measured, never past the starting position, so a pull-to-refresh never fires.
