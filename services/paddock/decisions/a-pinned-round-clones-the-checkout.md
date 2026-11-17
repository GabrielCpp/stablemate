story: none
date: 2026-11-16
elements: RunTask
sources: paddock/paddock/project.py::pin, paddock/paddock/project.py::release

Without --no-pin-project a round drives a remoteless clone of the checkout paddock is imported from, checked out detached
at its HEAD, with its git directory stashed beside it and `.git` replaced by a gitfile that names a path that does not
exist (paddock/paddock/project.py::pin, fence). The clone costs a few seconds, so the book plays it once in a column
and once in a journey, and every other play passes --no-pin-project. The plain task's second step writes what it sees
of the pin: that it is pinned, that it is fenced and that it has no remote. Release deletes the clone when the round
ends.

The pinned round shows `pinned=True` in its note and `"pinned": true` in the ledger. The unpinned one shows both as
False, and has no fence to look at.
