---
type: cli
slug: book-checks
title: ostler book checks
---
# ostler book checks

The read-only half of `ostler`: commands that open a repo's `docs/` book, check it, and report what
they find without changing a file. Every claim here runs against a small repo seeded under the
checkout, with `-C book-scratch`, so the real books never decide the outcome.

- binary: ostler
- code: ostler/ostler/cli.py::main@e56ee756ce4b
- detail: [The book's markdown model](concepts/the-books-markdown-model.md)

## Commands

### ostler-doctor
- usage: ostler doctor [--json] [--path PATH] [--census] — loads the book, runs every referential
  and shape check over it, and prints one line per finding followed by `N error(s), M warning(s)`
  (or the whole outcome as one JSON object with --json). A `grpc-server` page whose `contract:`
  names a folder holding a `.proto` file is held to that contract: each RPC of a service its
  `serves:` bullet names with no `rpc` page is an `rpc-missing` error, and each `rpc` page whose
  `name:` is no RPC of those services is an `rpc-phantom` error. The comparison is exact and
  case-sensitive, and a server without a readable contract gets neither. A `server` page
  whose `contract:` names such a folder is held to the routes its rpcs annotate with a
  `google.api.http` option: each annotated route that no hosted `endpoint` page books by `method:`
  and `path:` is a `route-missing` error, and each `endpoint` page whose method and path the
  contract lacks is a `route-phantom` error. The method compares upper-cased, a `{...}` variable
  matches any other whatever its name, and a custom-verb suffix such as `:read` is part of the
  path. A service whose pages' `code:` bullets cite files of two repositories is a
  `service-spans-repositories` error that names both repositories.
- flags:
  - --json (print `{org, profile, epics, errors, warnings, findings}` as one indented JSON object), --path (check only the book at this path), --census (print the census of the book's nodes instead of the findings)
- exits: 0 — a book whose findings are all warnings, or none, is sound
- run: invoke(argv=["-C", "book-scratch", "doctor", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="errors", equals=0)
- verify: json_path(path="findings[0].severity", equals="warn")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a sound `demo` book whose
  citations carry no digest stamp, so it reports warnings and no error
- code: ostler/ostler/doctor.py::run@ab8462bb5f23
- code: ostler/ostler/doctor.py::_check_service_repository@2122aafa61b2
- code: ostler/ostler/book_reach.py::dead_pages@1b04d3198b2e
- code: ostler/ostler/checks.py::bind@f5907a5ae8cb
- code: ostler/ostler/acts.py::bind@dc8636ce92aa
- code: ostler/ostler/data_state_ledger.py::check_conditions@80a291c0be7d
- code: ostler/ostler/data_states.py::check_data_states@668422249346
- code: ostler/ostler/dynamic_registry.py::as_entity_types@50d7ebcbe638
- code: ostler/ostler/fragment_hosts.py::check_fragment_hosts@051b42c16e2f
- code: ostler/ostler/graph.py::build@31a892ee2146
- code: ostler/ostler/hidden_claims.py::check_hidden_claims@01b52ba2ba67
- code: ostler/ostler/index.py::active@bb6bee252338
- code: ostler/ostler/inventory.py::declared_names_at@e123d35ce9ed
- code: ostler/ostler/links.py::is_doc_link@aa0ea7dd1ae5
- code: ostler/ostler/locators.py::collisions@0885bd23cdd8
- code: ostler/ostler/markdown.py::all_code_spans@ee7716c8d9cd
- code: ostler/ostler/model.py::anchor_of@798e27713414
- code: ostler/ostler/outcome_rules.py::check_outcomes@bcc991ae153c
- code: ostler/ostler/page_size.py::check_page_size@74d1cb1352a4
- code: ostler/ostler/pages.py::files_in_book@2ffb748edb94
- code: ostler/ostler/passages.py::check_passages@70f710b87f89
- code: ostler/ostler/proto_contract.py::read_contract@02d97443644d
- code: ostler/ostler/refs.py::bare_targets@98dad71638c3
- code: ostler/ostler/route_coverage.py::check_route_coverage@d8d1ef63978c
- code: ostler/ostler/rpc_coverage.py::check_rpc_coverage@e0d8fcd394eb
- code: ostler/ostler/registry.py::address_keys@fc0150f3e5ef
- code: ostler/ostler/section_hosts.py::check_section_hosts@195b6d29b004
- code: ostler/ostler/server_membership.py::check_server_membership@d147c9afd673
- code: ostler/ostler/shared_checks.py::check_shared_checks@89a92d7670f2
- code: ostler/ostler/source_snapshots.py::book_repository@50a95918473d
- code: ostler/ostler/stack_checks.py::check_stack@6e19b01a0531
- code: ostler/ostler/syntax.py::grammar_version@785d019e2b70
- code: ostler/ostler/qa/fixture_provides.py::closure@bdd1adf2dc1d
- code: ostler/ostler/qa/fixtures.py::parse_bullet@69e389c684f7
- code: ostler/ostler/qa/journey_steps.py::journey_steps@348541ac03a5
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@1d8c8dad0e49
- code: ostler/ostler/qa/references.py::find_references@72bc7e005145
- code: ostler/ostler/qa/runbook.py::has_served_surface@83c654ab7d92
- code: ostler/ostler/qa/sensitivity.py::report@d9a000f060b1
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@de55f6adfd9d
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@2e9d64d79798
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@254195c1d2aa
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@333a1e67799e
- detail: [Book health: coverage, reach and census](concepts/book-health-coverage-reach-and-census.md)

### ostler-doctor-dangling-link
- usage: ostler doctor --json — reports a link to a page that does not exist as an error finding
  and exits 1, so a caller that gates on the exit status stops on it
- exits: 1 — a book with one error finding fails the check
- run: invoke(argv=["-C", "book-scratch-broken", "doctor", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=1)
- verify: json_path(path="findings[0].code", equals="dangling-link")
- verify: json_path(path="findings[0].path", equals="docs/services/demo/entries.md")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds `book-scratch-broken/`, whose
  entries page links to a page that does not exist
- code: ostler/ostler/doctor.py::run@ab8462bb5f23
- code: ostler/ostler/finding.py::Finding@7a656ee8e8b6
- code: ostler/ostler/markdown.py::comment_blocks@778e6de4247e
- code: ostler/ostler/model.py::doc_roots@cc98ffe30811
- code: ostler/ostler/refs.py::bullet_ref@a1a41caa5b7f

### ostler-checks
- usage: ostler checks [--json] — lists the `verify:` check vocabulary, one entry per check with its
  signature and what it excludes, or the whole table as one JSON array with --json
- flags:
  - --json (print `[{name, signature, params, ...}]` as one indented JSON array)
- exits: 0 — listing the vocabulary reads only the code-declared check table, so this command never
  fails
- run: invoke(argv=["checks", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].name", matches="^[a-z_]+$")
- verify: json_path(path="[0].params[0].name", matches="^[a-z_]+$")
- fixture: none, because the vocabulary is fixed in code and reads no book
- code: ostler/ostler/checks.py::CheckSpec@f334be44b51b

### ostler-checks-one
- usage: ostler checks NAME — prints a note on `within=<seconds>`, which every check that reads a subject accepts, only on a `verify:` row held on an `observe:` observation, and which re-reads the observation until the row holds or the deadline passes, then one check's signature and what it excludes, one line each
- args: name — a check name `ostler checks` lists
- fixture: none, because the vocabulary is fixed in code and reads no book
- exits: 0 — a name the vocabulary declares prints its signature and description
- run: invoke(argv=["checks", "exit_status"])
- verify: exit_status(code=0)
- verify: stdout(matches="exit_status\\(code\\*=<int>\\)")
- verify: stdout(matches="is accepted by every check that reads a subject, and only on a")
- code: ostler/ostler/checks.py::describe@fa25d7e1749e
- code: ostler/ostler/checks.py::WITHIN_PREAMBLE@b3b97ff94fb4
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)

### ostler-audit
- usage: ostler audit PATH... [--max-items N] [--max-chars N] [--tier 1|all] [--json] — extracts
  the declared symbols of each source file, joins them to the book's claims about them, and prints
  bounded review packets, deciding nothing itself
- flags:
  - --max-items (most claims plus candidates per packet), --max-chars (most serialized characters per packet), --tier (1: candidates the book cites or the language exports; all: every candidate), --json (print `{version, status, inventory, packets, ...}` as one indented JSON object)
- args: path — one or more repo-relative source files or directories
- exits: 0 — a parsed source file yields packets and the command reports `prepared`
- run: invoke(argv=["-C", "book-scratch", "audit", "src/demo.py", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="prepared")
- verify: json_path(path="inventory.files[0].status", equals="parsed")
- verify: json_path(path="inventory.files[0].path", equals="src/demo.py")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a source file with two
  functions
- code: ostler/ostler/behavior.py::build_audit_packets@dfe3ced9593c
- code: ostler/ostler/behavior_cli.py::run@bee28451f1ee
- code: ostler/ostler/behavior_models.py::FileExcerpt@5b154a9104d8
- code: ostler/ostler/behavior_python.py::PythonEvidence@c18974dca35b
- code: ostler/ostler/dynamic_registry.py::load_kinds@ca1b93afa65c
- code: ostler/ostler/markdown.py::leading_code_spans@a97eabbfc76a
- code: ostler/ostler/registry.py::normative_keys@57fd51c6a734
- code: ostler/ostler/syntax.py::language_for@5b80fb0f6273
- detail: [Auditing a book's claims against source](concepts/auditing-a-books-claims-against-source.md)

### ostler-audit-go
- usage: ostler audit PATH --json — extracts the declared symbols of a Go source file and prints review packets for them, deciding nothing itself
- args: path — a repo-relative Go source file
- exits: 0 — a parsed source file yields packets and the command reports `prepared`
- run: invoke(argv=["-C", "book-scratch", "audit", "src/greet.go", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="prepared")
- verify: json_path(path="inventory.files[0].path", equals="src/greet.go")
- verify: json_path(path="inventory.candidates[0].symbol", equals="Greet")
- verify: json_path(path="inventory.candidates[0].kind", equals="function_contract")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a Go source file with one function
- code: ostler/ostler/behavior_go.py::GoEvidence@8a19dac567ac
- code: ostler/ostler/behavior_cli.py::run@bee28451f1ee
- detail: [Auditing a book's claims against source](concepts/auditing-a-books-claims-against-source.md)

### ostler-audit-typescript
- usage: ostler audit PATH --json — extracts the declared symbols of a TypeScript source file and prints review packets for them, deciding nothing itself
- args: path — a repo-relative TypeScript source file
- exits: 0 — a parsed source file yields packets and the command reports `prepared`
- run: invoke(argv=["-C", "book-scratch", "audit", "src/greet.ts", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="status", equals="prepared")
- verify: json_path(path="inventory.files[0].path", equals="src/greet.ts")
- verify: json_path(path="inventory.candidates[0].symbol", equals="greet")
- verify: json_path(path="inventory.candidates[0].kind", equals="function_contract")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a TypeScript source file with one function
- code: ostler/ostler/behavior_tree.py::TreeEvidence@370c02185fb4
- code: ostler/ostler/behavior_cli.py::run@bee28451f1ee
- detail: [Auditing a book's claims against source](concepts/auditing-a-books-claims-against-source.md)

### ostler-trace
- usage: ostler trace TOKEN — prints the node a seed id, story slug, surface or doc path names, then
  every link out of it with `[ok]` or `[broken]` and every page that links to it
- args: token — a node id, slug, surface or doc path
- exits: 0 — a token that names a node prints its neighbours
- run: invoke(argv=["-C", "book-scratch", "trace", "entries"])
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^  → docs/services/demo/cli\\.md  \\[ok\\]$")
- verify: stdout(matches="(?m)^  → docs/services/demo/flows/say-hello\\.md  \\[ok\\]$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds an entries page that links the
  cli page and the flow
- code: ostler/ostler/trace.py::run@458721fa8dcb
- code: ostler/ostler/markdown.py::MarkdownDoc@dea72bc55864
- code: ostler/ostler/registry.py::type_of@358aaeed15b3

### ostler-trace-unknown
- usage: ostler trace TOKEN — a token that names no node prints `no node found for '<token>'` and
  exits 1
- args: token — a string no node id, slug, surface or path matches
- exits: 1 — an unknown token is an error, not an empty answer
- run: invoke(argv=["-C", "book-scratch", "trace", "nothing-here"])
- verify: exit_status(code=1)
- verify: stdout(matches="^no node found for 'nothing-here'$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a book no token `nothing-here`
  names
- code: ostler/ostler/trace.py::run@458721fa8dcb

### ostler-explain
- usage: ostler explain NAME — prints five sections in order: the resource page's own text unchanged; a `probe:` line, which reads `probe: GET <path> on <base>` for an `http` resource with `<base>` as the page writes it and `probe: <command> (binary <binary>)` for a `cli` resource; `## Observations` with one `<observation>: <request or command>` line per observation; `## Borrowed by` with one `<fixture>: <step kind> <step id>, ...` line per fixture that has a step on the resource, so a fixture lists its borrow and release steps by id; and `## Claims` with one group per fixture that borrows from the resource, directly or through `needs:`, and one group per `observe:` observation of the resource, each followed by the ids of its claims. Under `## Borrowed by` it prints `no fixture borrows from it` when no fixture has a step on the resource, and under `## Claims` it prints `no claim reads it` when no claim names a borrowing fixture or an observation of the resource
- args: name — a resource's name, which is its page's file stem, or the path of its page
- exits: 0 — a name that matches a resource page prints its explanation
- run: invoke(argv=["-C", "explain-scratch", "explain", "camera-booking"])
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^probe: GET /health on http://booking\\.example\\.internal:8080$")
- verify: stdout(matches="(?m)^leases: GET /leases$")
- verify: stdout(matches="(?m)^no fixture borrows from it$")
- verify: stdout(matches="(?m)^no claim reads it$")
- fixture: [explain scratch repo](fixtures/explain-scratch-repo.md)
- code: ostler/ostler/explain.py::run@1fcc0de8bbfe
- code: ostler/ostler/cli.py::main@e56ee756ce4b
- code: ostler/ostler/qa/book_fixtures.py::resolved_resources@48ca191dff1a
- detail: [Describing an outside system a QA run depends on](concepts/describing-an-outside-system-a-qa-run-depends-on.md)
- tests: ostler/tests/test_explain.py::test_explain_prints_the_five_sections_in_order
- tests: ostler/tests/test_explain.py::test_explain_names_the_claims_that_observe_a_resource

### ostler-explain-unknown
- usage: ostler explain NAME — a name that matches no resource page prints `no resource named '<name>'; ostler search <name> lists what the book holds` on stderr and exits 1
- args: name — a string no resource page's stem, id or path matches
- exits: 1 — an unknown name is an error, not an empty explanation
- run: invoke(argv=["-C", "explain-scratch", "explain", "nowhere"])
- verify: exit_status(code=1)
- verify: stderr(matches="no resource named 'nowhere'")
- fixture: [explain scratch repo](fixtures/explain-scratch-repo.md)
- code: ostler/ostler/explain.py::run@1fcc0de8bbfe
- tests: ostler/tests/test_explain.py::test_an_unknown_resource_exits_one_and_says_how_to_look

### ostler-search
- usage: ostler search QUERY [--type TYPE] [--root ROOT] [--limit N] [--match] [--json] — ranked
  full-text search over every section of every document root, printing one hit per two lines (or
  the hits as one indented array with --json)
- flags:
  - --type (keep the sections of pages with this frontmatter type), --root (keep one document root:
    services, epics, milestones, specs, register or adr), --limit (the most hits to return, 10 by
    default), --match (pass QUERY through as raw FTS5 syntax, and exit 2 when FTS5 cannot parse it), --json (print the hits as one indented
    JSON array)
- args: query — the words to look for, joined with OR and matched as stemmed prefixes
- exits: 0 — a query prints its hits, possibly none
- run: invoke(argv=["-C", "book-scratch", "search", "Say hello", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].type", equals="flow")
- verify: json_path(path="[0].path", equals="docs/services/demo/flows/say-hello.md")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a flow titled "Say hello"
- code: ostler/ostler/textindex.py::TextIndex.search@6845fdf66e03
- detail: [The text index](concepts/the-text-index.md)

### ostler-index-build
- usage: ostler index build [--json] — builds or refreshes the full-text index over every document
  root and prints how many sections and files it holds
- flags:
  - --json (print the counts as one JSON object)
- exits: 0 — the index is current
- run: invoke(argv=["-C", "book-scratch", "index", "build", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="files", matches="^[1-9][0-9]*$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a flow titled "Say hello"
- code: ostler/ostler/textindex.py::TextIndex.refresh@f7d9eee29be9
- detail: [The text index](concepts/the-text-index.md)

### ostler-list
- usage: ostler list --type TYPE [--json] — lists the nodes of one type, one JSON object per line
  (or one indented array with --json)
- flags:
  - --type (the node type to list), --json (print the nodes as one indented JSON array)
- exits: 0 — a known type prints its nodes, possibly none
- run: invoke(argv=["-C", "book-scratch", "list", "--type", "flow", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].type", equals="flow")
- verify: json_path(path="[0].path", equals="docs/services/demo/flows/say-hello.md")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds one flow
- code: ostler/ostler/query.py::list_entities@b6cce43b16aa

### ostler-query
- usage: ostler query KIND ARG [--checkout REPOSITORY=PATH] [--json] — answers a reverse-index
  question about a node: the stories covering a seed, the surfaces a story references, or the story
  and commit a node traces to
- flags:
  - --checkout (a source checkout for exact `Story` trailer queries; repeat per repository), --json (print the answers as one indented JSON array)
- args: kind — one of stories-covering-seed, surfaces-referenced-by-story, story-provenance, commit-story, node-provenance, story-for-node; arg — the id, slug or path the kind asks about
- exits: 0 — a node with no checkout supplied is answered, unresolved, with a warning naming the missing checkout
- run: invoke(argv=["-C", "book-scratch", "query", "story-for-node", "docs/services/demo/cli.md", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].node.id", equals="docs/services/demo/cli.md")
- verify: json_path(path="[0].resolved", equals=false)
- verify: json_path(path="[0].node.codeRefs[0]", equals="src/demo.py::greet")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a cli page that cites
  `src/demo.py::greet`
- code: ostler/ostler/query.py::query@dee579a3cb02
- code: ostler/ostler/provenance.py::checkout_for@c798b5423249

### ostler-graph
- usage: ostler graph [--surface S] [--type T] [--title T] [--path P] [--under ID] [--depth N]
  [--has-bullet KEY] [--bullet KEY=VAL] [--links-to ID] [--orphans] [--tree | --ids | --json] —
  filters the book's node and edge graph and prints it as an outline, bare ids or one JSON object
- flags:
  - --type (nodes of this type), --ids (print one bare node id per line), --json (print the filtered `{counts, nodes, edges}` object), --tree (print an indented outline, the default)
- exits: 0 — a filter that matches nothing prints an empty result
- run: invoke(argv=["-C", "book-scratch", "graph", "--type", "command", "--ids"])
- verify: exit_status(code=0)
- verify: stdout(matches="^docs/services/demo/cli\\.md#demo-greet$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds one command node
- code: ostler/ostler/graph.py::build@31a892ee2146
- code: ostler/ostler/markdown.py::extract_refs@185c57ef4c03

### ostler-reach
- usage: ostler reach [TARGET] [--from ID] [--surface S] [--json] — derives the click path from a
  surface's root screen to a screen, or with no target audits every screen of the surface and lists
  those no click path reaches
- flags:
  - --from (the screen the walk starts on), --surface (scope to one service), --json (print `{start, surface, counts, routes, opens, doors, unreachable, undeclared}` as one JSON object)
- args: target — a screen node id; omit it to audit every screen
- exits: 0 — a surface whose screens are all reachable prints an empty `unreachable` list
- run: invoke(argv=["reach", "--surface", "groom", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="surface", equals="groom")
- verify: json_path(path="counts.unreachable", equals=0)
- fixture: none, because the groom book is tracked in the repo and holds one screen
- code: ostler/ostler/reach.py::literal_entries@9283335c8d5a
- code: ostler/ostler/routes.py::entry_address@dce0a6260cff
- code: ostler/ostler/markdown.py::bullet_text@44779fe79ecf
- code: ostler/ostler/registry.py::base_type@57e382012b26

### ostler-locators
- usage: ostler locators [--surface S] [--json] — builds the Playwright locator of every documented
  control and lists those that collide, carry no name or use an invalid role
- flags:
  - --surface (scope to one service), --json (print `{screens, collisions, unnamed, invalid_roles, ..., counts}` as one indented JSON object)
- exits: 0 — a book whose controls all locate prints empty problem lists
- run: invoke(argv=["locators", "--surface", "groom", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="counts.unlocatable", equals=0)
- fixture: none, because the groom book is tracked in the repo and its controls all locate
- code: ostler/ostler/locators.py::build@ad7a2d40dc98
- code: ostler/ostler/selector_forms.py::parse_scheme_selector@03b1a7ae9044

### ostler-coverage
- usage: ostler coverage --inventory PATH [--surface S] [--waivers PATH] [--json] — joins the
  book's `code:` citations against a source inventory and lists the units no node cites, exiting 1
  while any is missing
- flags:
  - --inventory (the source inventory to diff against), --waivers (adjudicated non-units, keyed by `code:` target), --surface (scope to one service), --json (print `{covered, total, waived, missing, ...}`)
- exits: 1 — an inventory with a unit the book does not cite is incomplete
- run: invoke(argv=["-C", "book-scratch", "coverage", "--inventory", "book-scratch/inventory.json", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="covered", equals=1)
- verify: json_path(path="total", equals=2)
- verify: json_path(path="missing[0].code", equals="src/demo.py::farewell")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds an inventory of two functions,
  of which the book cites one
- code: ostler/ostler/coverage.py::citations@1d717abaaced
- code: ostler/ostler/qa/outcome.py::QaOutcome@d89b9acaf3b3

### ostler-backfill-plan
- usage: ostler backfill plan --inventory PATH [--surface S] [--waivers PATH] [--scope PATH]
  [--json] [--check] — lists the units the book owes the code: uncovered symbols, drifted
  citations, moved ones and dangling ones
- flags:
  - --inventory (the source inventory), --waivers (adjudicated non-units), --scope (limit to this path), --check (exit 1 while the plan is not clean), --json (print `{surface, clean, counts, units, errors}`)
- exits: 0 — the plan reports its units and exits 0 unless --check is given
- run: invoke(argv=["-C", "book-scratch", "backfill", "plan", "--inventory", "book-scratch/inventory.json", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="clean", equals=false)
- verify: json_path(path="counts.uncovered", equals=1)
- verify: json_path(path="units[0].unit", equals="src/demo.py::farewell")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds an inventory of two functions,
  of which the book cites one
- code: ostler/ostler/backfill.py::plan@594db96524ce
- code: ostler/ostler/checks.py::literal@b1865cb90eea

### ostler-gc
- usage: ostler gc [--write] — lists the book pages no link path from their service's entries page
  reaches, and with --write deletes them
- flags:
  - --write (delete the unreachable pages instead of only listing them)
- exits: 0 — a book whose pages all link from its entries page prints `every page is reachable`
- run: invoke(argv=["-C", "book-scratch", "gc"])
- verify: exit_status(code=0)
- verify: stdout(matches="^every page is reachable$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a book whose entries page
  links every other page
- code: ostler/ostler/registry.py::fixture_keys@3037ce17c16c
