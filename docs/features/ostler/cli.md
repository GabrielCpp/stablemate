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
- verify: exit_status(code=2)

## Commands


### ostler create backlog-item
- usage: ostler create backlog-item TEXT [--section NAME] [--prefix PREFIX] [--json]
- flags: --section (file under this `##` heading instead of the end of the list), --prefix
  (override the derived id prefix), --json (print `{ok, id, name, message}` instead of a line of text)
- args: text — the item's description, written verbatim after the allocated id
- does: allocates a fresh full id and appends `- [<id>] <text>` to `docs/backlog.md`
  (creating the file with a bare `# Backlog` heading first run); two calls with the same
  text each get their own id and both bullets are kept
- exits: 0 — creation of a freshly allocated id can't collide, so this command never fails
- run: invoke(argv=["create", "backlog-item", "a sample backlog item", "--prefix", "TEST", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="id", matches="^TEST-[0-9A-HJKMNP-TV-Z]{26}$")
- verify: contents(subject="docs/backlog.md", matches="(?m)^- \\[TEST-[0-9A-HJKMNP-TV-Z]{26}\\] a sample backlog item$")
- code: ostler/ostler/backlog.py::create@fbc174481294
- code: ostler/ostler/ids.py::allocate@b37d33a102e8
- detail: [Planning identities](concepts/planning-identities.md)
- tests: ostler/tests/test_backlog.py::test_create_backlog_item_persists_full_generated_id
