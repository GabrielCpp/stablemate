---
type: concept
slug: book-health-coverage-reach-and-census
title: 'Book health: coverage, reach and census'
---
# Book health: coverage, reach and census

`finding.py`'s `Finding` is the one record every check in the book shares to report a problem —
a message and a fix, appended to the `list[Finding]` a check function threads through — and every
module in this page, like most of `doctor.py`'s other rule modules, ends in a function that fills
one.

`inventory.py` is the generic, multi-language symbol table the citation and audit checks read
instead of each re-parsing source themselves: `symbols`/`declared_names`/`declares` report what a
file exports or declares in whichever of Python (`parse_python`, `_py_surface`, `_py_declared`,
with `_py_recovered_surface`/`_py_recovered_declared` as a fallback when `ast` cannot parse the
file at all), Go (`_go_receiver`, `_go_embedded_name`, `_go_member_names`, `_go_symbols`),
tree-sitter-backed languages (`_ts_pattern_names`, `_ts_declaration_names`, `_ts_surface`,
`_ts_declared`), PHP (`_php_symbols`) or Twig (`_twig_blocks`) it is written in; `symbol_parts`
and `_grounds` decide whether a dotted citation like `Class::method` is grounded by what
`declared_names` found. `declared_names_at`/`declares_at`/`_table_at` cache this per path through
a `_SymbolTable` keyed by `index.py`'s content hash (`_symbol_key`, `_extracted`), and
`import_origin`/`_import_bases` resolve a bare import statement to the file it actually names.
`extents`/`symbol_digests`/`symbol_digests_at` go one step further, finding each declaration's own
line span (`_py_extents`, `_tree_declarations`, `_go_declarations`, `_ts_declarations`,
`_php_declarations`, with `_py_recovered_extents`/`_py_recovered_declarations` as the AST-failure
fallback) and hashing just that span (`_token_digest`, `_py_digests`, `_twig_digests`) so a
citation's `@hash` can be checked against the one declaration it names rather than the whole
file. `imports_of`/`_py_imports`/`_go_imports`/`_ts_imports`, with
`_py_recovered_imports` again as the fallback, report what a file imports, the input `reach.py`'s
navigation walk and `book_reach.py`'s dead-page walk both start from.

`coverage.py` answers "is everything inventory.py can see actually cited by some page":
`citations` collects every `code:`/`tests:` reference the graph makes, `load_inventory` and
`load_waivers` read the external file listing which source units should be checked and which are
explicitly exempted, `compute` (via `_module_is_covered`) cross-references the two,
`is_complete` reports a clean result, `render` prints it, and `run`/`cmd_coverage` are the
command entry points. `backfill.py` picks up where an incomplete `coverage.py` result stops:
`plan`'s `BackfillPlan` proposes, for every `StaleUnit` coverage flags as uncovered
(`_uncovered`) or every finding left dangling by a citation that no longer resolves (`_dangling`),
either a new page to scaffold or an existing one already covering a related symbol
(`_already_documented_elsewhere`, `_mark_relocated`, `_symbol_of`), scoped to the directories
`_in_scope` is given; `render` prints the plan.

`census.py`'s `take_census` runs a given callable (typically the test suite, or one invocation of
a tool under test) and records which lines of a given set of modules it actually executed, via
`code_sites`/`_module_sites`'s per-module site index; `Census` holds one run's result and `merge`
combines several into one; `render` prints it. This is a runtime coverage census of the book's
own tooling, distinct from `coverage.py`'s static citation coverage of the book's subject.

`reach.py` and `book_reach.py` both ask "what can actually be reached", from two different
starting points. `reach.py`'s `reachability`/`reachability_in` walk a screen graph's declared
`route:`/navigation bullets forward (`navigation_edges`, `preconditions`, `route`, `_through_a_door`)
from a `resolve_start` starting screen, reporting `unreachable_screens` and rendering the shortest
`route_entries` path to any screen (`render_route`, `render_reachability`); `surface_runbooks`,
`surface_driver`, `surface_bundle_id`, `surface_launch_screen` and `root_screen`/`surface_root`
read a surface's own launch configuration to seed that walk, and `url_origin`/`url_path`/
`is_route`/`_norm_path` normalize a URL or path value along the way. `book_reach.py` instead
starts from the book's entry points and walks forward through markdown links rather than through
declared routes: `_book_pages`/`BookPages` and `_linked_pages` build the link graph, `fixture_edges`
adds a fixture's own reachability edges, and `dead_pages` reports a `DeadPage` nothing links to;
`delete_pages` removes one.

`hidden_claims.py`'s `check_hidden_claims` flags a normative-sounding claim written into an
ordinary prose sentence or HTML comment instead of a declared bullet (`_hidden`, against the
`_claim_keys` vocabulary) — a claim that looks checked to a human reader but that no `verify:`
bullet actually proves. `step_commands.py` validates a flow step's shell-command bullets rather
than its prose: `check_step_command_bullets`/`check_step_command_syntax` validate a step's
command is well-formed, `check_step_command_checkout_path` validates a path argument stays inside
the step's own checkout, `check_fixture_step_directory`/`check_fixture_step_serves` validate a
fixture step's working directory, a `repo://<member>/<path>` one in that member's checkout, and what it claims to serve, `check_step_not_scenario_frame`
flags a step command that duplicates what a scenario's own frame already provides, and
`check_fixture_probe_remote` validates a fixture's health-check probe target.

