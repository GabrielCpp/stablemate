---
type: concept
slug: profile-selection-guidance
title: ProfileSelection selection guidance
---
# ProfileSelection selection guidance

`ProfileSelection` is one shared mutable selected-name box, not a separate profile-resolution
implementation. `AgentRunner.run` reads that box on each turn, and `switch_profile` changes its
`name` after validating the requested profile. The configuration tables remain outside the box and
are re-read for each turn.

Use [ProfileSelection](profile-selection.md) for the selected-name state contract: its empty-name
default and why every copied runner reference shares it. Use [AgentRunner.run](run-agent.md) for
the runner lifecycle that reads that state while resolving and running a turn. Use
[ProfileSelection documentation scope](profile-selection-documentation-scope.md) when deciding
which page owns a statement about this shared box.

These are complementary views of the same source symbol, not alternatives or a deprecation
relationship; no source-level ranking exists.

- rule: choose the document by the question it answers: state contract, runner lifecycle, or documentation ownership; none replaces another
