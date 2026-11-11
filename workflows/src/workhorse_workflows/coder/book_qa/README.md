# book_qa

The book lane of the coder workflow. A story that touches a service with an executable book (`services/<name>/service.py` under the repo root) has that service judged by a run of the book. The scenario QA in `qa/` is a separate lane, and the main loop hands off to this one first. Both return a `QaFlowResult`.

The lane costs one seat turn. The verdict costs no model call. A story with no covered service ends here as `passed` with no agent call and no stack.

## How a story's book pass settles

1. `start` lists the story's covered services, leases a copy of the stack and brings it up. A stack that is not up goes to the operator, never to the seat. A `book-qa.json` in the spec dir holds the calls a passed check played, so a second visit for the same story goes straight to `check`.
2. `work` runs the `qa-book` seat. It names the calls the story touches, brings each covered book up to the story's claims and reports a finding for each claim the app does not meet. A `blocked` reply asks the operator.
3. `check` runs `ostler book check` for each covered service, then plays its calls with `ostler book run --only <calls> --copy <lease>`. Exit 1 or 2 goes back to the seat with the tail of the output. Exit 3 means the environment could not be judged, and it asks the operator without a finding or a lap. A seat that names no call for a covered service goes back to the seat.
4. Exit 0 on every service lands the changed paths under each covered `services/<name>/` as one `test` commit with the story's footer, and writes `book-qa.json`. A changed product path outside those folders refuses the commit and goes back to the seat. The lane ends as `refix` with the seat's findings, or as `passed`. A finding stops the story even on a green run, because a declared defect makes the run green by design.

Checks that still fail after three repair turns park the run at the operator gate.
