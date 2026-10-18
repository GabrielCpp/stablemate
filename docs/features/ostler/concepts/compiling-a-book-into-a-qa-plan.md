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
`check_document`/`trigger_name`/`on_href` render one check call's book-declared arguments into
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

- code: ostler/ostler/qa/compile.py::compile_plan@08cf0153b44e
- code: ostler/ostler/qa/compile.py::compile_plan_gaps@08cf0153b44e
- code: ostler/ostler/qa/compile.py::cmd_compile_plan@08cf0153b44e
- code: ostler/ostler/qa/compile.py::_plan_header@08cf0153b44e
- code: ostler/ostler/qa/compile_http.py::api_scenarios@7b561de0b90a
- code: ostler/ostler/qa/compile_http.py::http_walk@7b561de0b90a
- code: ostler/ostler/qa/compile_http.py::read_back@7b561de0b90a
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@003bdbe757de
- code: ostler/ostler/qa/compile_cli.py::cli_journey@003bdbe757de
- code: ostler/ostler/qa/compile_cli.py::_run_arguments@003bdbe757de
- code: ostler/ostler/qa/compile_cli.py::invoke_env_names@003bdbe757de
- code: ostler/ostler/qa/compile_page.py::page_scenarios@86e11d4ad1cb
- code: ostler/ostler/qa/compile_page.py::web_state_walks@86e11d4ad1cb
- code: ostler/ostler/qa/compile_playwright.py::perform_acts@0f1323f2699e
- code: ostler/ostler/qa/compile_playwright.py::page_observations@0f1323f2699e
- code: ostler/ostler/qa/compile_playwright.py::web_walk@0f1323f2699e
- code: ostler/ostler/qa/compile_maestro.py::mobile_scenarios@f88c740f3674
- code: ostler/ostler/qa/compile_maestro.py::maestro_walk@f88c740f3674
- code: ostler/ostler/qa/compile_moves.py::move_walks@357b72ed93c7
- code: ostler/ostler/qa/compile_moves.py::state_walks@357b72ed93c7
- code: ostler/ostler/qa/compile_journey.py::journey_target@1dbd04809ecb
- code: ostler/ostler/qa/compile_journey.py::api_target@1dbd04809ecb
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@1dbd04809ecb
- code: ostler/ostler/qa/compile_journey.py::journey_scenario@1dbd04809ecb
- code: ostler/ostler/qa/compile_stops.py::resolve_stop@4daf7645d9c5
- code: ostler/ostler/qa/compile_stops.py::resolve_state@4daf7645d9c5
- code: ostler/ostler/qa/compile_stops.py::ScreenStop@4daf7645d9c5
- code: ostler/ostler/qa/compile_support.py::unobservable_gap@d73966f66e36
- code: ostler/ostler/qa/compile_support.py::vettable@d73966f66e36
- code: ostler/ostler/qa/compile_support.py::check_document@d73966f66e36
- code: ostler/ostler/qa/plan_source.py::Gap@fa73bba2be06
- code: ostler/ostler/qa/plan_source.py::ScenarioRefusal@fa73bba2be06
- code: ostler/ostler/qa/plan_source.py::python_literal@fa73bba2be06
- code: ostler/ostler/qa/plan_source.py::arrangement_of@fa73bba2be06
- code: ostler/ostler/qa/obligation.py::Obligation@f238f8b8f458
- code: ostler/ostler/qa/obligation.py::obligation_of@f238f8b8f458
- code: ostler/ostler/qa/obligation.py::obligations_of@f238f8b8f458
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@c6e8278e4f37
- code: ostler/ostler/qa/obligation_frame.py::obligation_frame@c6e8278e4f37
- code: ostler/ostler/qa/obligation_frame.py::BookNode@c6e8278e4f37
- code: ostler/ostler/qa/book_index.py::BookIndex@cc5b868a3e45
- code: ostler/ostler/qa/book_index.py::node_acts@cc5b868a3e45
- code: ostler/ostler/qa/book_fixtures.py::resolved@360f74516536
- code: ostler/ostler/qa/journey_steps.py::journey_steps@0794ea6c9659
- code: ostler/ostler/qa/fixture_provides.py::closure@9053b42918c0
- code: ostler/ostler/qa/fixture_provides.py::index@9053b42918c0
- code: ostler/ostler/qa/fixture_browser.py::browser_step@d769665467aa
- code: ostler/ostler/qa/navigation.py::navigation_rows@4a5908762bb1
- code: ostler/ostler/qa/navigation.py::maestro_launch@4a5908762bb1
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
- generated names are unique: every `*_function_name` helper in `plan_source.py` is given the
  full set of already-emitted names (`EmittedScenarios`) and never returns one already used in
  the same plan.
