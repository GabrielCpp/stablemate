story: SM-01M6CP8CERP74W2EBRG0AW3W1K
date: 2026-11-23
elements: ReadFiles, ReadDiff, ReadRepos
sources: groom/groom/sidecar.py, groom/groom/app.py

A caller that reads a run's tree or diff learns which checkouts the run's workspace holds, so a page can offer a choice between them. The sidecar's `getTree` and `getDiff` add `repos` beside what they carried. The same walk that finds the checkout an empty `repo` reads builds the list, so the terminal client reads what it read before.

`/files/` and `/diff/` pass `repos` on only when the sidecar sent it. A read whose workspace cannot be listed names none.

`/repos` is unchanged. It serves the terminal client's repo view, one group per container with run-prefixed labels, and the page does not read it.

This sits beside `a-tree-or-file-read-says-whether-it-failed`.
