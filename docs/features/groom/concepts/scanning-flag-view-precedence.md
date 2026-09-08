---
type: concept
slug: scanning-flag-view-precedence
title: Scanning flag view precedence
---
# Scanning flag view precedence

[Dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) and [scanning flag
documentation views](scanning-flag-documentation-views.md) both describe
`groom/groom/state.py::SCANNING`, and neither supersedes the other. The source declares the
value once, with no alternate implementation anywhere in the codebase — there is nothing here
for a selection rule to rank.

[Dashboard discovery scanning flag](dashboard-discovery-scanning-flag.md) is the semantic
reference: the flag's meaning, lifecycle, writers, readers, and UI effect. [Scanning flag
documentation views](scanning-flag-documentation-views.md) is the boundary index: it names
which of the semantic, module-inventory, or payload-input view answers a given question. Read
the first for what the flag means and does; read the second to find the view that matches the
question being asked. Neither is a competing implementation of the flag — they document the
same value at different boundaries, and this concept exists only so a reader arriving at either
one can learn that the other is not a rival.

- rule: no source-level ranking exists between these two views; read [dashboard discovery
  scanning flag](dashboard-discovery-scanning-flag.md) for the flag's semantics and [scanning
  flag documentation views](scanning-flag-documentation-views.md) to find the view matching the
  question being asked
