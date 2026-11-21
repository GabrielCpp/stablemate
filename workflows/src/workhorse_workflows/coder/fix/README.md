# fix

The fix lane of the coder workflow. It drains the items the coder filed into the backlog. One owner session takes each item end to end. It fixes and QAs the item through subagents, and the run checks what it handed back.

## How an item settles

1. `start` draws the next item, seeds it as a story and resolves its paths. An empty section ends the run.
2. `work` runs the owner turn in the item's own session. A `blocked` reply goes to the resolver, then to the operator, and the answer resumes the same session.
3. `check` runs each changed repository's own gates. Anything red goes back to `work` as one report.
4. Gates that still fail after three repair turns block the same way.
5. Clean gates prune the item from the backlog. The `docs` flow then folds it into the book, and the run commits it and draws the next.

The owner turn runs for at most `turn_minutes` minutes (60 by default). A turn still running then is cut and asks the operator, and the answer resumes it on the same conversation. The silence bound and the command cap bound the turn within that.
