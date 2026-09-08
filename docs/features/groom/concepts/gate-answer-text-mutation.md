---
type: concept
slug: gate-answer-text-mutation
title: Gate answer text mutation
---
# Gate answer text mutation

`groom/groom/gates.py::apply_answer` has one implementation and two complementary
documentation views. The [Groom gates module](groom-gates-module.md#apply-answer)
view is for callers of the pure helper and its boundary from the asynchronous answer
operation. The [operator gate context file](../operator-gate-context-file.md#method-apply-answer)
view is for the resulting artifact: the status replacement, answer paragraph, and
preservation rules that its consumers observe.

The implementation delegates the first `STATUS:` line replacement to
`workhorse.gates.set_status`, keeping the header compatible with the workflow-side
reader and writer. Groom then strips a submitted answer and appends a non-blank value
as a final paragraph. Neither documentation view is a different implementation or a
replacement for the other; choose the view that matches whether the reader needs the
callable contract or the context-file contract.

- code: groom/groom/gates.py::apply_answer
- rule: use the Groom gates module method for the pure helper API and call boundary; use the operator gate context file method for the observable file-text contract. Both describe the same `groom/groom/gates.py::apply_answer` implementation.
