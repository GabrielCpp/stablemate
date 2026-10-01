# survey

The survey kit that the rubric surveyor and the parity surveyor share.

## Map

- `backlog.py`: the generated, marker-fenced section a survey writes into the backlog.
- `blueprint.py`: the node registry the survey nodes decorate against.
- `inventory.py`: the frozen unit list: its enumeration rules, its expansion and the split of a unit too big to assess.
- `records.py`: the finding record contract, checked one record at a time and as a coverage gate over all of them.
- `stubs.py`: what the survey gates return under `--dry-run`.
- `units.py`: walking the frozen list: the next pending unit and the status stamped on a finished one.
