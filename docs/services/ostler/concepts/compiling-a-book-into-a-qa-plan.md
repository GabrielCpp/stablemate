---
type: concept
slug: compiling-a-book-into-a-qa-plan
title: Compiling a book into a QA plan
---
# Compiling a book into a QA plan

`ostler qa compile-plan` turns a book's claims into runnable Python: one check function per
obligation the book states and a driver can observe. `compile.py`'s `compile_plan` is the entry
point, walking a `ContextPacket` of `Obligation` records and, for each, choosing a driver
(`_dispatch`), refusing it with a `ScenarioRefusal` when no driver can reach it (`_state_target`,
`_undriven_state_gaps`), and appending the result to a growing `qa_plan.py` source string; a
`## Debt` section at the end lists every obligation whose book entry carries `--no-verify`
(`_book_debt`, `_no_verify_detail`), so a plan always shows what it chose not to prove alongside
what it did. `compile_plan_gaps` runs the same walk purely to report what has no driver, before
any code is generated; `cmd_compile_plan` is the CLI entry point. All three share `_plan_header`,
which renders the banner, import line and `plan(...)` call a generated module opens with; when
`invoke_env_names` finds a CLI `invoke` act in the book that declares `env:`, `_plan_header` adds
`tool_env` to the import line and a `tool_env(...)` call naming those acts right after
`plan(...)`, so every compiled plan carries that line whenever the book names an environment
variable, not only when a check needs one.

Each backend owns one driver. `compile_http.py`'s `api_scenarios` builds a check function around
an `Http` call for an HTTP-observed obligation, assembling a request body from a `CheckValue`
tree (`_tree_literal`) and threading a captured field from an earlier step into a later one's
assertion (`read_back`); `http_walk` compiles an HTTP-only journey the same way. `compile_cli.py`'s
`cli_scenario_body` runs the book's CLI binary as a subprocess and asserts on its exit status or
captured stdout, deciding first whether a check is about the file tree before or after
(`reads_the_tree`, `compares_the_tree`); `cli_journey` and `cli_move_walk` compile a CLI-driven
journey or state walk. `_run_arguments` assembles every emitted `.run(...)` call's keyword
arguments — `argv`, `cwd=qa.scenario_checkout_copy()`, and, when the act declares `env:`,
`env=qa.scenario_env(...)` — so a step's or scenario's subprocess call carries whatever
environment the book's `invoke` act names, in both `cli_scenario_body` and `cli_journey`. `compile_page.py`'s `page_scenarios` builds a web-UI check, holding a
conditional or mutually-exclusive component's obligations together (`_node_claims`,
`_shared_shape`) and inserting a navigation step before the assertion when the obligation is not
already on the right screen (`_arrival_scenario`); `web_state_walks` compiles a `DataState`
screen-to-screen walk. `compile_playwright.py` supplies what `compile_page.py` emits into each
scenario body: `perform_acts` renders a book's `acts:` into Playwright action lines,
`page_observations` renders one assertion from a locator and a check call, and `web_walk` compiles
a browser-driven journey. `compile_maestro.py`'s `mobile_scenarios` is the same shape for a mobile
surface, pairing a generated Maestro YAML flow (`_flow_yaml`) with the Python function that
invokes it; `maestro_walk` and `device_state_walks` compile a mobile journey or state walk.
`compile_moves.py`'s `move_walks` and `state_walks` compile the obligations that assert one
`DataState` reaches another by a named `Move`, independent of which of the four drivers performs
the move. `compile_journey.py` sits above all four backends: `journey_target`/`api_target`
resolve a `JourneyTarget` to the right `JourneyBackend`, `journey_scenarios` builds the
`JourneyPlan` of every `BoundJourney` a book declares, and `journey_scenario` walks one
`JourneyWalk` into a `WalkedJourney` by calling back into whichever of `http_walk`, `cli_journey`,
`web_walk` or `maestro_walk` the target's backend names.

Three modules are shared by every backend rather than owning one. `compile_stops.py` resolves
what screen or state a journey step lands on (`resolve_stop`, `resolve_state`, `expand_steps`),
the "where did this step end up" question every backend asks before it emits a settle or an
assertion for that step. `compile_support.py` decides what a check can observe at all:
`unobservable_gap` reports a check whose chosen driver cannot see the thing it claims,
`vettable`/`vet_calls` decide whether a screen's rendering can be checked with `ostler vet`, and
`check_document`/`trigger_name`/`trigger_act`/`on_href` render one check call's book-declared arguments into
the literal values a scenario body embeds. `plan_source.py` is the lowest-level codegen layer:
`Gap` and `ScenarioRefusal` are the two shapes a compile step uses to report it produced no
scenario, `python_literal`/`call_kwargs` render a Python value as source text, `Arrangement`/
`arrangement_of` group an obligation's fixtures, and the `*_function_name` helpers
(`claim_scenario_function_name`, `journey_function_name`, `probe_function_name`, …) give every
emitted function a distinct, legal name.

