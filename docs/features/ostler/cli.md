---
type: cli
slug: cli
title: ostler
---
# ostler

Ostler is the planning CLI: one `ostler` binary dispatching to subcommands that read and write the
managed markdown tree (backlog, milestones, epics, features) under a repo root.

- binary: ostler
- code: ostler/ostler/cli.py::main@03c9e301c36d
- detail: [Planning identities](concepts/planning-identities.md)

## Commands


### ostler-create-backlog-item
- usage: ostler create backlog-item TEXT [--section NAME] [--prefix PREFIX] [--json] — allocates a
  fresh full id and appends `- [<id>] <text>` to `docs/backlog.md` (creating the file with a bare
  `# Backlog` heading first run); two calls with the same text each get their own id and both
  bullets are kept
- flags:
  - --section (file under this `##` heading instead of the end of the list), --prefix (override the derived id prefix), --json (print `{ok, id, name, message}` instead of a line of text)
- args: text — the item's description, written verbatim after the allocated id
- exits: 0 — creation of a freshly allocated id can't collide, so this command never fails
- run: invoke(argv=["create", "backlog-item", "a sample backlog item", "--prefix", "TEST", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="id", matches="^TEST-[0-9A-HJKMNP-TV-Z]{26}$")
- verify: contents(subject="docs/backlog.md", matches="(?m)^- \\[TEST-[0-9A-HJKMNP-TV-Z]{26}\\] a sample backlog item$")
- fixture: none, because a freshly allocated id needs no seeded state; docs/backlog.md is created
  if absent and appended to if present
- code: ostler/ostler/backlog.py::create@fbc174481294
- code: ostler/ostler/ids.py::allocate@b37d33a102e8
- detail: [Planning identities](concepts/planning-identities.md)
- tests: ostler/tests/test_backlog.py::test_create_backlog_item_persists_full_generated_id

### ostler-artifact-list
- usage: ostler artifact list [--json] — prints the built-in artifact kinds
  (plan-context, qa-evidence, backlog-items), each as a `{kind, filename, description}` line, or as
  one indented JSON array with --json
- flags:
  - --json (print the whole array as one indented JSON document instead of one compact line per kind)
- exits: 0 — listing the built-in kinds reads only the code-registered kind table, so this command
  never fails
- run: invoke(argv=["artifact", "list", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[2].kind", equals="backlog-items")
- verify: json_path(path="[2].filename", equals="backlog-items.json")
- fixture: none, because the kind registry is fixed in code, not read from any spec dir
- code: ostler/ostler/artifact/run.py::list_kinds@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::KINDS@ec25eeaddd5f
- code: ostler/ostler/artifact/__init__.py::__all__@d177bd2861a0
- code: ostler/ostler/cli.py::_cmd_artifact@03c9e301c36d

### ostler-artifact-scaffold
- usage: ostler artifact scaffold KIND --spec PATH [--force] — writes KIND's JSON skeleton to
  `<spec-dir>/<kind>.json`, creating the spec directory first, and prints
  `scaffolded <kind> -> <path>`; refuses to overwrite an existing artifact file unless --force is
  given
- flags:
  - --spec (the spec directory: absolute as given, else resolved under the specs root if it exists there, else under the repo root), --force (overwrite an existing artifact file instead of erroring)
- args: kind — one of the names `ostler artifact list` reports (plan-context, qa-evidence,
  backlog-items)
- exits: 0 — a kind name from the registry, scaffolded at a path that does not yet hold that kind's
  file, writes the skeleton and prints the destination
- run: invoke(argv=["artifact", "scaffold", "backlog-items", "--spec", "artifact-flow-spec"])
- verify: exit_status(code=0)
- verify: contents(subject="artifact-flow-spec/backlog-items.json", matches="(?s)^\\[\\]\\n$")
- fixture: none, because scaffolding into a fresh spec directory needs no seeded state; the
  directory is created if absent
- code: ostler/ostler/artifact/run.py::scaffold@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::ArtifactKind@ec25eeaddd5f
- code: ostler/ostler/path.py::resolve_spec_arg@b434dbc906c6
- code: ostler/ostler/cli.py::_cmd_artifact@03c9e301c36d

### ostler-artifact-scaffold-unknown-kind
- usage: ostler artifact scaffold KIND --spec PATH — rejects a KIND outside the registry before
  touching the spec directory
- args: kind — a name not among those `ostler artifact list` reports
- exits: 1 — a kind name outside the registry is rejected before any file is touched
- run: invoke(argv=["artifact", "scaffold", "bogus-kind", "--spec", "artifact-scaffold-error-spec"])
- verify: exit_status(code=1)
- fixture: none, because an unknown kind name fails before the spec directory is read or written
- code: ostler/ostler/artifact/run.py::scaffold@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::ArtifactKind@ec25eeaddd5f
- code: ostler/ostler/cli.py::_cmd_artifact@03c9e301c36d

### ostler-artifact-vet
- usage: ostler artifact vet KIND --spec PATH [--json] — validates `<spec-dir>/<kind>.json` against
  KIND's contract and prints either `{kind}: clean` or `{kind}: problems` followed by one `  - ` line
  per problem (or the whole outcome as one JSON object with --json)
- flags:
  - --spec (same resolution as `ostler artifact scaffold`), --json (print `{kind, path, status, problems?, error?}` as one indented JSON object)
- args: kind — one of the names `ostler artifact list` reports
- exits: 1 — vetting a kind whose artifact file does not yet exist at the spec dir fails with
  `error: <path> does not exist — scaffold it first`, rather than treating an absent file as clean
- run: invoke(argv=["artifact", "vet", "backlog-items", "--spec", "artifact-vet-missing-spec"])
- verify: exit_status(code=1)
- fixture: none, because the claim is that a never-scaffolded spec dir is rejected
- code: ostler/ostler/artifact/run.py::vet@72b226ff9de4
- code: ostler/ostler/artifact/kinds.py::_backlog_items_vet@ec25eeaddd5f
- code: ostler/ostler/cli.py::_cmd_artifact@03c9e301c36d

### ostler-env-schema
- usage: ostler env schema — prints the JSON Schema of a book's `ops/stack.yml`
- exits: 0 — printing the schema reads only the code-declared key table, so this command never fails
- run: invoke(argv=["env", "schema"])
- verify: exit_status(code=0)
- verify: json_path(path="$schema", equals="https://json-schema.org/draft/2020-12/schema")
- fixture: none, because the schema is built from the code-declared key table, not read from any
  stack.yml
- code: ostler/ostler/environments/spec.py::schema@b020ed778dc2
- code: ostler/ostler/environments/spec.py::KEYS@b020ed778dc2
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17

### ostler-env-check
- usage: ostler env check [--json] — reads every book's `ops/stack.yml`, prints `N services in M
  books fit together` when none of them disagree, and otherwise prints one `- ` line per problem
  (or the whole outcome as one JSON object with --json)
- flags:
  - --json (print `{ok, books, services, errors}` as one indented JSON object)
- exits: 1 — a book whose `ops/stack.yml` does not parse to a mapping with a `services:` key is
  reported by name and path, rather than being skipped silently
- run: invoke(argv=["env", "check", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="errors[0]", matches="^docs/features/env-check-fixture/ops/stack\\.yml: is not a mapping with a `services:` key$")
- fixture: env-check-fixture creates docs/features/env-check-fixture/ops/stack.yml, a stack file
  whose top level is a YAML list rather than a mapping
- code: ostler/ostler/environments/spec.py::load@b020ed778dc2
- code: ostler/ostler/environments/spec.py::_read_book@b020ed778dc2
- code: ostler/ostler/environments/commands.py::cmd_check@36bbc1003620
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17
