---
type: concept
slug: research-program-manifest-field-selection
title: Research program manifest field selection
---
# Research program manifest field selection

The manifest fields are complementary settings written by the program scaffolder, not alternative
implementations. Select the field for the aspect of a program being declared: `code_root` names the
experiment source; `progress_path` and `result_branch` change their derived locations only when an
operator supplies their corresponding overrides; and the envelope fields together state the machine
resources and containment tier under which a measurement is trusted.

No ranking exists among these fields. The scaffolder always writes the envelope and containment
settings, while it writes the path and branch entries only for explicit overrides; leaving a resource
axis at `0` or `none` declares that no bound is available for that axis.

- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- rule: choose the manifest field that matches the program attribute being declared; use an override field only to replace its derived default, and use each envelope field together with `min_containment` to declare executable measurement constraints
- detail: [research program scaffolder documentation scope](research-program-scaffolder-documentation-scope.md)