The rest of the files hold the book-side data every backend reads instead of the Python-side
code it writes. `obligation.py` defines `Obligation` itself — a claim, with its `Locators`,
`CallRow` acts, `FixtureRow` needs and `FlowStep` sequence — and `obligation_of`/`obligations_of`
parse one back out of the context JSON. `obligation_frame.py`'s `book_nodes` and
`obligation_frame` build the `BookNode` graph obligations are minted against, resolving a node's
`extends:` (`resolve_extends`) and its `repeat:` contract (`RepeatContract`) first.
`book_index.py`'s `BookIndex` indexes a list of obligations by node id so a backend can look up a
node's acts, fixtures or captures (`node_acts`, `fixture_pages`, `captures_by_node`) without
rescanning the full list per scenario. `book_fixtures.py`'s `resolved` walks the graph to find
what a fixture node provides, needs and runs as steps (`_declared_provides`, `_needs_of`,
`_steps_of`) before a scenario arranges it. `journey_steps.py`'s `journey_steps` turns a node's
`journey:` bullets into an ordered tuple of steps. `fixture_provides.py`'s `closure` computes the
transitive set of fixtures a node's steps provide, `index` inverting that into a
provider-to-dependent lookup. `fixture_browser.py`'s `browser_step` classifies one UI journey
step as a browser action by resolving its locator, screen, or act against the graph.
`navigation.py`'s `navigation_rows` parses a surface's declared routes into a `SurfaceNavigation`
per surface, and `maestro_launch` derives the mobile launch flow a mobile journey needs before
its first hop.

- code: ostler/ostler/qa/compile.py::compile_plan@f211b537faac
- code: ostler/ostler/qa/compile.py::compile_plan_gaps@f211b537faac
- code: ostler/ostler/qa/compile.py::cmd_compile_plan@f211b537faac
- code: ostler/ostler/qa/compile.py::_plan_header@f211b537faac
- code: ostler/ostler/qa/compile_http.py::api_scenarios@e17faa3b5f39
- code: ostler/ostler/qa/compile_http.py::http_walk@e17faa3b5f39
- code: ostler/ostler/qa/compile_http.py::read_back@e17faa3b5f39
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@479bda09f64c
- code: ostler/ostler/qa/compile_cli.py::cli_journey@479bda09f64c
- code: ostler/ostler/qa/compile_cli.py::_run_arguments@479bda09f64c
- code: ostler/ostler/qa/compile_cli.py::invoke_env_names@479bda09f64c
- code: ostler/ostler/qa/compile_page.py::page_scenarios@606b70054ffc
- code: ostler/ostler/qa/compile_page.py::web_state_walks@606b70054ffc
- code: ostler/ostler/qa/compile_playwright.py::perform_acts@373cfbcaf3e9
- code: ostler/ostler/qa/compile_playwright.py::page_observations@373cfbcaf3e9
- code: ostler/ostler/qa/compile_playwright.py::web_walk@373cfbcaf3e9
- code: ostler/ostler/qa/compile_maestro.py::mobile_scenarios@da217d55c8c0
- code: ostler/ostler/qa/compile_maestro.py::maestro_walk@da217d55c8c0
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::maestro_pattern@ce61d0ffcd61
- code: ostler/ostler/qa/harness/ostler_qa.py::Maestro@80d0580df929
- code: ostler/ostler/qa/compile_moves.py::move_walks@357b72ed93c7
- code: ostler/ostler/qa/compile_moves.py::state_walks@357b72ed93c7
- code: ostler/ostler/qa/compile_journey.py::journey_target@421ed1147b57
- code: ostler/ostler/qa/compile_journey.py::api_target@421ed1147b57
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@421ed1147b57
- code: ostler/ostler/qa/compile_journey.py::journey_scenario@421ed1147b57
- code: ostler/ostler/qa/compile_stops.py::resolve_stop@e2a0b2312b45
- code: ostler/ostler/qa/compile_stops.py::resolve_state@e2a0b2312b45
- code: ostler/ostler/qa/compile_stops.py::ScreenStop@e2a0b2312b45
- code: ostler/ostler/qa/compile_support.py::unobservable_gap@771f910c9275
- code: ostler/ostler/qa/compile_support.py::vettable@771f910c9275
- code: ostler/ostler/qa/compile_support.py::check_document@771f910c9275
- code: ostler/ostler/qa/plan_source.py::Gap@08fddc26f73f
- code: ostler/ostler/qa/plan_source.py::ScenarioRefusal@08fddc26f73f
- code: ostler/ostler/qa/plan_source.py::python_literal@08fddc26f73f
- code: ostler/ostler/qa/plan_source.py::arrangement_of@08fddc26f73f
- code: ostler/ostler/qa/obligation.py::Obligation@4bdc7a410ade
- code: ostler/ostler/qa/obligation.py::obligation_of@4bdc7a410ade
- code: ostler/ostler/qa/obligation.py::obligations_of@4bdc7a410ade
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@59e7ee8278ae
- code: ostler/ostler/qa/obligation_frame.py::obligation_frame@59e7ee8278ae
- code: ostler/ostler/qa/obligation_frame.py::BookNode@59e7ee8278ae
- code: ostler/ostler/qa/book_index.py::BookIndex@dd91e95d2722
- code: ostler/ostler/qa/book_index.py::node_acts@dd91e95d2722
- code: ostler/ostler/qa/book_fixtures.py::resolved@26e58a44f4ed
- code: ostler/ostler/qa/journey_steps.py::journey_steps@0794ea6c9659
- code: ostler/ostler/qa/fixture_provides.py::closure@9053b42918c0
- code: ostler/ostler/qa/fixture_provides.py::index@9053b42918c0
- code: ostler/ostler/qa/fixture_browser.py::browser_step@d769665467aa
- code: ostler/ostler/qa/navigation.py::navigation_rows@e5be923f66b9
- code: ostler/ostler/qa/navigation.py::maestro_launch@e5be923f66b9
- detail: [ostler](../cli.md)

