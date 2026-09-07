---
type: concept
slug: turn-state-fields
title: TurnState field selection
---
# TurnState field selection

`TurnState` records one completed non-Claude turn. Its fields are complementary observations
accumulated by the stream callbacks and process supervisor before `finalize_turn` passes the
completed state to the shared classifier.

There is no source-defined ranking among `result_text`, `session_id`, `diagnostics`, `timed_out`,
and `returncode`: each answers a different question about that same turn. Select the field whose
meaning matches the information being read, rather than treating one as a substitute for another.
`usage` is likewise a separate normalized measurement used for telemetry.

- code: `workhorse/workhorse/runner/backends/turn.py::TurnState`
- rule: select the TurnState field that represents the needed turn observation; the fields have no
  preference order because each holds distinct information
