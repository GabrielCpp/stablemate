story: none
date: 2026-11-17
elements: Unblock, SetStatus

`ostler unblock` clears the stamp a run leaves on a story, and a status is a stamp when it starts with `Blocked`,
`Docs blocked` or `QA give-up` (`ostler/ostler/select.py::is_blocked`). The book reaches a blocked story with
`set-status ... "Blocked: waiting"`, the one blocked status the watch knows.

The command takes one scope: a story id, `--epic`, or `--all`. It refuses none, two or a story and an epic together,
in that order, and then an unknown story or an unknown epic. A scope with no blocked story answers success with
`nothing to unblock`, and with the name it was given when it names a story or an epic.

The restored status is `Not started` unless `--status` gives another, and the summary prints it as typed, so
`unblock --all --status in-progress` says `-> in-progress`. The stories are listed in folder order.
