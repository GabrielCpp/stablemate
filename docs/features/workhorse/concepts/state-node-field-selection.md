---
type: concept
slug: state-node-field-selection
title: State node field selection
---
# State node field selection

`StateNode` is one static description of a live workflow state, not a choice among alternative
representations. Read the field for the information needed: `name` identifies the state;
`edges` lists its unique statically discovered transitions; `steps` lists its unique discovered
engine seams in source order; and `opaque` records that source inspection failed, making the
transitions and steps unknown. The `StateNode` field names no longer compete once that scope is
clear: a graph reader may need any compatible combination of them.

- code: `workhorse/workhorse/pyflow/graph.py::StateNode`
- rule: select the `StateNode` field for the distinct static-state information being read; its fields are complementary and have no ranking or replacement relationship
