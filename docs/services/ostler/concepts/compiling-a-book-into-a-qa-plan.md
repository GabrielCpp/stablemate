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
assertion (`read_back`); `http_walk` compiles an HTTP-only journey the same way. A claim that states no status expects the one its siblings on the same request state, whether or not the request carries an act, so a body check on a refusal reads the refusal. `compile_cli.py`'s
`cli_scenario_body` runs the book's CLI binary as a subprocess and asserts on its exit status or
captured stdout, deciding first whether a check is about the file tree before or after
(`reads_the_tree`, `compares_the_tree`); `cli_journey` and `cli_move_walk` compile a CLI-driven
journey or state walk. `_run_arguments` assembles every emitted `.run(...)` call's keyword
arguments — `argv`, `cwd=qa.scenario_checkout_copy()`, and, when the act declares `env:`,
`env=qa.scenario_env(...)` — so a step's or scenario's subprocess call carries whatever
environment the book's `invoke` act names, in both `cli_scenario_body` and `cli_journey`. `compile_page.py`'s `page_scenarios` builds a web-UI check, holding a
conditional or mutually-exclusive component's obligations together (`_node_claims`,
`_shared_shape`) and inserting a navigation step before the assertion when the obligation is not
already on the right screen (`_arrival_scenario`). When the walk's acts read a fixture's fact, the scenario arranges that fixture once before the first navigation, merged with the fixtures the claims carry. Components that declare different fixtures get separate arrival scenarios (`_plain_arrivals`). A component whose screen opens in a state that lists it `absent` is gapped as `unarranged-state` instead of asserted on arrival, and the gap names the states that show it. `web_state_walks` compiles a `DataState`
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

- code: ostler/ostler/qa/compile.py::compile_plan@e469fe41e5de
- code: ostler/ostler/qa/compile.py::compile_plan_gaps@1c70c4235a8d
- code: ostler/ostler/qa/compile.py::cmd_compile_plan@a0f77ff012ce
- code: ostler/ostler/qa/compile.py::_plan_header@1df6921235ab
- code: ostler/ostler/qa/compile.py::compiled_from_the_book@dedfe53e8b6d
- code: ostler/ostler/qa/compile_http.py::api_scenarios@4dc4547ef07a
- code: ostler/ostler/qa/compile_http.py::http_walk@62469eaf0f71
- code: ostler/ostler/qa/compile_http.py::read_back@2eba39db5fe6
- code: ostler/ostler/qa/compile_cli.py::cli_scenario_body@b17165cba10a
- code: ostler/ostler/qa/compile_cli.py::cli_journey@afb3667f295c
- code: ostler/ostler/qa/compile_cli.py::_run_arguments@51585c8ef3f6
- code: ostler/ostler/qa/compile_cli.py::invoke_env_names@cab445496b1b
- code: ostler/ostler/qa/compile_page.py::page_scenarios@fba8efba86f1
- code: ostler/ostler/qa/compile_page.py::web_state_walks@8e3a88f1d3a8
- code: ostler/ostler/qa/compile_playwright.py::perform_acts@b1e0dd466b28
- code: ostler/ostler/qa/compile_playwright.py::page_observations@e610be86684b
- code: ostler/ostler/qa/compile_playwright.py::web_walk@40e28af83b41
- code: ostler/ostler/qa/compile_maestro.py::mobile_scenarios@3f09b3d2d52d
- code: ostler/ostler/qa/compile_maestro.py::maestro_walk@6bb3e55179b5
- code: ostler/ostler/qa/harness/ostler_qa_elements.py::maestro_pattern@224915efaaf0
- code: ostler/ostler/qa/harness/ostler_qa.py::Maestro@b5e05dbd5366
- code: ostler/ostler/qa/compile_moves.py::move_walks@c8463448d0ef
- code: ostler/ostler/qa/compile_moves.py::state_walks@5e62aca2c37f
- code: ostler/ostler/qa/compile_journey.py::journey_target@bab75359ba6d
- code: ostler/ostler/qa/compile_journey.py::api_target@20652e710dad
- code: ostler/ostler/qa/compile_journey.py::journey_scenarios@a83239a8b983
- code: ostler/ostler/qa/compile_journey.py::journey_scenario@08d7dd7c2661
- code: ostler/ostler/qa/compile_stops.py::resolve_stop@d296755be9b1
- code: ostler/ostler/qa/compile_stops.py::resolve_state@0cd0a5f9d41c
- code: ostler/ostler/qa/compile_stops.py::ScreenStop@8946299e4550
- code: ostler/ostler/qa/compile_support.py::unobservable_gap@8fa6d6b4555a
- code: ostler/ostler/qa/compile_support.py::vettable@fb6ad09a98f2
- code: ostler/ostler/qa/compile_support.py::check_document@e58546e37917
- code: ostler/ostler/qa/plan_source.py::Gap@d9fcecfd2b4b
- code: ostler/ostler/qa/plan_source.py::ScenarioRefusal@7f7a2c2cefe2
- code: ostler/ostler/qa/plan_source.py::python_literal@cb8bccf55a79
- code: ostler/ostler/qa/plan_source.py::arrangement_of@9dcaf902b06a
- code: ostler/ostler/qa/obligation.py::Obligation@8aa729c4f7da
- code: ostler/ostler/qa/obligation.py::obligation_of@b558662c2212
- code: ostler/ostler/qa/obligation.py::obligations_of@103f496c84c3
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@1d8c8dad0e49
- code: ostler/ostler/qa/obligation_frame.py::obligation_frame@32a66096777d
- code: ostler/ostler/qa/obligation_frame.py::BookNode@89d602494fca
- code: ostler/ostler/qa/book_index.py::BookIndex@eea59e696855
- code: ostler/ostler/qa/book_index.py::node_acts@734a965ada9c
- code: ostler/ostler/qa/book_fixtures.py::resolved@c2327c8c4431
- code: ostler/ostler/qa/journey_steps.py::journey_steps@348541ac03a5
- code: ostler/ostler/qa/fixture_provides.py::closure@bdd1adf2dc1d
- code: ostler/ostler/qa/fixture_provides.py::index@5cf4090d392b
- code: ostler/ostler/qa/fixture_browser.py::browser_step@190da9181967
- code: ostler/ostler/qa/navigation.py::navigation_rows@4df2fbcf356b
- code: ostler/ostler/qa/navigation.py::maestro_launch@cf1797f85188
- code: ostler/ostler/qa/readiness.py::cmd_compile_gaps@f2be3f75e500
- code: ostler/ostler/qa/readiness.py::defect_gaps@ee9178710def
- rule: a fixture's condition belongs to the claim that declared it, so a compiled arrival never holds two claims with different fixtures. Two arms of one fault fixture replace each other, and the first claim would read a state nobody declared.
- rule: a body claim and a status claim about one request are read off one response, with or without an act. A body claim that made the driver raise on the stated refusal would never be read.
- tests: ostler/tests/test_qa_readiness.py::test_compile_gaps_reads_the_same_missing_component_checks_the_workflow_rejects
- detail: [ostler](../cli.md)

