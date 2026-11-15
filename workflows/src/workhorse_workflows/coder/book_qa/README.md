# book_qa

The book lane of the coder workflow. A story that touches a service with an executable book (`services/<name>/service.py` under the book root: the repo root in a monorepo, the artifacts folder in a multi-repo workspace) has that service judged by a run of the book. The scenario QA in `qa/` is a separate lane, and the main loop hands off to this one first. Both return a `QaFlowResult`.

The lane costs one seat turn. The verdict costs no model call. A story with no covered service ends here as `passed` with no agent call and no stack.

## How a story's book pass settles

1. `start` lists the story's covered services: the declared ones that have a book, then every other service with a book whose app source the story's commits changed (`ostler book stale --since <story base>`, the story base being the commit its own work started from). It then leases a copy of the stack and brings it up. A stack that is not up goes to the operator, never to the seat. A `book-qa.json` in the spec dir holds the calls a passed check played, so a second visit for the same story goes straight to `check`.
2. `work` runs the `qa-book` seat. It names the calls the story touches, brings each covered book up to the story's claims and reports a finding for each claim the app does not meet. A `blocked` reply asks the operator.
3. `check` runs `ostler book check` for each covered service, then plays its calls with `ostler book run --only <calls> --copy <lease>`. Exit 1 or 2 goes back to the seat with the tail of the output. Exit 3 means the environment could not be judged, and it asks the operator without a finding or a lap. A seat that names no call for a covered service goes back to the seat.
4. Exit 0 on every service with no finding runs `ostler book verified` for each covered service, so the book records the app commit it was judged at. A book already verified at the app's HEAD is left alone, so a second visit stamps nothing twice. A refusal goes back to the seat with the output. Then the lane lands the changed paths under each covered `services/<name>/` as one `test` commit with the story's footer, and writes `book-qa.json`. A changed product path outside those folders refuses the commit and goes back to the seat. The lane ends as `refix` with the seat's findings, or as `passed`. A finding stops the story even on a green run, because a declared defect makes the run green by design.

Checks that still fail after three repair turns park the run at the operator gate.
