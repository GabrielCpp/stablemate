---
type: concept
slug: author-story-author-prompt-contracts
title: Author story-author prompt contracts
---
# Author story-author prompt contracts

The story-author package contains four agent-facing templates under
`workflows/src/workhorse_workflows/author/story_author/prompts/`. The [author story-author subflow](author-story-author-subflow.md)
renders them from its state methods; each turn receives only the target story paths and the
stage-specific evidence named below. The templates are contracts for one bounded planning action,
not alternate workflow states: they do not select another story, run validation, or commit changes.

The shared prompt static checks ensure that each literal render path exists, every referenced
`workhorse_var` is supplied by its caller, and each model-returning prompt describes the top-level
keys of its declared reply. The package's prompt contracts are also covered by the shared
[workflow prompt static contracts](workflow-prompt-static-contracts.md).

When a story write or validation cannot proceed, the subflow also renders the shared [author
resolve-operator prompt](../author-resolve-operator-prompt.md) with `block_stage: "write-story"`.
That diagnostic turn investigates the epic and preserves its findings for the operator; it does
not decide the product or scope question and the subflow resumes through an operator-awaiting
context.

- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.design_mockup`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.write_story`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.audit_story`
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.rework_story`
- tests: `workflows/tests/test_prompts_exist.py::test_the_prompt_file_is_there`
- tests: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`
- detail: [author story-author subflow](author-story-author-subflow.md)
- detail: [workflow prompt static contracts](workflow-prompt-static-contracts.md)

## Prompt contracts

### design-mockup.md

The design turn runs only when the covered story has a frontend seed whose mockup gate requires
design. It receives `epic`, `story_slug`, `story_dir`, `features_dir`, and `epics_dir`. It reads the
feature book and prior story-local mockups for style and existing surface behavior, then writes
only the current story's `mockup.html`; failure to produce a mockup is non-blocking. Its response
is `MockupResult`: `status`, `surface`, `mockup`, and `notes`. The returned `mockup` path is passed
to the writing turn, including an empty path when design failed.

### write-story.md

The writing turn receives `epic`, `story_slug`, `story_path`, `story_dir`, `features_dir`, and the
optional `mockup_path`. It reads the parent epic, the story's covered seeds, the planning artifact
grammar, and any operator context. It writes only the named story planning artifact with Context,
Acceptance Criteria, Non-Functional Acceptance Criteria, Technical Notes, and the machine-owned
sections preserved. The focused contract is grounded in existing feature-book nodes where present;
new in-scope behavior may be made explicit, but implementation plans and proposed component or
library choices are excluded. A blocked product or scope decision returns `status: "blocked"` with
the question in `notes`; a successful turn returns `status` and `notes` in `WriteStoryResult`.

### audit-story.md

The independent audit receives `epic`, `story_slug`, `story_path`, `story_dir`, `features_dir`, and
any `prior_audit_findings`. It rereads the story, its cited book nodes, and the epic's seed and story
scope, then tries to refute coder-readiness across observable verifiability, grounding and scope,
hidden decisions, changed-journey completeness, classification, and technical grounding. It appends
the independent audit section to the story-local audit artifact and returns `AuditResult`; the
workflow uses `findings`, not free-text `status`, as the verdict. A finding has `id`, one of
`journey`, `chrome`, `transient-feedback`, or `grounding` as `kind`, plus its `target`, `issue`, and
`repair`. An empty findings list is a pass; non-empty findings are routed to bounded rework.

### rework-story.md

The rework turn receives `epic`, `story_slug`, `story_path`, `story_dir`, `features_dir`, optional
`mockup_path`, `validation_errors`, `operator_feedback`, and earlier `prior_attempts` when the
caller supplies them. It changes only the story-local planning artifacts named by the task and
addresses every supplied validation or audit finding without rewriting correct material. It leaves
dependencies and fixtures under their owning workflow stages, resolves open decisions when the
existing epic or evidence settles them, and returns `status` and `notes` in the same
`WriteStoryResult` shape as the writing turn. Operator feedback is applied within the existing epic
scope; a request that requires a new product or scope decision returns `status: "blocked"`.
