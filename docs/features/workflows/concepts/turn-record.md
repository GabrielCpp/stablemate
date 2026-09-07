---
type: concept
slug: turn-record
title: Coder Turn Record
---
# Coder Turn Record

`Turn` is the resolved prompt envelope for one coder-agent call. Its fields are complementary
parts of one record, not competing ways to represent a turn: callers pass `prompt` and `args`
to rendering, then pass `returns` to the agent so the reply is parsed as the same model whose
schema was rendered in `args`. `turn` constructs all three together; when no body override is
available, only the optional body entries are omitted from `args`.

- code: `workflows/src/workhorse_workflows/coder/shared/roles.py::Turn`
- rule: use the complete `Turn` record for a resolved coder call; read `prompt` for the flow-owned envelope, `args` for rendering context, and `returns` for the reply model
