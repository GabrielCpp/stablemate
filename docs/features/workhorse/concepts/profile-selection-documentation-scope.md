---
type: concept
slug: profile-selection-documentation-scope
title: ProfileSelection documentation scope
---
# ProfileSelection documentation scope

`ProfileSelection` has one implementation: the mutable `name` box declared in
`ladder.py`. The related concepts describe different reader needs rather than competing ways to
select a profile.

Read [ProfileSelection](profile-selection.md) for the box's state contract: its default,
empty-name meaning, and shared-reference behaviour. Read
[AgentRunner.run](run-agent.md) for the runner context that owns the box, constructs it from
run configuration, and changes it through `switch_profile`. The source deliberately keeps
the box minimal: configuration tables are re-read at turn time after the name is selected.

- code: `workhorse/workhorse/runner/ladder.py::ProfileSelection`
- rule: use ProfileSelection for the selected-name state contract; use AgentRunner.run for the runner lifecycle that reads and changes that shared state
- detail: [ProfileSelection selection guidance](profile-selection-guidance.md)
