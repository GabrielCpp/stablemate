---
type: concept
slug: the-debt-register
title: The debt register
---
# The debt register

The debt register is the one place a workspace keeps the improvements nobody has done yet. Each
item is a record: one `record.md` file in the artifacts repo, never in a code repo, on the untracked `backlogs/` shelf described in [the artifacts layout](artifacts-layout.md). A record is
filed by the agent or person who found the work, and it stays on the shelf after it ends, with the
status it ended at and the reason. Ostler owns the shelf: it files, lists, closes and imports
records, and `ostler doctor` names a record that does not parse. The review-debt workflow reads
the whole shelf and groups it into trends. A cluster of records can become a
[decision record](decision-records.md) that names them as its evidence.

- code: ostler/ostler/register.py::Record@c830fda449ae
- code: ostler/ostler/register.py::records@c830fda449ae
- code: ostler/ostler/register.py::write@c830fda449ae
- code: ostler/ostler/register.py::close@c830fda449ae
- code: ostler/ostler/register.py::file_person@c830fda449ae
- code: ostler/ostler/register_import.py::import_list@307db9c8d802
- code: ostler/ostler/path.py::register_root@6a1acd1702fd
- tests: ostler/tests/test_register.py::test_write_lays_the_record_under_repo_area_id_in_the_artifacts_dir
- tests: ostler/tests/test_register.py::test_the_listing_has_one_line_per_record_closed_ones_included
- tests: ostler/tests/test_register_close.py::test_close_marks_a_record_done_and_keeps_every_other_field_and_the_body
- tests: ostler/tests/test_register_import.py::test_a_hand_written_list_becomes_one_record_per_bullet
- detail: [The artifacts layout](artifacts-layout.md)
- detail: [Decision records](decision-records.md)
- detail: [Planning identities](planning-identities.md)

## The shelf

The shelf is `backlogs/` in the artifacts dir: `$STABLEMATE_ARTIFACTS_DIR`, else the home config's
`artifacts_dir`, else an `artifacts` folder under the platform data directory. A record lives at
`backlogs/<repo>/<area>/<id>/record.md`. Ostler reads every file that matches that three-level
pattern and nothing else. The listing sorts the records by repo, then area, then id. A file that
does not parse stays out of the listing, and `ostler doctor` reports it as
`register-record-unreadable`, an error. The shelf is untracked: the artifacts repo ignores `backlogs/`, and the first write creates the
artifacts dir as a git repository with no remote when it is not one yet.

## Fields

### field: id
- type: string
- required: yes
- the record's folder name, so one path-safe segment of letters, digits, `.`, `_` and `-`, starting
  with a letter or digit. Ids are unique across the workspace: a write refuses an id any story,
  epic, seed, milestone or record already holds, with `record id '<id>' is already taken`. A
  minted id is a full `<PREFIX>-<ULID>` from the same allocator stories use.

### field: repo
- type: string
- required: yes
- the workspace repository the record is about, one lowercase kebab segment.

### field: area
- type: string
- required: yes
- the part of that repository it sits in, one lowercase kebab segment, such as `billing` or `book`.

### field: pattern
- type: string
- required: yes
- the kind of fix the record calls for. A person's filing and an import default it to `untriaged`.

### field: symbols
- type: list of strings
- default: empty
- the code symbols or paths the record names.

### field: filed_by
- type: one of coder, qa, qa-deferred, person, survey, parity
- required: yes
- who filed it: the coder's deferred follow-ups, QA's leftovers, the book pages QA could not check,
  a person, the author's code survey, or the legacy parity survey.

### field: source_story
- type: string
- default: empty
- the story whose run filed the record, when one did.

### field: summary
- type: string
- required: yes
- the listing text, one non-empty line.

### field: status
- type: one of open, done, dropped, promoted
- default: open
- `open` until the record ends. `done` means the work shipped, `dropped` means nobody will do it,
  and `promoted` means a story now stands for it.

### field: decision
- type: string
- default: empty
- the id of the decision record that cites this record as evidence.

### field: reason
- type: string
- default: empty
- why the record ended, written when it is closed.

### field: body
- type: markdown
- default: empty
- the record's text below the frontmatter.

## Closing a record

Closing rewrites only `status` and `reason` and leaves every other field and the body as they
were. The target status is `done`, `dropped` or `promoted`. A close to `open` is refused. Closing a
record at the status it already has writes nothing and succeeds. Closing a closed record at
another status is refused with `record '<id>' is already <status>, not <target>`. A close makes
no commit. `ostler backlog prune` adds one guard: `dropped` and
`promoted` need a `--reason`.

## No commits

The shelf is untracked, so no write to it commits anything. Filing, closing and importing change
files and nothing else, and the code repo is never touched.

## Importing an old list

`ostler backlog adopt --repo <repo> <file>` turns a hand-written bullet list into records, once,
then deletes the list.

- each top-level bullet becomes one record of `<repo>` with pattern `untriaged`. Numbered lists,
  paragraphs and nested bullets are prose, not records.
- the area is the kebab of the nearest heading above the bullet, cut at ` | `. A bullet under no
  heading goes to `general`. A level-1 title on the first line does not count as a heading.
- the heading also sets who filed the record. "Filed by coder" means `qa`, because QA filed those
  items for the coder. "Deferred by coder" means `coder`. "Book checks QA could not run" means
  `qa-deferred` in area `book`. "Survey findings" means `survey`, and "Legacy surfaces missing
  from the new app" means `parity`. Each of these lands in area `untriaged` except the book checks.
  A bullet under any other heading is filed by `person`.
- the summary is the bullet's first sentence, cut at a word boundary within 160 characters, with
  `…` appended when cut.
- the body is the bullet's whole text less its marker and id, then a `## Context` section that
  says `Filed under the heading "<title>".` or `Filed under no heading.`, followed by the prose
  under that heading.
- a bullet that opens with `[<id>]` keeps that id. Any other bullet gets a minted id.
- the import is all or none. It refuses a missing file, a file with no bullets, an id used twice
  in the list, a kept id the workspace already holds, and a bullet that makes an invalid record.
  A refusal writes nothing and keeps the file.
- the import makes no commit.

## Contract

- one record, one file: each record is exactly one `record.md`, and each `record.md` holds exactly
  one record.
- the shelf is outside every code repo, so a code branch never carries a record.
- a record stays on the shelf after it ends: the listing shows every status unless filtered.
- ids are workspace-wide. A short handle names a record the same way it names a story, and every
  command that takes a record id takes one.
