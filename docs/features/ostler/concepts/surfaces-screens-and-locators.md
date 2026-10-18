---
type: concept
slug: surfaces-screens-and-locators
title: Surfaces, screens and locators
---
# Surfaces, screens and locators

`pages.py`'s `files_in_book` lists every markdown file under a book's doc roots, skipping a
folder `in_hidden_folder` reports as hidden (a dotted directory, a run's own working copy); it is
the file-listing primitive several of the walks below start from rather than owning a check of
its own.

`routes.py` is the grammar a screen's or endpoint's address is checked against: `is_path_shaped`,
`is_screen_name_shaped` and `is_never_routed` classify one `route:` value, `route_grammar` and
`is_path_addressed` pick which grammar applies for a given `driver:`, `literal_route` and
`entry_address` normalize a route to its canonical form, `route_pattern`/`arrival_regex` compile
a route (possibly carrying other routes' placeholders, via `others`) into a matcher, `arrived_at`
tests a live URL against it, and `why_unreadable`/`_excerpt` explain a route that cannot be
parsed at all. `screen_routes` and `vet_routes` collect every screen's route across the graph, and
`is_comparable`/`performable_surface_types` report which surface kinds a route check or an act
even applies to. `page_size.py`'s `check_page_size` is a single, unrelated rule: it flags a page
that has grown too large to stay one file, the trigger `carve.py`'s endpoint split and
`fragment_carve.py`'s fragment split exist to resolve.

`section_hosts.py`'s `check_section_hosts` and `fragment_hosts.py`'s `check_fragment_hosts`
validate the two ways a smaller piece of UI nests inside a larger page: `check_section_hosts`
checks a `## Heading`-hosted component belongs under a heading its type is allowed to appear
under, and `check_fragment_hosts`' `host_type`/`_hosts`/`_links` instead check a fragment's own
page is actually linked from every page that claims to host it, so a fragment carved out by
`fragment_carve.py` cannot drift from the pages that still reference it.

`passages.py` models a flow as a sequence of states a journey passes through rather than as a
list of steps: `trace` and `Trace` walk a sequence of `(node, state)` steps against the
`Passage`/`Stop` a screen declares, and `passage_of`/`passages_of` build the `Passage` a journey
step actually lands in. The bulk of the file is the checks this model enables, each appending to
a shared `list[Finding]`: `_check_ends`/`_check_steps`/`_check_run_steps`/`_check_requests`
validate a flow's own step sequence is well-formed; `_check_inputs`/`_missing_inputs` and
`_check_flow` cross-reference what a step captures (`_captured_by`) against what a later step
needs; `_check_settled`/`_check_stateful` validate a flow ends on a state the book actually
declares; `_check_perceivable`/`_perceived`/`_unperceivable`/`_selector` validate every component
a flow interacts with is reachable by a real locator. `joint_before`/`joint_after`/`unarranged`
render the English message one of these checks attaches to its finding.

`locators.py` is the grammar and uniqueness model behind every `press:`/`read:`/`fill:` target:
`Locator` and `locator_for` resolve a node's declared selector into the typed shape a driver can
act on; `LocatorBook` indexes every locator in the graph, scoped by `repeat:` context
(`_scopes`); `CompiledName`/`compile_template`/`name_pattern` turn a `{field}`-templated locator
name into a matcher; `RepeatContract`/`repeat_contract`/`repeat_of`/`unique_by_of`/`variants_of`
read a repeated component's uniqueness contract off its bullets. The rest of the file is the
checks `LocatorBook` enables: `collisions`/`collision_remedy` finds two locators that could match
the same element; `invalid_roles`, `malformed_identity`/`malformed_templates`, `prose_names`,
`static_templates`, `unproven_unique_names`, `templates_outside_repeat`, `invalid_variants` and
`unnamed_interactives` each flag one specific way a locator can be malformed; `build`/`render`/
`render_json` assemble and print the full locator report for a surface or screen.
`locator_findings.py` is the sibling module declaring the dataclass each of those checks returns
— `LocatorCollision`, `InvalidRole`, `ProseName`, `StaticTemplate`, `UnprovenUniqueName`,
`MalformedTemplate`, `TemplateOutsideRepeat`, `InvalidVariants` and `UnnamedInteractive` — kept
apart from `locators.py` itself so the shape of a locator finding carries no dependency on the
`LocatorBook` machinery that produces one.

`selector_forms.py` and `accessible_names.py` are the lower-level selector grammar `locators.py`
builds on. `selector_forms.py`'s `parse_scheme_selector` splits a `scheme:value` selector into its
parts, and `is_addressable`/`is_web_representable`/`is_mobile_representable`/`is_never_selected`
and `selector_grammar` classify which drivers can act on a given selector scheme at all.
`accessible_names.py`'s `literal_name` and `prose_mark` are smaller still: they decide whether an
accessible-name value is a literal string or must be read live off the rendered page.

`acts.py` is the `acts:` bullet's own check-expression-style grammar, parsed the same way
`checks.py` parses a `verify:` bullet: `ActSpec`/`ActParam` declare one act's name and typed
parameters, `parse_act` parses a raw string into an `ActCall` or a `Refusal` (`_not_an_act`,
`_unknown`), `bind` resolves a parsed call's arguments, `vocabulary` lists every known act name,
and `is_act_expression` tests whether a string is one at all. `answers.py` parses a different
bullet shape, a review's `answers:` block: `Answer` and `AnswerList` hold one answered question
and the list a review carries, `parse_answers` parses the block's markdown, `_heading` and
`_collect_evidence` read one answer's heading and supporting evidence, and `_reason`/
`_reason_start`/`_unquoted` extract the free-text reason attached to an answer.

`data_states.py` and `data_state_ledger.py` model a flow's effect on persisted data rather than
on screens. `data_states.py`'s `DataState` and `Move` are a declared data shape and a named
transition between two of them; `data_state_of`/`data_states_of` build every `DataState` a book
declares, `moves_of`/`moves_table` collect the moves a node makes, and `siblings_of` finds the
other states a `Move` could have landed in instead. `told_apart` and the checks built on it
(`_check_sends`, `_check_when`, `_check_state`, `_check_moves`, `_check_distinct`,
`check_data_states`) validate that two data states a book claims are different are actually
distinguishable by some check, reading a state's own declared `verify:` calls back out via
`_calls`/`_field`/`_expected`. `state_obligation_id`/`move_obligation_id`/`anchor_of`/`of_of` mint
the stable ids a compiled scenario (see
[Compiling a book into a QA plan](compiling-a-book-into-a-qa-plan.md)) binds a data-state
obligation to. `data_state_ledger.py` walks one flow's steps in order rather than checking a
declared state in isolation: `initial_ledger`/`_walk` build the `Ledger` of what has been written
and sent so far at each `LedgerStep`/`LedgerStop`, `_apply`/`_send`/`_set` update it one step at a
time, and `_check_flow`/`_check_stops`/`check_conditions` flag a step that reads a record before
anything in the flow has written it, or sends on a condition the ledger up to that point cannot
satisfy.

- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/pages.py::in_hidden_folder@e9f96e7b3156
- code: ostler/ostler/routes.py::is_path_shaped@778f9d4fb9ed
- code: ostler/ostler/routes.py::route_grammar@778f9d4fb9ed
- code: ostler/ostler/routes.py::route_pattern@778f9d4fb9ed
- code: ostler/ostler/routes.py::arrival_regex@778f9d4fb9ed
- code: ostler/ostler/routes.py::arrived_at@778f9d4fb9ed
- code: ostler/ostler/routes.py::screen_routes@778f9d4fb9ed
- code: ostler/ostler/routes.py::vet_routes@778f9d4fb9ed
- code: ostler/ostler/routes.py::performable_surface_types@778f9d4fb9ed
- code: ostler/ostler/page_size.py::check_page_size@91b84d86b7a8
- code: ostler/ostler/section_hosts.py::check_section_hosts@f8458f69db47
- code: ostler/ostler/fragment_hosts.py::check_fragment_hosts@908846415586
- code: ostler/ostler/fragment_hosts.py::host_type@908846415586
- code: ostler/ostler/passages.py::trace@7b055a542ea9
- code: ostler/ostler/passages.py::Trace@7b055a542ea9
- code: ostler/ostler/passages.py::passage_of@7b055a542ea9
- code: ostler/ostler/passages.py::passages_of@7b055a542ea9
- code: ostler/ostler/passages.py::check_passages@7b055a542ea9
- code: ostler/ostler/locators.py::Locator@4e770b42dfdc
- code: ostler/ostler/locators.py::locator_for@4e770b42dfdc
- code: ostler/ostler/locators.py::LocatorBook@4e770b42dfdc
- code: ostler/ostler/locators.py::repeat_contract@4e770b42dfdc
- code: ostler/ostler/locators.py::collisions@4e770b42dfdc
- code: ostler/ostler/locators.py::invalid_roles@4e770b42dfdc
- code: ostler/ostler/locators.py::build@4e770b42dfdc
- code: ostler/ostler/locators.py::render@4e770b42dfdc
- code: ostler/ostler/locator_findings.py::LocatorCollision@7318d29e242e
- code: ostler/ostler/locator_findings.py::InvalidRole@7318d29e242e
- code: ostler/ostler/locator_findings.py::UnnamedInteractive@7318d29e242e
- code: ostler/ostler/selector_forms.py::parse_scheme_selector@f340cabcc2d7
- code: ostler/ostler/selector_forms.py::selector_grammar@f340cabcc2d7
- code: ostler/ostler/selector_forms.py::is_web_representable@f340cabcc2d7
- code: ostler/ostler/accessible_names.py::literal_name@e34b952636fb
- code: ostler/ostler/accessible_names.py::prose_mark@e34b952636fb
- code: ostler/ostler/acts.py::ActSpec@0c9fb4bab2b6
- code: ostler/ostler/acts.py::ActCall@0c9fb4bab2b6
- code: ostler/ostler/acts.py::parse_act@0c9fb4bab2b6
- code: ostler/ostler/acts.py::bind@0c9fb4bab2b6
- code: ostler/ostler/acts.py::vocabulary@0c9fb4bab2b6
- code: ostler/ostler/acts.py::is_act_expression@0c9fb4bab2b6
- code: ostler/ostler/answers.py::Answer@6c168f1fb49d
- code: ostler/ostler/answers.py::AnswerList@6c168f1fb49d
- code: ostler/ostler/answers.py::parse_answers@6c168f1fb49d
- code: ostler/ostler/data_states.py::DataState@06a62f37cb1d
- code: ostler/ostler/data_states.py::Move@06a62f37cb1d
- code: ostler/ostler/data_states.py::data_state_of@06a62f37cb1d
- code: ostler/ostler/data_states.py::data_states_of@06a62f37cb1d
- code: ostler/ostler/data_states.py::moves_of@06a62f37cb1d
- code: ostler/ostler/data_states.py::told_apart@06a62f37cb1d
- code: ostler/ostler/data_states.py::check_data_states@06a62f37cb1d
- code: ostler/ostler/data_states.py::state_obligation_id@06a62f37cb1d
- code: ostler/ostler/data_states.py::move_obligation_id@06a62f37cb1d
- code: ostler/ostler/data_state_ledger.py::initial_ledger@932372d84505
- code: ostler/ostler/data_state_ledger.py::ledger_steps@932372d84505
- code: ostler/ostler/data_state_ledger.py::ledger_stops@932372d84505
- code: ostler/ostler/data_state_ledger.py::check_conditions@932372d84505
- code: ostler/ostler/data_state_ledger.py::LedgerStep@932372d84505
- code: ostler/ostler/data_state_ledger.py::LedgerStop@932372d84505
- detail: [Compiling a book into a QA plan](compiling-a-book-into-a-qa-plan.md)
- detail: [ostler](../cli.md)

## Contract

- a selector is graded by driver before it is graded by uniqueness: `selector_forms.py` decides
  whether a driver can act on a selector's scheme at all, before `locators.py` ever asks whether
  that selector is unique enough to be a safe target.
- a ledger step never reads ahead: `data_state_ledger.py`'s `_walk` builds a `Ledger` strictly in
  the flow's declared step order, so a check it runs can only flag a read that precedes its write
  in that same order, never one later in the flow.
- `acts:` and `verify:` share one parsing shape: `acts.py`'s `parse_act`/`bind` mirror `checks.py`'s
  `parse_check`/`bind` exactly, so an act and a check fail to parse (`Refusal`) the same way.
- a fragment host check is a link check, not a nesting check: `check_fragment_hosts` validates
  that every page claiming to host a fragment actually links to it; `check_section_hosts` is the
  separate check for a heading a component type may nest under.
