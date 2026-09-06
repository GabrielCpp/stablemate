---
type: flow
slug: coder-documentation-gate
title: Coder documentation gate
---
# Coder documentation gate

- start: A coder story has completed implementation review.
- start: Its reviewed changes are present in the working tree.
- start: The story and plan context are resolvable.
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
     service or UI, CLI, HTTP, domain, or format contract. Revision requests are numbered checklist
     findings in the typed `DocumentationReview.findings` schema, with exact file/anchor targets
     and defect classes; later reviews receive the previous checklist and first verify whether each
     item was resolved instead of starting a fresh broad review.
  6. Deterministic grounding failures and semantic review failures use separate bounded repair
     counters. A repair pass receives the previous gate/review notes as its complete worklist and
     must make the smallest evidence-backed edits needed to close those findings. A block or
     exhausted budget prevents QA or commit.
  7. After QA, regression repair, and the inline fix drain, the parent invokes the same `docs` flow
     again over the final working tree before selecting the story or epic commit node. Epic
     QA-give-up markers and standalone fix-story commits use the same gate. CI and merge
     remediation run without a selected story and are therefore contract-preserving only; they
     must fail and escalate rather than introduce behavior requiring new documentation.
- end: The story reaches QA and later commit only when every applicable documentation pass reports
   a conformant, directly grounded, semantically complete OKF book.
- verify: exit_status(code=0)
- end: A documentation finding leaves no QA or commit transition available in either story or epic
    mode.
- verify: count(subject="QA or commit transitions after a documentation finding", equals=0)
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_revision_request_reworks_and_carries_the_notes_forward`,
  `workflows/tests/coder/docs/test_flow.py::test_a_revision_request_without_structured_findings_fails_the_flow`,
  `workflows/tests/coder/docs/test_flow.py::test_a_revision_request_with_an_empty_finding_fails_the_flow`,
  `workflows/tests/coder/docs/test_flow.py::test_the_grounding_failure_names_the_symbols_not_the_files`,
  `workflows/tests/coder/docs/test_flow.py::test_the_gates_failure_does_not_spend_the_reviewers_budget`
