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
- code: ostler/ostler/cli.py::main@03c9e301c36d
- detail: [The book's markdown model](concepts/the-books-markdown-model.md)

## Commands

### ostler-doctor
- usage: ostler doctor [--json] [--path PATH] [--census] — loads the book, runs every referential
  and shape check over it, and prints one line per finding followed by `N error(s), M warning(s)`
  (or the whole outcome as one JSON object with --json)
- flags:
  - --json (print `{org, profile, epics, errors, warnings, findings}` as one indented JSON object), --path (check only the book at this path), --census (print the census of the book's nodes instead of the findings)
- exits: 0 — a book whose findings are all warnings, or none, is sound
- run: invoke(argv=["-C", "book-scratch", "doctor", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="errors", equals=0)
- verify: json_path(path="findings[0].severity", equals="warn")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a sound `demo` book whose
  citations carry no digest stamp, so it reports warnings and no error
- code: ostler/ostler/doctor.py::run@b02e27a258c1
- code: ostler/ostler/book_reach.py::dead_pages@1cbfe5c921ec
- code: ostler/ostler/checks.py::bind@d5883c9e9bfd
- code: ostler/ostler/acts.py::bind@610cf52e40be
- code: ostler/ostler/data_state_ledger.py::check_conditions@932372d84505
- code: ostler/ostler/data_states.py::check_data_states@06a62f37cb1d
- code: ostler/ostler/dynamic_registry.py::as_entity_types@09b3f9268893
- code: ostler/ostler/fragment_hosts.py::check_fragment_hosts@908846415586
- code: ostler/ostler/graph.py::build@631acb3378b2
- code: ostler/ostler/hidden_claims.py::check_hidden_claims@97734306adec
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/inventory.py::declared_names_at@fc37414c2b8a
- code: ostler/ostler/links.py::is_doc_link@471fa7366668
- code: ostler/ostler/locators.py::collisions@4e770b42dfdc
- code: ostler/ostler/markdown.py::all_code_spans@115245786c4b
- code: ostler/ostler/model.py::anchor_of@0ed7e7aad44d
- code: ostler/ostler/outcome_rules.py::check_outcomes@408c771787b5
- code: ostler/ostler/page_size.py::check_page_size@91b84d86b7a8
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/passages.py::check_passages@7b055a542ea9
- code: ostler/ostler/refs.py::bare_targets@5de8b2ec8022
- code: ostler/ostler/registry.py::address_keys@cd37e79abc8c
- code: ostler/ostler/section_hosts.py::check_section_hosts@f8458f69db47
- code: ostler/ostler/server_membership.py::check_server_membership@badd1c75c0f9
- code: ostler/ostler/shared_checks.py::check_shared_checks@c96e41ffd13b
- code: ostler/ostler/source_snapshots.py::book_repository@40c4e0bf4525
- code: ostler/ostler/stack_checks.py::check_stack@2f4549d63d1b
- code: ostler/ostler/syntax.py::grammar_version@0850b2c61451
- code: ostler/ostler/qa/fixture_provides.py::closure@9053b42918c0
- code: ostler/ostler/qa/fixtures.py::parse_bullet@a4b91574f193
- code: ostler/ostler/qa/journey_steps.py::journey_steps@0794ea6c9659
- code: ostler/ostler/qa/obligation_frame.py::book_nodes@c6e8278e4f37
- code: ostler/ostler/qa/references.py::find_references@087a925ce811
- code: ostler/ostler/qa/runbook.py::has_served_surface@b0b4e9245916
- code: ostler/ostler/qa/sensitivity.py::report@bc503e0d42f7
- code: ostler/ostler/qa/harness/ostler_qa_responses.py::read_exit@1d4c7f6bc802
- code: ostler/ostler/qa/harness/ostler_qa_verdicts.py::recorded@6473ea39a89f
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- detail: [Book health: coverage, reach and census](concepts/book-health-coverage-reach-and-census.md)

### ostler-doctor-dangling-link
- usage: ostler doctor --json — reports a link to a page that does not exist as an error finding
  and exits 1, so a caller that gates on the exit status stops on it
- exits: 1 — a book with one error finding fails the check
- run: invoke(argv=["-C", "book-scratch-broken", "doctor", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="errors", equals=1)
- verify: json_path(path="findings[0].code", equals="dangling-link")
- verify: json_path(path="findings[0].path", equals="docs/features/demo/entries.md")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds `book-scratch-broken/`, whose
  entries page links to a page that does not exist
- code: ostler/ostler/doctor.py::run@b02e27a258c1
- code: ostler/ostler/finding.py::Finding@9ff7be48f3bd
- code: ostler/ostler/markdown.py::comment_blocks@115245786c4b
- code: ostler/ostler/model.py::doc_roots@0ed7e7aad44d
- code: ostler/ostler/refs.py::bullet_ref@5de8b2ec8022

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
- code: ostler/ostler/checks.py::CheckSpec@d5883c9e9bfd

### ostler-checks-one
- usage: ostler checks NAME — prints one check's signature and what it excludes, one line each
- args: name — a check name `ostler checks` lists
- exits: 0 — a name the vocabulary declares prints its signature and description
- run: invoke(argv=["checks", "exit_status"])
- verify: exit_status(code=0)
- verify: stdout(matches="exit_status\\(code\\*=<int>\\)")
- fixture: none, because the vocabulary is fixed in code and reads no book
- code: ostler/ostler/checks.py::describe@d5883c9e9bfd

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
- code: ostler/ostler/behavior.py::build_audit_packets@9b054226c6dd
- code: ostler/ostler/behavior_cli.py::run@324557ae52a9
- code: ostler/ostler/behavior_models.py::FileExcerpt@23f8eb86babc
- code: ostler/ostler/behavior_python.py::PythonEvidence@56f54c99d10e
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/markdown.py::leading_code_spans@115245786c4b
- code: ostler/ostler/registry.py::normative_keys@cd37e79abc8c
- code: ostler/ostler/syntax.py::language_for@0850b2c61451
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
- code: ostler/ostler/behavior_go.py::GoEvidence@f1f9630c97e2
- code: ostler/ostler/behavior_cli.py::run@324557ae52a9
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
- code: ostler/ostler/behavior_tree.py::TreeEvidence@c32ff5de858b
- code: ostler/ostler/behavior_cli.py::run@324557ae52a9
- detail: [Auditing a book's claims against source](concepts/auditing-a-books-claims-against-source.md)

### ostler-trace
- usage: ostler trace TOKEN — prints the node a seed id, story slug, surface or doc path names, then
  every link out of it with `[ok]` or `[broken]` and every page that links to it
- args: token — a node id, slug, surface or doc path
- exits: 0 — a token that names a node prints its neighbours
- run: invoke(argv=["-C", "book-scratch", "trace", "entries"])
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^  → docs/features/demo/cli\\.md  \\[ok\\]$")
- verify: stdout(matches="(?m)^  → docs/features/demo/flows/say-hello\\.md  \\[ok\\]$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds an entries page that links the
  cli page and the flow
- code: ostler/ostler/trace.py::run@627ab268dee3
- code: ostler/ostler/markdown.py::MarkdownDoc@115245786c4b
- code: ostler/ostler/registry.py::type_of@cd37e79abc8c

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
- code: ostler/ostler/trace.py::run@627ab268dee3

### ostler-search
- usage: ostler search QUERY [--json] — full-text search over the book's pages and nodes, printing
  one JSON object per match per line (or the matches as one indented array with --json)
- flags:
  - --json (print the matches as one indented JSON array)
- args: query — the text to look for
- exits: 0 — a query prints its matches, possibly none
- run: invoke(argv=["-C", "book-scratch", "search", "Say hello", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[1].slug", equals="say-hello")
- verify: json_path(path="[1].path", equals="docs/features/demo/flows/say-hello.md")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a flow titled "Say hello"
- code: ostler/ostler/query.py::list_entities@df0758605f55

### ostler-list
- usage: ostler list --type TYPE [--json] — lists the nodes of one type, one JSON object per line
  (or one indented array with --json)
- flags:
  - --type (the node type to list), --json (print the nodes as one indented JSON array)
- exits: 0 — a known type prints its nodes, possibly none
- run: invoke(argv=["-C", "book-scratch", "list", "--type", "flow", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].type", equals="flow")
- verify: json_path(path="[0].path", equals="docs/features/demo/flows/say-hello.md")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds one flow
- code: ostler/ostler/query.py::list_entities@df0758605f55

### ostler-query
- usage: ostler query KIND ARG [--checkout REPOSITORY=PATH] [--json] — answers a reverse-index
  question about a node: the stories covering a seed, the surfaces a story references, or the story
  and commit a node traces to
- flags:
  - --checkout (a source checkout for exact `Story` trailer queries; repeat per repository), --json (print the answers as one indented JSON array)
- args: kind — one of stories-covering-seed, surfaces-referenced-by-story, story-provenance, commit-story, node-provenance, story-for-node; arg — the id, slug or path the kind asks about
- exits: 0 — a node with no checkout supplied is answered, unresolved, with a warning naming the missing checkout
- run: invoke(argv=["-C", "book-scratch", "query", "story-for-node", "docs/features/demo/cli.md", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].node.id", equals="docs/features/demo/cli.md")
- verify: json_path(path="[0].resolved", equals=false)
- verify: json_path(path="[0].node.codeRefs[0]", equals="src/demo.py::greet")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds a cli page that cites
  `src/demo.py::greet`
- code: ostler/ostler/query.py::query@df0758605f55
- code: ostler/ostler/provenance.py::checkout_for@e9279b5048ce

### ostler-graph
- usage: ostler graph [--surface S] [--type T] [--title T] [--path P] [--under ID] [--depth N]
  [--has-bullet KEY] [--bullet KEY=VAL] [--links-to ID] [--orphans] [--tree | --ids | --json] —
  filters the book's node and edge graph and prints it as an outline, bare ids or one JSON object
- flags:
  - --type (nodes of this type), --ids (print one bare node id per line), --json (print the filtered `{counts, nodes, edges}` object), --tree (print an indented outline, the default)
- exits: 0 — a filter that matches nothing prints an empty result
- run: invoke(argv=["-C", "book-scratch", "graph", "--type", "command", "--ids"])
- verify: exit_status(code=0)
- verify: stdout(matches="^docs/features/demo/cli\\.md#demo-greet$")
- fixture: [book scratch repo](fixtures/book-scratch-repo.md) — seeds one command node
- code: ostler/ostler/graph.py::build@631acb3378b2
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b

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
- code: ostler/ostler/reach.py::literal_entries@9d242d10b584
- code: ostler/ostler/routes.py::entry_address@778f9d4fb9ed
- code: ostler/ostler/qa/runbook.py::bullet_text@b0b4e9245916
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

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
- code: ostler/ostler/locators.py::build@4e770b42dfdc
- code: ostler/ostler/selector_forms.py::parse_scheme_selector@f340cabcc2d7

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
- code: ostler/ostler/coverage.py::citations@2e691370b1e7
- code: ostler/ostler/qa/outcome.py::QaOutcome@a11c201f424c

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
- code: ostler/ostler/backfill.py::plan@e3c3cac49def
- code: ostler/ostler/checks.py::literal@d5883c9e9bfd

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
- code: ostler/ostler/registry.py::fixture_keys@cd37e79abc8c
