---
type: cli
slug: editing
title: ostler editing commands
---
# ostler editing commands

The commands that change a book or a story for the caller: they put pages in canonical form, repair
drift, stamp source digests, create nodes, and move or rename what other pages link to. Every claim
here runs in a scratch repository, and an edit that moves files runs with --write so the claim can
read the result. Each command changes its own entity, so only the story rename depends on running
last.

- binary: ostler
- code: ostler/ostler/cli.py::main@6f9e6ca5fc20

## Commands

### ostler-fmt-check
- usage: ostler fmt --check [PATH ...]: lists the pages that are not in canonical form and changes
  none
- flags:
  - --check (change nothing and exit 1 when any page is not canonical)
- args: PATH ... (the pages to check; default is every page of the book)
- exits: 1 when a listed page is not canonical, 0 when all are
- run: invoke(argv=["-C", "edit-scratch", "fmt", "--check", "docs/services/demo/tidy.md"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=1)
- verify: stdout(matches="(?m)^would reformat: docs/services/demo/tidy\\.md$")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/fmt.py::format_text@aa3a632453a3

### ostler-fmt
- usage: ostler fmt [PATH ...]: rewrites each page into canonical form: frontmatter keys in order,
  bullets spaced and ordered, headings cased and a wikilink turned into a markdown link
- args: PATH ... (the pages to format; default is every page of the book)
- exits: 0 when every page is rewritten or already canonical
- run: invoke(argv=["-C", "edit-scratch", "fmt", "docs/services/demo/tidy.md"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^reformatted: docs/services/demo/tidy\\.md$")
- verify: contents(subject="edit-scratch/docs/services/demo/tidy.md", matches="See \\[rec\\]\\(rec\\) for the record")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/fmt.py::format_text@aa3a632453a3

### ostler-autofix-check
- usage: ostler autofix --check [PATH ...]: lists the pages that carry a drift autofix can repair
  and changes none
- flags:
  - --check (change nothing and exit 1 when any page carries fixable drift)
- args: PATH ... (the pages to check; default is every page of the book)
- exits: 1 when a listed page carries fixable drift, 0 when none does
- run: invoke(argv=["-C", "edit-scratch", "autofix", "--check", "docs/services/demo/api.md"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=1)
- verify: stdout(matches="(?m)^would fix: docs/services/demo/api\\.md$")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/autofix.py::fix_text@821c6bbcfd2c
- code: ostler/ostler/fmt.py::_target_files@aa3a632453a3

### ostler-autofix
- usage: ostler autofix [PATH ...]: repairs the drift whose fix is certain, such as a verify bullet
  that holds a test reference instead of a check, which becomes a tests bullet
- args: PATH ... (the pages to repair; default is every page of the book)
- exits: 0 when every page is repaired or has nothing to repair
- run: invoke(argv=["-C", "edit-scratch", "autofix", "docs/services/demo/api.md"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^fixed: docs/services/demo/api\\.md$")
- verify: contents(subject="edit-scratch/docs/services/demo/api.md", matches="- tests: .src/test_demo\\.py::test_submit")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/autofix.py::fix_text@821c6bbcfd2c
- code: ostler/ostler/fmt.py::_target_files@aa3a632453a3

### ostler-stamp
- usage: ostler stamp (--node ID [--file PATH] ... | --path PAGE --whole-page): writes the content
  hash of each cited source file onto the code bullets of a node or a page
- flags:
  - --node (a node id to stamp, repeatable; only that node's own code bullets are restamped)
  - --file (paired with --node: restamp only the target citing this file)
  - --path (a book page to stamp, repeatable; requires --whole-page)
  - --whole-page (restamp every code bullet on the page)
  - --json (print the results as JSON)
- exits: 0 when the stamps are written, 2 when the arguments are inconsistent
- run: invoke(argv=["-C", "edit-scratch", "stamp", "--path", "docs/services/demo/cli.md", "--whole-page"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^docs/services/demo/cli\\.md: 2 stamped$")
- verify: contents(subject="edit-scratch/docs/services/demo/cli.md", matches="src/demo\\.py::greet@[0-9a-f]+")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/stamp.py::digest_file@b578fea528ce

### ostler-scaffold
- usage: ostler scaffold TYPE NAME [--service SERVICE] [--in FILE] [--title TITLE] [--json]: creates
  a node of a book type in the place the type belongs, from the type's skeleton
- flags:
  - --service (file-level types: the service whose subtree receives the page)
  - --in (section-level types: the page the new section is inserted into)
  - --title (the title of the node)
  - --json (print the outcome as JSON)
- args: TYPE (a node type of the book), NAME (the new node's name)
- exits: 0 when the node is created, 1 when the type, the name or the place is refused
- run: invoke(argv=["-C", "edit-scratch", "scaffold", "concept", "widgets", "--service", "demo", "--json"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: contents(subject="edit-scratch/docs/services/demo/concepts/widgets.md", matches="type: concept")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/result.py::Result@f4149eb63e51
- code: ostler/ostler/scaffold.py::scaffold@ecfd6a2ea722

### ostler-edit-relink
- usage: ostler edit relink OLD NEW [--write]: replaces a path in every page and spec file that
  names it, as a dry run unless --write is given
- flags:
  - --write (apply the plan; the default is a dry run that prints the diff)
- args: OLD (the path to replace), NEW (the path to put in its place)
- exits: 0 when the plan is built, 1 when it holds an error
- run: invoke(argv=["-C", "edit-scratch", "edit", "relink", "../../../../services/area/rec.md", "../../../../services/area/record.md", "--write"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 1 file\\(s\\) changed, 0 move\\(s\\)$")
- verify: contents(subject="edit-scratch/docs/epics/0001-first/stories/sx/story.md", matches="services/area/record\\.md")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/edit.py::relink@63e4a8c64c39

### ostler-edit-migrate-context
- usage: ostler edit migrate-context NODE_TYPE SERVICE [--write]: moves a service's pages of one
  node type into the folder the type belongs in and rewrites every link the move touches
- flags:
  - --write (apply the plan; the default is a dry run that prints the diff)
- args: NODE_TYPE (a node type of the book), SERVICE (the service under the services root)
- exits: 0 when the plan is built, 1 when the type, the service or the pages are missing
- run: invoke(argv=["-C", "edit-scratch", "edit", "migrate-context", "concept", "demo", "--write"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 2 file\\(s\\) changed, 2 move\\(s\\)$")
- verify: absent(subject="edit-scratch/docs/services/demo/idea.md")
- verify: contents(subject="edit-scratch/docs/services/demo/entries.md", matches="\\(concepts/idea\\.md\\)")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/edit.py::migrate_context@63e4a8c64c39

### ostler-edit-settle-review
- usage: ostler edit settle-review STORY [--write]: settles a story's review from the
  review-resolution.json in its spec directory and flips the story status when every finding is
  settled
- flags:
  - --write (apply the plan; the default is a dry run that prints the diff)
- args: STORY (the story's id)
- exits: 0 when the plan is built, 1 when the resolution is missing or malformed
- run: invoke(argv=["-C", "edit-scratch", "edit", "settle-review", "TST-01M585PFWZZXH4Y6KNMH1VK58H", "--write"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 2 file\\(s\\) changed, 0 move\\(s\\)$")
- verify: contents(subject="edit-scratch/docs/epics/0001-first/stories/sx/story.md", matches="Review fixes applied")
- verify: contents(subject="edit-scratch/art/specs/TST-01M585PFWZZXH4Y6KNMH1VK58H/review-settlement.json", matches="\"all_settled\": true")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/edit.py::settle_review@63e4a8c64c39

### ostler-edit-carve-endpoints
- usage: ostler edit carve-endpoints SERVER [--write]: moves each endpoint of a server page onto a
  page of its own beside it, with the invocations that call it, and rewrites every link the move
  touches
- flags:
  - --write (apply the plan; the default is a dry run that prints the summary)
- args: SERVER (the server page, relative to the repo or to the services root)
- exits: 0 when the plan is built, 1 when it holds an error
- run: invoke(argv=["-C", "edit-scratch", "edit", "carve-endpoints", "docs/services/demo/http/server.md", "--write"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^carve docs/services/demo/http/server\\.md: 2 endpoint page\\(s\\), 1 invocation\\(s\\) moved with them$")
- verify: contents(subject="edit-scratch/docs/services/demo/http/get-widget.md", matches="(?m)^type: endpoint$")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/carve.py::carve_endpoints@16296e22e532
- code: ostler/ostler/edit.py::_doc_files@63e4a8c64c39

### ostler-edit-carve-fragments
- usage: ostler edit carve-fragments PAGE [--write]: moves the subsections of a page's largest
  sections onto fragment pages beside it until it fits the page size limit, and rewrites every link
  the move touches
- flags:
  - --write (apply the plan; the default is a dry run that prints the summary)
- args: PAGE (the page, relative to the repo or to the services root)
- exits: 0 when the plan is built, 1 when it holds an error
- run: invoke(argv=["-C", "edit-scratch", "edit", "carve-fragments", "docs/services/demo/concepts/ledger.md", "--write"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^carve docs/services/demo/concepts/ledger\\.md: 2 fragment page\\(s\\) from 1 section\\(s\\)$")
- verify: contents(subject="edit-scratch/docs/services/demo/concepts/ledger-rules-rule-1.md", matches="(?m)^type: fragment$")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/carve.py::references@16296e22e532
- code: ostler/ostler/edit.py::_doc_files@63e4a8c64c39
- code: ostler/ostler/fragment_carve.py::carve_fragments@7d965ac3d2df

### ostler-edit-rename
- usage: ostler edit rename OLD NEW [--write]: renames a story slug in every page and spec file that
  names it, and moves the story folder
- flags:
  - --write (apply the plan; the default is a dry run that prints the diff)
- args: OLD (the slug to replace), NEW (the new slug)
- exits: 0 when the plan is built, 1 when the slug is not found
- run: invoke(argv=["-C", "edit-scratch", "edit", "rename", "sx", "sy", "--write"], env={"STABLEMATE_ARTIFACTS_DIR": "edit-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 2 file\\(s\\) changed, 1 move\\(s\\)$")
- verify: absent(subject="edit-scratch/docs/epics/0001-first/stories/sx")
- verify: contents(subject="edit-scratch/docs/epics/0001-first/stories/sy/story.md", matches="slug: sy")
- fixture: [edit scratch repo](fixtures/edit-scratch-repo.md) with an edit scratch repo whose book
  and story have not been edited yet
- code: ostler/ostler/edit.py::rename@63e4a8c64c39