## Contract

- one driver per obligation: `dispatch_target` (see
  [Running and reporting a QA run](running-and-reporting-a-qa-run.md)) picks exactly one of
  cli/http/web/maestro for an obligation before any `compile_*` backend sees it; a backend never
  chooses its own driver.
- a refusal is not an error: `Gap` and `ScenarioRefusal` are ordinary return values threaded back
  up to `compile_plan`, which reports them in the plan's debt section rather than raising, so a
  compile always finishes with a plan, even a partial one.
- captures resolve forward only: `read_back` and the `{node-id.capture}` reference syntax
  resolve a value an earlier step in the same scenario produced; a reference to a step later in
  the same scenario is a gap, not a forward declaration.
- a book value means one thing on every driver: a `name:` is the words the element announces,
  in any case and with surrounding punctuation, a `name:` with a `{hole}` is a template whose
  holes stand for any text, and a check's `text=` is a literal piece of what the element shows,
  matched case for case. The harness renders that meaning once per driver: Python patterns for
  the browser, and `maestro_pattern` for a Maestro flow, whose `text:` is a full-match Java
  regex. A value holding a reference such as `@fixture.key` or `$capture` exists only at run
  time, so the compiler writes `${OKF_REF_n}` into the flow and the scenario hands the resolved,
  rendered value to `qa.maestro.run(..., env=...)`. A flow that still holds an unrendered hole or
  reference is a compiler defect, and the compile raises. A claim Maestro cannot observe, such as
  `visible(count=)` or a `fill` value with a hole in it, is a gap.
- rule: an interaction is performed the same way on every driver: its `arrange:` acts in order, then
  its trigger as the act it names, so a `fill(value=...)` trigger types the value and a
  `press(key=...)` trigger presses the key. The book fixes what an interaction does, through
  `step_acts` and `trigger_act`; a driver only spells each act, and one that cannot spell an act
  files `uncompilable-claim` and compiles nothing for that interaction. A phone scenario and a
  phone journey step therefore fill a form before they tap its submit control.
- an absence on the phone means "below the fold" only once the screen has drawn: Maestro's
  `launchApp` returns before the app's first frame, so the first look of a launching flow waits
  up to 15 seconds for its control with an optional `extendedWaitUntil`, and only then scrolls
  for it. A look after a tap scrolls at once, because the tap already waited for the screen to
  settle.
- rule: a phone flow finds a control by searching below the viewport and then above it, because a
  device driver sees only the drawn viewport and the viewport may sit anywhere in the content.
  The downward search is optional, so a control above the viewport falls through to the upward
  search instead of failing the flow.
- rule: a phone flow and the device vet find an element by its name as any line of what the
  phone reads for it, because the phone merges the text of widgets with no semantics of their own
  into one reading, joined by line breaks in tree order, and reads a control as its name followed
  by more lines, such as a tab's position. A field's name is the part before its hint or error
  after a comma. The browser driver keeps matching the accessible name alone.
- rule: a field's held value is checked with `value()` on every platform. On the phone the flow
  copies the value from the field and compares it, with `equals` as an exact match and `matches`
  as a regular-expression search. A phone field keeps its name and its value in separate
  attributes, so no text selector reads both, and `value(equals="")` is refused there because an
  empty field reads as its label.
- rule: a text field is never checked with `visible(text=)`. A field shows its content as a value and
  never as text, so doctor refuses that check on a `textbox` or `searchbox` component with
  `text-of-a-field`, and the check is `value(locator=..., equals=...)` instead.
- generated names are unique: every `*_function_name` helper in `plan_source.py` is given the
  full set of already-emitted names (`EmittedScenarios`) and never returns one already used in
  the same plan.
