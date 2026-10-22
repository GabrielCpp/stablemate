---
type: concept
slug: output-cleanup-documentation
title: Output cleanup documentation
---
# Output cleanup documentation

`remove_targets` has one implementation whose `Managed` argument supplies the directories,
named files, and convention-owned patterns it cleans. Repository scope includes launcher
artifacts in that input; it does not select a separate launcher cleanup path.

Start with [output installation cleanup](output-installation.md#method-remove_targets) for the
complete ownership and deletion contract. Use [generated agent launcher](generated-agent-launcher.md#remove_targets)
when that same contract must be related to generated launcher artifacts. [Output cleanup
selection](output-cleanup-selection.md) summarizes that choice; it is not a third implementation.

- rule: use output installation cleanup for the general contract and the generated-agent launcher only for repository-scope launcher artifacts
- prefers: [output installation cleanup](output-installation.md#method-remove_targets)
