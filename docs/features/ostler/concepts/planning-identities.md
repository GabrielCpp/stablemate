---
type: concept
slug: planning-identities
title: Planning identities
---
# Planning identities

Ostler allocates immutable full ids for planning entities while preserving readable names for the
things people browse. A backlog item's text can change without changing its id; a milestone's slug,
filename, and title can describe a release without serving as that release's identity. Short handles
are derived display and command-input forms only. They are never persisted because a newly allocated
collision can require an existing handle to lengthen.

Backlog items live in the managed `docs/backlog.md` worklist as
`- [<full-id>] <description>`. New automation creates them through `ostler create backlog-item` or
`Ostler.create_backlog_item`. Existing human-authored bullets enter the same identity model through
`ostler backlog adopt` or `Ostler.backlog_adopt`: adoption names every unnamed bullet while
preserving text, ordering, headings, and nesting. The backlog grammar treats every bullet as an item;
supporting context and non-item detail are prose. Running adoption again changes nothing.

Milestones live at readable `docs/milestones/<slug>.md` paths but carry independently generated full
ids. Their `sourceItems` list records the full backlog ids whose product outcome they own. Creating a
milestone records its initial ownership; `milestone set-source-items` replaces that list when an
active release absorbs additional intake. Referential validation rejects one source item owned by
multiple milestones.

- code: ostler/ostler/ids.py::allocate
- code: ostler/ostler/backlog.py::create
- code: ostler/ostler/backlog.py::adopt
- code: ostler/ostler/crud.py::create_milestone
- code: ostler/ostler/crud.py::set_milestone_source_items
- code: ostler/ostler/doctor.py::_check_milestones
- verify: ostler/tests/test_backlog.py::test_create_backlog_item_persists_full_generated_id,
  ostler/tests/test_backlog.py::test_adopt_names_every_bullet_and_is_idempotent,
  ostler/tests/test_crud.py::test_create_milestone_allocates_id_and_records_source_items

## Contract

- persisted identity: the full `<PREFIX>-<26-character ULID>` allocated by Ostler.
- readable name: mutable prose or filesystem slug that does not substitute for generated identity.
- display handle: the shortest currently unambiguous prefix of a full id; accepted at command input
  boundaries and resolved back to the full id before any write.
- backlog adoption scope: every unnamed list item in the document, including preamble and nested
  items; non-items are expressed as prose.
- backlog pruning: a parent item cannot be pruned while nested items remain.
- milestone ownership: each backlog id may occur in at most one milestone `sourceItems` list.
- mutation: identity allocation freezes the repository prefix and invalidates the facade's cached
  graph so the next read observes the write.
- failure: missing targets, ambiguous handles, invalid graph state, or duplicate ownership produce a
  failed result or doctor finding rather than guessing an identity.
