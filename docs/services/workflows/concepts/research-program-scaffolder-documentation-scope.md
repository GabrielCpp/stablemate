---
type: concept
slug: research-program-scaffolder-documentation-scope
title: Research program scaffolder documentation scope
---
# Research program scaffolder documentation scope

`new_program.py::main` is a single scaffolding entry point with separate but complementary
documentation concerns. Its arguments and writes define the operator lifecycle, while its
conditional `progress_path` and `result_branch` entries and unconditional envelope and containment
entries define how `program.yml` is interpreted. The implementation establishes no ranking between
these concerns: both describe the same command from distinct reader contexts.

Read the scaffolder concept when creating a program directory or understanding generated outputs and
overwrite behavior. Read the manifest field-selection concept when choosing an override or
interpreting the generated manifest's resource and containment settings. Neither replaces the other.

- rule: use the scaffolder concept for the command lifecycle and the manifest field-selection concept for `program.yml` values; both are required to understand the one `new_program.py::main` entry point, and neither is preferred
