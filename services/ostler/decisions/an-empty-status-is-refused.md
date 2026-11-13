story: SM-01M7APW2Y9KF8E5HXCCWET7Z1S
date: 2026-11-13
elements: SetStatus

`ostler set-status` refuses a status that is empty or made only of spaces and tabs. The refusal prints
`status of '<story>' cannot be empty` on standard output, exits 1 and writes no file. It lives in
`ostler/ostler/crud.py::set_status`, which the command line and `Ostler.set_status` share, so both refuse alike.

The story lookup runs first. An unknown story keeps its own refusal, `no story with id '<story>'`, whatever the status.

Every other text stays accepted, `Done` and `Blocked: waiting` among them, because the repository names no list of
story statuses. The spaces and tabs around a status are dropped before it is written, and the success line prints
the status without them. Whether a fixed list of statuses should exist stays open, as entry 1 of
`UNDERSPECIFIED.md`.

The book plays the refusal with an empty status, a status of spaces and a status of a tab, each on a known story and
the empty one on an unknown story, and it watches both the frontmatter line and the Implementation Status line so a
refused call is judged to change neither. `Ostler(root).set_status(story, "")` answers a failed result with the same
message; the book reaches the tool through the command line only, so the API half is checked by the story's QA.
