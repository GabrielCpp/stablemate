---
type: spec.executive
---

# Executive Summary: Approve or Deny a Claim

Adds the only transition a claim has after it is filed: an adjuster moves it to `Approved` or
`Denied`, with a note, against the version they read.

The criterion worth reading twice is that neither of the two rules that matter is observable
inside one request. The compare-and-swap needs two writes off one reading — an accepted decision
and then a second quoting the version the first consumed — and the durability of the result needs
a read from a process that is not the one that wrote it. A single accepted `200` satisfies a
service that ignores `version` entirely and one that keeps its decisions in memory.

The role gate is checked before the claim is looked up, so a holder who tries to decide learns
nothing about the claim. See `plan.md` for the implementation shape and `plan-context.json` for
the machine-readable service manifest.
