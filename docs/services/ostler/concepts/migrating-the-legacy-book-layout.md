---
type: concept
slug: migrating-the-legacy-book-layout
title: Migrating the legacy book layout
---
# Migrating the legacy book layout

Before OKF markdown, a book's planning state lived as JSON siblings next to markdown: an
epic's seed items in `seed.json`, its story dependencies in `dependencies.json`, its backlog
queue in `epics-todo.json`, and a `docs/features/` tree with no `type:` frontmatter at all.
`ostler/scripts/okf_migrate.py` is a one-shot, idempotent script that rewrites a repo's `docs/`
tree from that legacy layout into the current markdown format, run by hand against a repo root
(`python -m ostler.scripts.okf_migrate [root]`, root defaulting to the current directory) —
it is not wired into the `ostler` CLI, since every repo needs it at most once.

`migrate` walks three independent trees under `docs/`. For `docs/epics/*/`, `_migrate_epic`
folds `seed.json`'s items and `dependencies.json`'s stories into `epic.md`'s frontmatter and a
`## Seeds` / `## Stories` body, then deletes both JSON files; a directory whose `epic.md`
already carries `type: epic` and no legacy JSON is left alone. `_stamp_stories` then gives
every `stories/*/story.md` a `type: story` and a `status` pulled from its old "Implementation
Status" section when the frontmatter does not already carry one. `_migrate_todo` turns
`epics-todo.json`'s ordered name list into `docs/epics/index.md`, one link per epic, then
deletes the JSON. For `docs/features/`, `_migrate_features` first expands a legacy
`inventory.json`'s `surfaces` or `entries` list into one stub page per entry (filed under the
entry's `area` subdirectory when it names one), then stamps `type: feature` onto every other
markdown file the tree already has (skipping `index.md` and `log.md`); `migrate` then renames
`docs/features/` to `docs/services/`, unless `docs/services/` already exists. For `docs/specs/`,
`_migrate_specs` stamps each `*/*.md` with the type `registry.spec_type_for` derives from its
filename, skipping any file `registry.RESERVED_FILES` already accounts for.

- code: ostler/ostler/scripts/__init__.py@e3b0c44298fc
- code: ostler/ostler/scripts/okf_migrate.py::migrate@55fab781de8c
- code: ostler/ostler/scripts/okf_migrate.py::main@55fab781de8c
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_epic@55fab781de8c
- code: ostler/ostler/scripts/okf_migrate.py::_stamp_stories@55fab781de8c
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_todo@55fab781de8c
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_features@55fab781de8c
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_specs@55fab781de8c

## Contract

- idempotent: a file already carrying the type the migration would give it is left untouched;
  running `migrate` twice on an already-migrated repo makes no further change.
- epic JSON removal: `seed.json` and `dependencies.json` are deleted only after their content is
  folded into `epic.md`, never left behind alongside the markdown they fed.
- scope: `migrate` only ever writes inside the `docs/epics/`, `docs/features/`/`docs/services/`
  and `docs/specs/` subtrees of the given root, and only those three top-level directories are
  inspected.
