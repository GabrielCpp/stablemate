---
type: concept
slug: turn-usage-measurements
title: Turn usage measurements
---
# Turn usage measurements

`TurnUsage` records independent measurements rather than seven alternative representations of
the same value. The token fields, cost, and duration retain the data each backend reported;
unreported measurements stay `None`. During multi-step turns, token quantities and cost are
accumulated, while duration is replaced by the latest report.

No field outranks or replaces another. Consumers select the measurement that answers their
question and treat an absent value as unreported, rather than substituting zero or reading a
different field as an equivalent.

- code: `workhorse/workhorse/runner/usage.py::TurnUsage`
- rule: use each field only for its named measurement; absent values are unreported and no field is a substitute for another
- detail: [Turn usage model](turn-usage-model.md)
