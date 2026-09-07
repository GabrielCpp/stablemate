---
type: concept
slug: emit-result-field-roles
title: Emit result field roles
---
# Emit result field roles

`EmitResult` reports the outcome of `emit_artifacts`, which writes generated backlog bullets and
survey-owned traceability. Its fields are complementary parts of that report rather than
alternative implementations.

Read `emit_ok` for whether both artifacts were emitted successfully. When emission fails, read
`emit_errors` for diagnostic text. Read `bullet_count` for the number of emitted backlog bullets,
and `emit_note` for the human-readable outcome summary. The schema declares no preference,
deprecation, or replacement relationship among these fields; select the field for the question at
hand rather than substituting one for another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::EmitResult`
- rule: use `emit_ok` for the emission outcome, `emit_errors` for failure diagnostics, `bullet_count` for the emitted backlog-bullet quantity, and `emit_note` for the human-readable outcome summary; none substitutes for another
