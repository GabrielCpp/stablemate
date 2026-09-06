---
type: concept
slug: output-cleanup
title: Output cleanup
---
# Output cleanup

`remove_targets` has one implementation. It cleans a repository according to the `Managed` scope
passed by its caller: it scans managed directories for marked files, removes marked named files,
and removes regular files matching that scope's convention-owned patterns. It leaves unowned files
and non-file pattern matches in place.

Use the [output-installation method](output-installation.md#method-remove_targets) for the complete
cleanup contract. The [generated-agent-launcher method](generated-agent-launcher.md#remove_targets)
is the same operation in the launcher context, where generated repository artifacts are relevant;
it is not an alternative implementation or a legacy cleanup path.

- code: `farrier/farrier/outputs.py::remove_targets`
- rule: use output installation for the general cleanup contract; use the generated-agent launcher
  context only when relating cleanup to its generated artifacts
- prefers: [output installation cleanup](output-installation.md#method-remove_targets)
- detail: [output cleanup selection](output-cleanup-selection.md)
- detail: [output cleanup documentation](output-cleanup-documentation.md)
