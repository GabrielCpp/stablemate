---
type: concept
slug: output-cleanup-selection
title: Output cleanup selection
---
# Output cleanup selection

`remove_targets` is the one cleanup operation for every `Managed` scope. Its source first sweeps
managed directories, then removes owned named files, and finally removes only regular files that
match convention-owned patterns. Repository scope supplies the launcher Compose override and
context manifests as convention-owned paths; it does not introduce a second cleanup
implementation.

Use [output installation cleanup](output-installation.md#method-remove_targets) for the complete
contract, including ownership boundaries that apply to every installed output. Use the
[generated agent launcher](generated-agent-launcher.md#remove_targets) only when the question is
how that same cleanup operation disposes of launcher artifacts. Neither view is deprecated.

- code: `farrier/farrier/outputs.py::remove_targets`
- rule: use output installation for the complete cleanup contract; use the generated-agent launcher only for its launcher-artifact context
- prefers: [output installation cleanup](output-installation.md#method-remove_targets)
- detail: [output cleanup documentation](output-cleanup-documentation.md)
