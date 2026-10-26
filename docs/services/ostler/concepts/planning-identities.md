---
type: concept
slug: planning-identities
title: Planning identities
---
# Planning identities

Ostler mints one immutable full id for each planning entity and keeps a readable name beside it
for the things people browse. A milestone's slug, folder name and title describe a release, and
none of them is its identity. A [debt register](the-debt-register.md) record's summary describes
the work, and its id is its folder name. Short handles are display and command-input forms only.
Ostler never writes one down, because a later id can make an existing handle ambiguous and force
it to lengthen.

Every id lives in one workspace-wide space: epics, seeds, stories, milestones, features, register
records and [decision records](decision-records.md) all draw from it. A new record or decision is
minted by the same allocator a story uses. A record imported from an old list may keep an id with
no ULID, and that id holds its place in the space all the same. It has no short handle, so a
command names it in full.

Milestones live in readable `docs/milestones/<slug>/milestone.md` folders and carry a minted id of
their own. Their `sourceItems` list holds the full ids of the register records whose product
outcome the milestone owns. Creating a milestone records its first list, and
`milestone set-source-items` replaces it when an active release absorbs more intake. Both resolve
a short handle to its full id before they write.

- code: ostler/ostler/ids.py::allocate@0d0049c06fca
- code: ostler/ostler/ids.py::abbreviate@0d0049c06fca
- code: ostler/ostler/ids.py::expand@0d0049c06fca
- code: ostler/ostler/ids.py::claimed@0d0049c06fca
- code: ostler/ostler/ids.py::resolve@0d0049c06fca
- code: ostler/ostler/crud.py::create_milestone@afec09b52ae2
- code: ostler/ostler/crud.py::set_milestone_source_items@afec09b52ae2
- code: ostler/ostler/doctor.py::_check_milestones@deed3045a8c9
- tests: ostler/tests/test_ids.py::test_handle_stays_short_for_a_burst_and_expands_round_trip
- tests: ostler/tests/test_ids.py::test_handle_lengthens_when_fingerprints_collide
- tests: ostler/tests/test_crud.py::test_create_milestone_allocates_id_and_records_source_items
- tests: ostler/tests/test_register.py::test_known_ids_include_every_record_on_the_shelf
- tests: ostler/tests/test_adr.py::test_the_minted_id_is_in_the_workspace_id_space

## Contract

- persisted identity: the full `<PREFIX>-<26-character ULID>` that Ostler mints. The prefix is
  frozen in `.agents/ids.json` on the first mint.
- imported identity: an id a hand-written list already carried, kept as written when it is one
  path-safe segment and no other entity holds it.
- readable name: mutable prose or a folder slug. Every reference to the entity goes through its
  id instead.
- display handle: the prefix and the shortest slice of a hash of the ULID that no other id shares,
  at least the minimum length. A command accepts a handle wherever it takes an id and expands it
  to the full id before any write. An id with no ULID is its own handle.
- uniqueness: a write refuses an id the workspace already holds, whatever kind of entity holds it.
- milestone ownership: each record id may occur in at most one milestone's `sourceItems` list.
  `ostler doctor` reports a second owner.
- mutation: a write through the facade drops its cached graph, so the next read sees the write.
- failure: a missing target, an ambiguous handle or a taken id produces a failed result or a
  doctor finding in place of a guessed identity.
