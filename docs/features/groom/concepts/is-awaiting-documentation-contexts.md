---
type: concept
slug: is-awaiting-documentation-contexts
title: Is awaiting documentation contexts
---
# Is awaiting documentation contexts

The two method nodes describe the same `groom/groom/gates.py::is_awaiting` callable from
different contexts. In the source, the callable delegates to `status_of(text)` and compares the
result with `AWAITING`; it does not define separate format-specific or module-specific classifiers.

Use the Groom gates module node when learning the module's public helper API and its relationship
to `answer_gate`. Use the operator gate context file node when learning how the classifier applies
the file format's normalized status token. Neither node is preferred for calling the function:
there is one implementation and both descriptions are current views of it.

- code: groom/groom/gates.py::is_awaiting
- rule: use the node whose documentation context answers the reader's question; both identify the same `is_awaiting` callable and neither supersedes the other
