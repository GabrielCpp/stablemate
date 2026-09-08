---
type: concept
slug: gate-status-parser-documentation-contexts
title: Gate status parser documentation contexts
---
# Gate status parser documentation contexts

The two method nodes describe the same Groom facade from different reader
contexts. `groom/groom/gates.py::status_of` delegates status-line parsing to
the shared Workhorse gate-file implementation; it does not provide two parser
implementations to choose between.

Use [operator gate context file status parser](../operator-gate-context-file.md#method-status-of)
when determining what a gate-file status line accepts and what a caller receives
from a full file or prefix. Use [status-of](groom-gates-module.md#status-of)
when determining the Groom module's public pure-helper boundary and its
relationship to the other gate helpers. Neither method supersedes the other:
they are complementary documentation views of the same callable.

- code: groom/groom/gates.py::status_of
- rule: select the operator gate context file method for file-format parsing semantics and the Groom gates module method for the module API boundary; neither view is preferred or deprecated.
