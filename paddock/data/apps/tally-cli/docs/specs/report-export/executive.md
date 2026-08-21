---
type: spec.executive
---

# Executive Summary: Read the Tally Back, for a Person and for a Pipe

Ships the two ways the ledger is read: `tally report`, which totals it, and `tally export`,
which writes it out as CSV.

The criterion worth reading twice is the one about streams. `tally report --json` must put
exactly one JSON object on stdout and nothing else, with every human-facing line on stderr.
This is where the discipline the earlier stories adopted stops being a convention: a progress
line on stdout does not make the report worse, it makes it unparseable, and the failure
surfaces in whatever was parsing it rather than here. The report itself is checkable against
itself — the total equals the sum of the per-person figures, and the currency is the one `init`
recorded.

`export` writes its header unconditionally, empty ledger included. An export whose shape
depends on its content is an export every reader has to sniff before parsing, and the first
thing every reader of a CSV does is skip line one.

One added module and one changed one, still stdlib only. See `plan.md` for the shape and
`plan-context.json` for the service manifest.