## Contract

- one driver per obligation: `dispatch_target` (see
  [Running and reporting a QA run](running-and-reporting-a-qa-run.md)) picks exactly one of
  cli/http/web/maestro for an obligation before any `compile_*` backend sees it; a backend never
  chooses its own driver.
- a refusal is not an error: `Gap` and `ScenarioRefusal` are ordinary return values threaded back
  up to `compile_plan`, which reports them in the plan's debt section rather than raising, so a
  compile always finishes with a plan, even a partial one.
- rule: `compile-plan` reporting `passed` means it emitted a plan, possibly a partial one. It is
  not the book-readiness verdict. `ostler qa compile-gaps` applies the acceptance policy to a
  refreshed packet and an explicit set of touched pages: discharged preconditions and unchecked
  node placeholders are exempt, while every other gap on those pages is blocking. The coder
  documentation writer and its workflow call this same policy, so neither invents a different
  filter for missing checks.
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
- rule: an HTTP page's claims share one scenario, except a claim that names a fixture with
  `lifetime: scenario`, which runs in a scenario of its own. Such a fixture holds a condition one
  request can consume, such as an account with no list yet, and the harness builds it once per
  scenario. A second claim in the same scenario would read what the first claim's request left.
- rule: a fixture never fixes an id. Every record a fixture creates takes the id the product
  assigns, or one the step generates as it runs, such as a uuid or a timestamp, and the fixture
  provides it with `from:`/`read:`. Fixtures compose on one copy of the stack, and two that write
  the same literal id rewrite each other's rows, so a scenario passes or fails by build order.
  Doctor refuses a step whose `run:` or `body:` writes a literal id, and a `provides:` id that is
  asserted with `is:`, as `fixture-fixed-id`.
- generated names are unique: every `*_function_name` helper in `plan_source.py` is given the
  full set of already-emitted names (`EmittedScenarios`) and never returns one already used in
  the same plan. A page with several scenarios on one target numbers the names after the first.
- rule: `compile-plan --cover AC=ID[,ID...]` is how an acceptance criterion reaches a compiled
  plan. The packet holds no link from a criterion to an obligation, so the owner states which
  obligations prove each criterion, and the compiler appends the criterion to the `covers=` of
  every compiled check that covers one of them and of the scenario holding that check. The
  rewrite is made on the plan's syntax tree, keeps each list free of duplicates and in a stable
  order, and runs after `--select`. A criterion the packet does not list, an id that matches no
  owed obligation, an id that compiled to no check in this plan and a malformed argument each fail
  by naming the value, and nothing is written. A criterion no obligation proves is not
  covered, and the owner writes a scenario for it.
- rule: the banner `compile-plan` writes on a plan's first line is the plan's provenance, and
  `compiled_from_the_book` reads it. A plan that opens with the banner carries the book's
  `covers=`. A plan that lacks it was written by hand, its `covers=` are its author's, and a
  stage that must prove the book's obligations compiles the book beside it instead of trusting
  them. A plan's existence and its validity say nothing about where it came from.
