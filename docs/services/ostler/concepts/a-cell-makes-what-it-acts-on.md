---
type: concept
slug: a-cell-makes-what-it-acts-on
title: A cell makes what it acts on
---
# A cell makes what it acts on

A cell of a lifecycle matrix is one action taken in one scene. The scene's steps arrange the scene by calling the service the way a user would: they create the records the column aims at, and the ids come from the service's answers. A fixture learns its id from the answer that created it, and a book never writes an id the service issues.

Nothing is torn down. The backstage of an environment arranges state no route can write, and it has no wipe, sweep or delete. A record only the outside world makes, such as a mail arriving or a stock feed, is arranged by an outside event, never by writing to the store.

Two kinds of record cannot be made by the cell, and each has its own rule.

- A record shared by every account and keyed by a name, such as one policy per category and priority, has no copy a cell can own. The model starts with what the seed made, and the surface puts the records back before each cell. It reads them through the product's own calls, as an account allowed to edit them, removes what the seed did not make and writes back what differs. It never writes to the store.
- A record that keeps acting after its cell ends, such as an open ticket whose timer breaches hours later and pages a team, is ended. The surface ends what the last cell opened, through the other service's own call, when it restores and when it stops.

An outcome that counts an account's whole history, such as a quota, a usage total or a first-time banner, needs an actor that gets a new account per cell, declared with its reason. A write that changes the account itself, such as a purchase or a setting, belongs to such an actor too, because a standing account that took it would carry it into every later cell.

- rule: a cell makes what it acts on, and nothing it makes is torn down
- rule: a shared record is put back through the product's own calls, never by a write to the store, and the surface says which calls it uses
- rule: a record that keeps acting is ended through the product's own call when the cell's surface restores or stops
- rule: an outcome that counts an account's history, or a write that changes the account itself, belongs to an actor with a fresh account per cell
- rule: the backstage sets the row the service made when the service creates a companion row for every record, and never inserts a second one beside it
- rule: a run on a shared environment changes the shared records it puts back under whoever else uses it, so the book's report lists them
- code: ostler/ostler/book/cells.py::one@655a8b6469b4
- code: ostler/ostler/book/httpsurface.py::HttpSurface@44aee6cc091e
- code: ostler/ostler/book/backstage.py::Backstage@b9527ba87e23
- code: ostler/ostler/book/cast.py::Actor@35bf5f38293a
- tests: ostler/tests/test_book_cells.py::test_two_read_cells_of_one_scene_share_an_arrangement
