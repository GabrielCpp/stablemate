story: SM-01M6CN5KZ826G63H89XZGBREEW
date: 2026-11-22
elements: ReadFleet
sources: services/groom/stack.py

A play with `--fresh-data` reloads the data before the stack starts. The book's groom keeps its database, its home and its
config in a temporary folder that `stack()` makes at each start, so no start sees a record an earlier play left. The
stack's `fresh` command is `true` for that reason: the reload has nothing to restore, and the play still has a stated
way to reload. A play that attaches to a groom already running, with `--no-stack`, gets no reload and starts on whatever
that groom holds.

The book's groom listens on port 18893, and `GROOM_BOOK_PORT` overrides it. Groom's own default is 18792, and a machine
that runs a workhorse run already has a groom there. A book on 18792 died at start with "address already in use".
