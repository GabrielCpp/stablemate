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
- code: `workflows/src/workhorse_workflows/author/story_author/prompts/design-mockup.md`
- code: `workflows/src/workhorse_workflows/author/story_author/prompts/write-story.md`
- code: `workflows/src/workhorse_workflows/author/story_author/prompts/audit-story.md`
- code: `workflows/src/workhorse_workflows/author/story_author/prompts/rework-story.md`
- code: `workflows/tests/author/test_prompt_authority.py::test_writer_can_define_in_scope_behavior_without_prior_okf_authority`
- code: `workflows/tests/author/test_prompt_authority.py::test_writer_separates_build_scope_from_regression_invariants`
- code: `workflows/tests/author/test_prompt_authority.py::test_writer_records_concise_grounded_technical_notes`
- code: `workflows/tests/author/test_prompt_authority.py::test_auditor_does_not_demand_prior_citations_for_new_behavior`
- code: `workflows/tests/author/test_prompt_authority.py::test_auditor_respects_the_bare_minimum_story_boundary`
- code: `workflows/tests/author/test_prompt_authority.py::test_reworker_makes_in_scope_choices_instead_of_blocking`
- code: `workflows/tests/author/test_prompt_authority.py::test_mutating_turns_leave_validation_and_delivery_to_author`
- code: `workflows/tests/author/test_prompt_authority.py::test_mockup_inspection_does_not_leave_screenshot_collateral`
- code: `workflows/tests/author/test_write_story_prompt.py::test_the_backend_only_story_is_given_something_to_ground_in`
- code: `workflows/tests/author/test_write_story_prompt.py::test_the_absent_mockup_is_not_a_block`
- code: `workflows/tests/author/test_write_story_prompt.py::test_the_mockup_arm_survives_for_the_story_that_has_one`
- tests: `workflows/tests/test_prompts_exist.py::test_the_prompt_file_is_there`
- tests: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`
- tests: `workflows/tests/author/test_prompt_authority.py::test_writer_can_define_in_scope_behavior_without_prior_okf_authority`
- tests: `workflows/tests/author/test_prompt_authority.py::test_writer_separates_build_scope_from_regression_invariants`
- tests: `workflows/tests/author/test_prompt_authority.py::test_writer_records_concise_grounded_technical_notes`
- tests: `workflows/tests/author/test_prompt_authority.py::test_auditor_does_not_demand_prior_citations_for_new_behavior`
- tests: `workflows/tests/author/test_prompt_authority.py::test_auditor_respects_the_bare_minimum_story_boundary`
- tests: `workflows/tests/author/test_prompt_authority.py::test_reworker_makes_in_scope_choices_instead_of_blocking`
- tests: `workflows/tests/author/test_prompt_authority.py::test_mutating_turns_leave_validation_and_delivery_to_author`
- tests: `workflows/tests/author/test_prompt_authority.py::test_mockup_inspection_does_not_leave_screenshot_collateral`
- tests: `workflows/tests/author/test_write_story_prompt.py::test_the_backend_only_story_is_given_something_to_ground_in`
- tests: `workflows/tests/author/test_write_story_prompt.py::test_the_absent_mockup_is_not_a_block`
- tests: `workflows/tests/author/test_write_story_prompt.py::test_the_mockup_arm_survives_for_the_story_that_has_one`
- detail: [author story-author subflow](author-story-author-subflow.md)
- detail: [workflow prompt static contracts](workflow-prompt-static-contracts.md)

The eight `test_prompt_authority.py` symbols above each pin a specific prompt-authority contract
that the `story_author` and `epic_edit` envelopes must hold in lockstep across every prompt copy.
The contracts the tests enforce — over both copies of each envelope — are themselves the behaviour
each symbol carries:

- `test_writer_can_define_in_scope_behavior_without_prior_okf_authority` asserts that every
  `write-story.md` copy declares "Acceptance Criteria become the authoritative contract", that
  "Absence from the existing OKF book is not by itself a reason to block", and that new decisions
  "must not contradict existing documented behavior".
- `test_writer_separates_build_scope_from_regression_invariants` asserts every `write-story.md`
  copy separates the build scope (Acceptance Criteria) from regression invariants
  (Non-Functional Acceptance Criteria) and that the regression side "does not add implementation
  scope" while "QA must still prove" each non-functional criterion.
- `test_writer_records_concise_grounded_technical_notes` asserts every `write-story.md` copy
  requires Technical Notes grounded by a `path::symbol` citation into "original or prior
  implementation".
- `test_auditor_does_not_demand_prior_citations_for_new_behavior` asserts every `audit-story.md`
  copy refrains from refuting new in-scope behavior "merely because no prior OKF node defines it"
  and only refutes behavior that "contradicts cited existing behavior".
- `test_auditor_respects_the_bare_minimum_story_boundary` asserts every `audit-story.md` copy
  judges only the behavior changed by the story's covered seeds, does not "demand endpoint names,
  request or response schemas", "does not import every guard, state, interaction, or journey", and
  treats "existing guards, chrome, states, and flows outside those covered seeds" as out of scope.
- `test_reworker_makes_in_scope_choices_instead_of_blocking` asserts every `rework-story.md` copy
  "makes the concrete choice in the Acceptance Criteria" and does "not block merely because the
  existing OKF book is silent".
- `test_mutating_turns_leave_validation_and_delivery_to_author` asserts that across ten mutating
  prompts (`epic_author/write-epic`, `story_split/split-stories`, the four `story_author` prompts,
  `finalize/resolve-integrity`, `milestone/build-milestone`, `epic_split/split-epics`, and
  `epic_split/rework-epic-split`) none of them "install dependencies, run repository-wide checks,
  stage, commit, push, or alter branches/remotes" and that "Author validates and delivers after
  all authoring turns finish".
- `test_mockup_inspection_does_not_leave_screenshot_collateral` asserts every `design-mockup.md`
  copy treats browser inspection as ephemeral, that the prompt "does not save screenshots,
  evidence, or rendered exports", and that the "story-local `mockup.html` is this turn's only
  output".

The three `test_write_story_prompt.py` symbols above each pin a prose-drift contract that every
`write-story.md` copy must hold in lockstep with the parameterization the deterministic author
gates actually produce. Both `author/main/nodes/stories.py` gates stand down on a backend-only
story: `check_story_grounding` puts its cite-a-node requirement behind `if okf.graph.ui_nodes:`,
and `check_mockup_needed` decides from `layers:` on the covered seeds, so a story tagged
`layers: backend` is rendered with `mockup_path=""`. The prompt must still give such a story
something to ground the Context in and tell the writer not to block on the missing artifact — a
stricter pair of instructions that demands an OKF node *or* a mockup, in a repo whose book is not
built yet, hands the writer two empty arms and parks the round at the operator gate. Prose drift
is invisible to ruff, ty, and review, so each of the three symbols renders the template with the
backend-only parameterization the gates produce and asserts the third arm survives in the prose
the author reads:

- `test_the_backend_only_story_is_given_something_to_ground_in` asserts every `write-story.md`
  copy renders the instruction "Ground the Context in the epic's seeds this story `covers`" and
  the phrase "new and undocumented" for a story whose `features_dir` is set but whose book holds
  no node and whose `mockup_path` is empty. An assertion that passes against the prose this test
  exists to replace is no assertion, so the check matches the instruction to ground in the seeds
  rather than the words alone.
- `test_the_absent_mockup_is_not_a_block` asserts every `write-story.md` copy renders the
  permission "its absence is not a block" and the explicit instruction "Do not block for the
  want of a node or a mockup" for the same backend-only parameterization. Mentioning the seeds
  is not enough — an earlier drift asked the writer to *link* the mockup — so this symbol
  proves the absence clause survives.
- `test_the_mockup_arm_survives_for_the_story_that_has_one` asserts every `write-story.md` copy
  still renders the mockup link arm for a story whose `mockup_path` is supplied: the literal
  `./mockup.html` path and the phrase "link it from Context as the source of truth". The fix
  widens the disjunction; this symbol proves the original arm was not replaced.

## Prompt contracts

### design-mockup.md

The design turn runs only when the covered story has a frontend seed whose mockup gate requires
design. It receives `epic`, `story_slug`, `story_dir`, `features_dir`, and `epics_dir`. It reads the
feature book and prior story-local mockups for style and existing surface behavior, then writes
only the current story's `mockup.html`; failure to produce a mockup is non-blocking. Its response
is [MockupResult](../mockup-result.md): `status`, `surface`, `mockup`, and `notes`. The returned
`mockup` path is passed to the writing turn, including an empty path when design failed. Browser
inspection is ephemeral: screenshots, evidence, and rendered exports are not written to the
repository.

### write-story.md

The writing turn receives `epic`, `story_slug`, `story_path`, `story_dir`, `features_dir`, and the
optional `mockup_path`. It reads the parent epic, the story's covered seeds, the planning artifact
grammar, and any operator context. It writes only the named story planning artifact with Context,
Acceptance Criteria, Non-Functional Acceptance Criteria, Technical Notes, and the machine-owned
sections preserved. The focused contract is grounded in existing feature-book nodes where present;
new in-scope behavior may be made explicit, but implementation plans and proposed component or
library choices are excluded. A blocked product or scope decision returns `status: "blocked"` with
the question in `notes`; a successful turn returns `status` and `notes` in [WriteStoryResult](../write-story-result.md).

### audit-story.md

The independent audit receives `epic`, `story_slug`, `story_path`, `story_dir`, `features_dir`, and
any `prior_audit_findings`. It rereads the story, its cited book nodes, and the epic's seed and story
scope, then tries to refute coder-readiness across observable verifiability, grounding and scope,
hidden decisions, changed-journey completeness, classification, and technical grounding. It appends
the independent audit section to the story-local audit artifact and returns `AuditResult`; the
workflow uses `findings`, not free-text `status`, as the verdict. A finding has `id`, one of
`journey`, `chrome`, `transient-feedback`, or `grounding` as `kind`, plus its `target`, `issue`, and
`repair` as specified by [AuditFinding](../audit-finding.md). The response is [AuditResult](../audit-result.md);
an empty `findings` list is a pass, while non-empty findings are routed to bounded rework.

### rework-story.md

The rework turn receives `epic`, `story_slug`, `story_path`, `story_dir`, `features_dir`, optional
`mockup_path`, `validation_errors`, `operator_feedback`, and earlier `prior_attempts` when the
caller supplies them. It changes only the story-local planning artifacts named by the task and
addresses every supplied validation or audit finding without rewriting correct material. It leaves
dependencies and fixtures under their owning workflow stages, resolves open decisions when the
existing epic or evidence settles them, and returns `status` and `notes` in the same
`WriteStoryResult` shape as the writing turn. Operator feedback is applied within the existing epic
scope; a request that requires a new product or scope decision returns `status: "blocked"`. It does
not install dependencies, run repository-wide checks, stage, commit, push, or alter branches or
remotes.
