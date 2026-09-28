# qa

The QA domain code any workflow family can call. Nothing here knows about one family's lanes.

## Map

- `evidence.py`: the QA evidence gate: whether a claimed pass holds up against the proof on disk.
- `runner.py`: bringing a book's stack up and running its compiled plan through ostler.
- `schemas.py`: the QA result models every family shares.
- `support.py`: what a QA node needs around an ostler call: run log reads, source roots and routing notes.
