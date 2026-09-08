---
type: concept
slug: author-load-config-documentation-roles
title: Author load_config documentation roles
---
# Author load_config documentation roles

`load_config` is one implementation with one call site's worth of behavior, documented from three
angles because three different flows read it for three different questions. [Author workflow
configuration](../author-config.md) is the canonical spec: every field of the returned `Config`,
every resolution rule, every raised failure, item by item. [Author finalize subflow](author-finalize-subflow.md)
restates it as one of Finalize's own `## Nodes` entries because Finalize calls it directly, in
`setup()`, to resolve epic-mode paths before any gate runs. [Author story-split subflow](story-split-subflow.md)
cites it only under `## Downstream Boundaries`, because story-split delegates configuration
loading to this shared node rather than owning any part of its behavior itself. None of the three
is a competing implementation of the other two, and none is deprecated: they are the same symbol
read for its contract, for one flow's use of it, and for a different flow's boundary with it.

- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`
- rule: read the author configuration format for the complete `load_config` contract; read the finalize subflow node for how Finalize's `setup()` consumes it; read the story-split downstream boundary only to see that story-split delegates to it rather than reimplementing it — none of the three supersedes another

