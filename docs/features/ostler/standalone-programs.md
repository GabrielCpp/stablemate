---
type: cli
slug: standalone-programs
title: Standalone programs
---
# Standalone programs

Two programs run outside the `ostler` binary's own dispatch: a one-shot repo migration script a
maintainer runs by hand, and the sandbox's loopback port forwarder its container entrypoint
starts as a background process. Both run through `python3`, not through `ostler`.

- binary: python3
- detail: [ostler](cli.md)

## Commands

### okf-migrate
- usage: python3 -m ostler.scripts.okf_migrate [ROOT] — walks ROOT's `docs/epics`, `docs/features`
  and `docs/specs` trees, rewrites whatever legacy JSON-sibling or frontmatter-less markdown it
  finds into the current OKF markdown format, and prints `migrated <root>: <report>`, a dict
  counting how many epics, stories, features and specs it touched and whether it rewrote the
  epics backlog queue
- args: root — the repo root to migrate; defaults to the current directory when omitted
- exits: 0 — `migrate` only ever counts and rewrites what it finds; a tree with nothing legacy
  left prints a report of all zero counts and `'todo': False`, not an error
- run: invoke(argv=["-m", "ostler.scripts.okf_migrate", "okf-migrate-fixture"])
- verify: exit_status(code=0)
- verify: stdout(matches="^migrated okf-migrate-fixture: \\{'epics': 1, 'stories': 0, 'features': 1, 'specs': 0, 'todo': True\\}$")
- verify: contents(subject="okf-migrate-fixture/docs/epics/sample-epic/epic.md", matches="(?s)^---\\ntype: epic\\n")
- verify: absent(subject="okf-migrate-fixture/docs/epics/sample-epic/seed.json")
- verify: absent(subject="okf-migrate-fixture/docs/epics/sample-epic/dependencies.json")
- verify: contents(subject="okf-migrate-fixture/docs/epics/index.md", matches="(?m)^- \\[sample-epic\\]\\(sample-epic/epic\\.md\\)$")
- verify: contents(subject="okf-migrate-fixture/docs/features/legacy-page.md", matches="(?s)^---\\ntype: feature\\n")
- fixture: [legacy book layout](fixtures/legacy-book-layout.md) — seeds the pre-OKF epic, its
  `seed.json`/`dependencies.json` siblings, the `epics-todo.json` queue naming it, and a
  frontmatter-less feature page, all under `okf-migrate-fixture/`
- code: ostler/ostler/scripts/okf_migrate.py::migrate@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::main@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_epic@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_todo@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_features@96c0602e35de
- detail: [Migrating the legacy book layout](concepts/migrating-the-legacy-book-layout.md)

### sandbox-forwarder
- usage: python3 ostler/docker/sandbox/forwarder.py [READY-FILE] — reads
  `OSTLER_SANDBOX_FORWARD` as a JSON object of `{"<local-port>": "<host>:<port>"}` entries, binds
  one loopback listener per entry, and once every listener is bound writes the count it bound to
  READY-FILE before it blocks relaying traffic forever
- args: ready-file — the path the forwarder writes its bound-listener count to once every
  listener is up; optional, and never written when a mapping entry is rejected first
- exits: 2 — a mapping value with no `host` before its last `:` is rejected with
  `forwarder: bad upstream <value> for port <port>` on stderr, before any port is bound and before
  the ready-file is ever written
- run: invoke(argv=["ostler/docker/sandbox/forwarder.py", "forwarder-ready.txt"], env={"OSTLER_SANDBOX_FORWARD": "{\"18080\": \"no-colon\"}"})
- verify: exit_status(code=2)
- verify: stderr(matches="^forwarder: bad upstream 'no-colon' for port 18080$")
- verify: absent(subject="forwarder-ready.txt")
- fixture: none, because the rejected mapping is passed as an environment variable, not read from
  a file
- code: ostler/docker/sandbox/forwarder.py::main@1a617ef8e11b
- detail: [Sandbox port forwarding](concepts/sandbox-port-forwarding.md)
