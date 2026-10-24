---
type: concept
slug: emit-result-field-roles
title: Emit result field roles
---
# Emit result field roles

`EmitResult` reports the outcome of `emit_artifacts` and `emit_parity_records`, which file a
survey's findings as records on the [debt register](../../ostler/concepts/the-debt-register.md)
and write survey-owned traceability. Its fields are complementary parts of that report rather than
alternative implementations.

Read `emit_ok` for whether the records were filed and the manifest was written. When emission fails, read
`emit_errors` for diagnostic text. Read `bullet_count` for the number of findings that have a record, filed now or found already on the register,
and `emit_note` for the human-readable outcome summary. The schema declares no preference,
deprecation, or replacement relationship among these fields; select the field for the question at
hand rather than substituting one for another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult` @59f51b5b79f1
- rule: use `emit_ok` for the emission outcome, `emit_errors` for failure diagnostics, `bullet_count` for the quantity of findings that have a record, and `emit_note` for the human-readable outcome summary; none substitutes for another
