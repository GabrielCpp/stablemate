---
type: flow
slug: coder-documentation-gate
title: Coder documentation gate
---
# Coder documentation gate

- start: A coder story has completed implementation review, and its reviewed changes are present
  in the working tree with a resolvable story and plan context.
- steps:
  1. The parent coder graph invokes the standalone `docs` flow before QA so QA derives its
     acceptance obligations from the updated as-built book.
  2. The flow resolves the story, affected repositories, source roots, and OKF feature root. A
     repository with no `docs/features/` tree is explicitly not applicable; an existing but
     unreadable OKF graph is a hard failure.
  3. The documentation author merges every changed service, screen, component, interaction,
     command, endpoint, invocation, flow, concept, and format into the complete current book using
     Ostler's scaffold, format, and doctor loop. A genuinely internal change may be reported as
     `not_required` with a precise reason.
  4. When affected sources share the docs Git worktree, deterministic context generation maps
     repository-wide `HEAD..WORKTREE` production changes while excluding configured document
     roots, so shared implementation remains visible. Every changed symbol requires its exact
     citation; a broad file or surface owner cannot hide a newly added
     component. Multi-repo and non-Git docs layouts use scoped doctor findings plus semantic review
     instead of attempting a cross-repository Git diff from the docs root. Unrelated pre-existing
     node findings remain visible but do not expand the story's scope.
  5. An independent documentation reviewer compares the story, implementation diff, and affected
     nodes. It approves only a complete current specification and rejects `not_required` for a new
     service or UI, CLI, HTTP, domain, or format contract.
  6. Deterministic or semantic failures return to a maximum of three authoring repairs; a block or
     exhausted budget reaches a `fail` node and prevents QA or commit.
  7. After QA, regression repair, and the inline fix drain, the parent invokes the same `docs` flow
     again over the final working tree before selecting the story or epic commit node. Epic
     QA-give-up markers and standalone fix-story commits use the same gate. CI and merge
     remediation run without a selected story and are therefore contract-preserving only; they
     must fail and escalate rather than introduce behavior requiring new documentation.
- end: The story reaches QA and later commit only when every applicable documentation pass reports
  a conformant, directly grounded, semantically complete OKF book; missing documentation cannot be
  flagged and bypassed in either story or epic mode.
- code: `base-library/workflows/coder/workflow.yaml`
- verify: `base-library/workflows/coder/tests/test_qa_control_plane.py::test_documentation_flow_is_hard_gated_and_fail_closed`,
  `base-library/workflows/coder/tests/test_flow_phases.py::test_standalone_docs_passes_author_review_and_deterministic_gate`,
  `base-library/workflows/coder/tests/test_story_documentation.py::test_documentation_gate_rejects_surface_only_ownership`