- code: ostler/ostler/finding.py::Finding@9ff7be48f3bd
- code: ostler/ostler/inventory.py::symbols@fc37414c2b8a
- code: ostler/ostler/inventory.py::declared_names@fc37414c2b8a
- code: ostler/ostler/inventory.py::declares@fc37414c2b8a
- code: ostler/ostler/inventory.py::declared_names_at@fc37414c2b8a
- code: ostler/ostler/inventory.py::declares_at@fc37414c2b8a
- code: ostler/ostler/inventory.py::import_origin@fc37414c2b8a
- code: ostler/ostler/inventory.py::imports_of@fc37414c2b8a
- code: ostler/ostler/inventory.py::extents@fc37414c2b8a
- code: ostler/ostler/inventory.py::symbol_digests@fc37414c2b8a
- code: ostler/ostler/inventory.py::symbol_digests_at@fc37414c2b8a
- code: ostler/ostler/inventory.py::symbol_parts@fc37414c2b8a
- code: ostler/ostler/coverage.py::citations@2e691370b1e7
- code: ostler/ostler/coverage.py::load_inventory@2e691370b1e7
- code: ostler/ostler/coverage.py::load_waivers@2e691370b1e7
- code: ostler/ostler/coverage.py::compute@2e691370b1e7
- code: ostler/ostler/coverage.py::is_complete@2e691370b1e7
- code: ostler/ostler/coverage.py::cmd_coverage@2e691370b1e7
- code: ostler/ostler/backfill.py::plan@e3c3cac49def
- code: ostler/ostler/backfill.py::render@e3c3cac49def
- code: ostler/ostler/backfill.py::StaleUnit@e3c3cac49def
- code: ostler/ostler/backfill.py::BackfillPlan@e3c3cac49def
- code: ostler/ostler/census.py::take_census@bde18842fcce
- code: ostler/ostler/census.py::Census@bde18842fcce
- code: ostler/ostler/census.py::merge@bde18842fcce
- code: ostler/ostler/census.py::code_sites@bde18842fcce
- code: ostler/ostler/census.py::render@bde18842fcce
- code: ostler/ostler/reach.py::reachability@a7af9ddc3e32
- code: ostler/ostler/reach.py::unreachable_screens@a7af9ddc3e32
- code: ostler/ostler/reach.py::route@a7af9ddc3e32
- code: ostler/ostler/reach.py::navigation_edges@a7af9ddc3e32
- code: ostler/ostler/reach.py::resolve_start@a7af9ddc3e32
- code: ostler/ostler/reach.py::render_reachability@a7af9ddc3e32
- code: ostler/ostler/book_reach.py::dead_pages@76220c84992e
- code: ostler/ostler/book_reach.py::delete_pages@76220c84992e
- code: ostler/ostler/book_reach.py::DeadPage@76220c84992e
- code: ostler/ostler/book_reach.py::fixture_edges@76220c84992e
- code: ostler/ostler/hidden_claims.py::check_hidden_claims@fbb124432063
- code: ostler/ostler/step_commands.py::check_step_command_bullets@a44a1ff496dd
- code: ostler/ostler/step_commands.py::check_step_command_syntax@a44a1ff496dd
- code: ostler/ostler/step_commands.py::check_fixture_step_directory@a44a1ff496dd
- code: ostler/ostler/step_commands.py::check_fixture_step_serves@a44a1ff496dd
- code: ostler/ostler/step_commands.py::check_step_not_scenario_frame@a44a1ff496dd
- code: ostler/ostler/step_commands.py::check_fixture_probe_remote@a44a1ff496dd
- detail: [The book's markdown model](the-books-markdown-model.md)
- detail: [ostler](../cli.md)

## Contract

- one symbol table, many callers: `coverage.py` and
  [Auditing a book's claims against source](auditing-a-books-claims-against-source.md)'s
  `behavior.py` both read a file's declared names through `inventory.py` rather than parsing it
  themselves, so a citation check and a behavior audit never disagree about what a file declares.
- coverage is static, census is dynamic: `coverage.py` asks whether a citation exists at all;
  `census.py` asks whether a line actually ran during a given execution; neither reads the
  other's result.
- reach is driver-first, book_reach is link-first: `reach.py` walks declared `route:` bullets a
  driver would actually follow; `book_reach.py` walks markdown links a human reader would follow;
  a screen unreachable by one can still be linked by the other.
- a hidden claim is a missing bullet, not a wrong one: `check_hidden_claims` only flags prose that
  reads as a claim with no corresponding bullet; a claim already written as a bullet, right or
  wrong, is some other check's finding.
