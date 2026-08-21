# Restart survival is code review's obligation, not QA's

**Status:** decided
**Applies to:** every story that touches the link ledger's durability

## The question

[link-follow] promises that a person who follows a short link *arrives at* the
destination. The ledger is therefore durable — a JSON file on disk, not state held in the
memory of the process that wrote it. The question is what QA is asked to *prove* about
that durability, and specifically whether a scenario may require that a link created
before a restart still resolves after one.

## The ruling

It may not. The acceptance criterion is that a created link is **persisted to the on-disk
ledger**, and the evidence is the file: after a successful `POST /links`, the ledger
contains the new key and its destination. Restart survival is a consequence of writing
the ledger to disk and reading it back at construction; it is **code review's** obligation
to confirm that startup path, and a reviewer discharges it by reading that the repository
loads its ledger from the file when it is built.

A QA plan that demands a restart is not stricter. It is unsatisfiable, and a lane that
meets it has cheated.

## Why

The QA runner fixes the process lifecycle for a whole session, not per scenario:
`ostler/ostler/qa/run.py:364` — "The plan is validated first, then executed: start →
scenarios → stop." A `background(...)` entry is contractually a daemon the runner starts
before scenario 1 and stops after the last (`qa-plan-authoring.md:71-80`), and the
plan-lint allowlist bars the process and OS modules that would let a scenario fake the
seam itself. There is no way for a scenario to cross a process boundary.

So an acceptance criterion demanding one can only be discharged by substituting something
that is not runtime evidence — a passing test suite, a manual note — which the QA rules
correctly forbid. The lane that met this criterion first did the right thing and blocked
rather than substitute, which is the outcome this record exists to make unnecessary the
second time.

The gap is the harness's, not this fixture's, and it is recorded as a flex finding in
the benchmark harness that produced this repo — not here. If the harness later grows lifecycle
control, this record is what should be revisited — not the promise, which never changed.
