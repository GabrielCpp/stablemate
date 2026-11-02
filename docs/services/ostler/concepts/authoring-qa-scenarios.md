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

- code: ostler/ostler/qa/harness/ostler_qa.py::plan@8d4a996f573f
- code: ostler/ostler/qa/harness/ostler_qa.py::target@004738c14823
- code: ostler/ostler/qa/harness/ostler_qa.py::secret@03ec751a0a19
- code: ostler/ostler/qa/harness/ostler_qa.py::background@ff9310569202
- code: ostler/ostler/qa/harness/ostler_qa.py::scenario@4627c6acef7d
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa@e8e9e751fd27
- code: ostler/ostler/qa/harness/ostler_qa.py::Http@55912ec4cef1
- code: ostler/ostler/qa/harness/ostler_qa.py::scenario_env@69e209e9bd38
- code: ostler/ostler/qa/harness/ostler_qa.py::CheckFailed@2d91bd45de1f
- code: ostler/ostler/qa/harness/ostler_qa.py::ClaimFault@5b5fba27b76a
- code: ostler/ostler/qa/harness/ostler_qa.py::FixtureFault@fb62eecb6b50
- code: ostler/ostler/qa/harness/ostler_qa.py::Response@70d2f288d407
- code: ostler/ostler/qa/harness/ostler_qa.py::Exchange@dd50376ac14f
- code: ostler/ostler/qa/harness/ostler_qa.py::Maestro@b5e05dbd5366
- code: ostler/ostler/qa/harness/ostler_qa.py::Tesseract@3587f68ddf3c
- code: ostler/ostler/qa/harness/ostler_qa.py::Convert@130a0cde031b
- code: ostler/ostler/qa/harness/ostler_qa.py::Tool@c59d509df426
- code: ostler/ostler/qa/harness/ostler_qa.py::count_checks@be8beed2102a
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_check_covers@cfad605b8ed6
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_check_calls@a635c68e9653
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_locators@5b27c72c2ace
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_vets@8b3fe168ef09
- code: ostler/ostler/qa/harness/ostler_qa.py::extract_instances@9dae79f46dc6
- code: ostler/ostler/qa/harness/ostler_qa.py::_run@0300cca09473
- code: ostler/ostler/qa/harness/ostler_qa.py::main@e064562a6978
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::Verdict@f872cc975752
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::str_arg@6789a24f771f
- code: ostler/ostler/qa/harness/ostler_qa_verifiers.py::_verifier@e0792d3a1d2a
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_http_status@2d1c94447a21
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_response_header@133724cec1a4
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_exit_status@f1db151c09f5
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::verify_printed@6213fb32c13e
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::verify_json_path@78e01ade0ed4
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::verify_count@2f2631b1be2e
- code: ostler/ostler/qa/harness/ostler_qa_documents.py::verify_omits@957c4de95063
- code: ostler/ostler/qa/harness/ostler_qa_files.py::read_file@7323032bd2b3
- code: ostler/ostler/qa/harness/ostler_qa_files.py::verify_unchanged@f0f626504478
- code: ostler/ostler/qa/harness/ostler_qa_files.py::verify_created@1f07716af334
- code: ostler/ostler/qa/harness/ostler_qa_paths.py::resolve_path@c7c8adc7d334
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::verify_attribute@6cfeb4332989
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::verify_value@ff67cb18e9ab
- code: ostler/ostler/qa/harness/ostler_qa_dom.py::verify_focused@e5bae221ece6
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_visible@529a98da1382
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_actionable@2a1c5aaa61b0
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_focusable@34ff4f2b7892
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_console@fe51e00c1e81
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::verify_download@37aeb9c07c90
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::verify_url@9f4169bd4980
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::verify_stored@8933e9ac86d0
- code: ostler/ostler/qa/harness/ostler_qa_browser_state.py::verify_clipboard@4cede15e0764
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::Browser@abc312bd9a1c
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::RecordedResponse@430439281b7b
- code: ostler/ostler/qa/harness/ostler_qa_browser.py::ResponseWindow@eb4c293213b1
- code: ostler/ostler/qa/harness/ostler_qa_settle.py::settle_screen@788ae59ee56f
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::paste@5278310185fb
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::drop@a53462986460
- code: ostler/ostler/qa/harness/ostler_qa_transfer.py::upload@b6f2d5c16b26
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::scan@834ee25f0693
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::parse_maestro@b18cdc0e6940
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::parse_device_nodes@bf1d9ab90f62
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::DeviceReading@c692d5c71294
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::DeviceScreen@ddbe7b318607
- code: ostler/ostler/qa/harness/ostler_qa_hierarchy.py::parse_uiautomator@3e8eb8fde32d
- code: ostler/ostler/qa/harness/ostler_qa_lap.py::Arranged@d2300a54c1e9
- code: ostler/ostler/qa/harness/ostler_qa_lap.py::LapRecord@4ff057faf213
- code: ostler/ostler/qa/harness/ostler_qa_checkout.py::copy_checkout@7d9282dec218
- code: ostler/ostler/qa/harness/ostler_qa_scan.py::merge_rects@e12c3290326a
- code: ostler/ostler/qa/harness/ostler_qa_scan.py::summarize@c8a9e958b44a
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
