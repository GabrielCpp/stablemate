---
type: concept
slug: surface-completeness
title: Surface completeness
---
# Surface completeness

Whether the promised behavior of a book's surface can actually be verified, answered
per surface by `ostler qa assess`. A surface is complete only relative to an explicit
contract and evidence snapshot: zero unaccounted obligations, zero outstanding required
capabilities, and zero required checks lacking applicable execution and sensitivity
evidence. Completeness says the declared contract is proven, not that every possible
behavior was discovered — source inventory coverage is reported separately.

- code: ostler/ostler/qa/assessment.py::assess@a97580592455
- rule: every selected required obligation has exactly one assessment row, and unknown,
  unavailable, excluded and failed obligations are never counted as passed.
- rule: capability, sensitivity and execution evidence are independent dimensions, not
  an ordered status — a later dimension can never fabricate an earlier one, and a
  surface with full capability but no run is `not-run`, not complete.
- rule: evidence is current only for its recorded contract fingerprint; a claim edited
  while its obligation id is kept makes prior evidence stale, because the id-set digest
  a compiled plan names cannot see claim content. Every run records the versioned
  fingerprint of the contract packet it executed against in its `qa-evidence.json`
  (`contractFingerprint` with `fingerprintVersion`), and evidence without that identity
  — legacy, interrupted or malformed — proves nothing.
- rule: an explicitly excluded obligation stays visible with its reason and satisfies
  no other obligation.
- rule: every gap names its owner — the book's author, the tooling, or the environment —
  and a gap kind nobody classified fails the assessment rather than defaulting to a
  passing owner.
- rule: doctor's structural findings on the selected scope's pages join the report as
  their own section, never flattened into tooling gaps; error-severity findings make
  the surface incomplete, warnings stay visible without blocking, and the
  address/environment family is owned by the environment because no book edit can
  supply the missing runtime input.
- rule: assessment is read-only — it compiles, trials witnesses and reads recorded
  evidence, and never starts the product, runs a scenario, or adds a required network
  dependency.
