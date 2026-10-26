---
type: concept
slug: story-split-subflow
title: Author story-split subflow
---
# Author story-split subflow

The `story_split` package is the standalone Author subflow for decomposing one explicitly named
epic into stories. It loads the configured repository paths, asks a high-power agent to split the
epic's seeds into stories, bounds each story's services, lints the coverage, and hands the result
to the [PM review](author-pm-review.md). A review that finds gaps sends the findings back to the
splitter, up to three reworks. A splitter that blocks on a product decision is answered by the
[PM](author-pm-gap-answer.md) up to twice, and the answer reaches it as a note. Past either budget
the flow returns a blocked result, and the Author flow keeps the epic's row blocked for the
completion gate. A passing review writes a [PM receipt](../formats/pm-receipt.md) in the epic
directory. The flow does not author epic prose, select another epic, or create a commit.

A story's services are bounded by the union of the services of the seeds it covers. A seed that
names a web app, a mobile app and their API is often split into one story per platform, and each
of those stories changes only its own platform's books. The splitter or a rework narrows such a
story's `services:` list, and the derivation keeps a non-empty list that stays inside the union.
An empty list, or one naming a book no covered seed names, is replaced by the union. A book a story
needs that no seed lists is a defect of the seed, so the derivation never widens past the union.

The [author workflow composition root](author-workflow-composition-root.md) registers this flow
alongside the other author stages.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow` @9e26ab4671cb
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/_blueprint.py::blueprint` @c780d75bd248
- rule: a story's `services:` stays a subset of its covered seeds' union; a narrower non-empty list is kept, anything else becomes the union
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`
- tests: `workflows/tests/author/story_split/test_flow.py::test_a_blocked_writer_is_answered_by_the_pm_then_retries`
- tests: `workflows/tests/author/story_split/test_flow.py::test_the_split_blocks_when_the_pm_never_passes`
- detail: [story-split prompt](../formats/story-split-prompt.md)
- detail: [story-split flow concept selection](story-split-flow-concept-selection.md)
- detail: [story-split flow inputs](story-split-flow-inputs.md)
- detail: [story split completion](../formats/story-split-done.md)
- detail: [story split agent result](../formats/story-split-agent-result.md)
- detail: [story split coverage defects](../formats/coverage-defects.md)
- detail: [author PM review](author-pm-review.md)
- detail: [author PM gap answer](author-pm-gap-answer.md)

## Fields

### epic
- type: `str`
- default: `""` — no epic is selected until the caller supplies one
- verify: json_path(path="$.epic", equals="")
- required: true
- semantics: identifies the single epic whose story graph is split and reviewed
- verify: count(subject="story-split runs with one selected epic", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow` @9e26ab4671cb
- detail: [story-split input fields](../concepts/story-split-input-fields.md)

### note
- type: `str`
- default: `""` — no extra context
- verify: json_path(path="$.note", equals="")
- required: false
- semantics: context from a previous attempt, such as the operator's answer, that the splitter reads first
- verify: count(subject="story-split planning turns that receive the note", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow` @9e26ab4671cb
- detail: [story-split input fields](../concepts/story-split-input-fields.md)

## Methods

### blueprint
- sig: `Blueprint("author-story-split") -> Blueprint`
- does: provides the package-local registration target for deterministic story-split nodes
- returns: returns a blueprint named `author-story-split`
- verify: json_path(path="$.name", equals="author-story-split")
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/_blueprint.py::blueprint` @c780d75bd248

### setup
- sig: `setup() -> Config`
- does: loads author configuration in `story-split` mode
- returns: returns the configured repository, epic, document-root, and feature paths
- verify: count(subject="prepared story-split configurations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.setup` @9e26ab4671cb

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the selected epic as `work_id` and `epic`
- does: labels progress as `splitting stories`
- returns: returns labels identifying the one selected epic
- verify: json_path(path="$.epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.labels` @9e26ab4671cb

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds the `story_split.reworks` and `story_split.answers` counters to the base run labels
- returns: returns labels containing both story-split budget counters
- verify: json_path(path="$.story_split.reworks", equals="example reworks")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.state_labels` @9e26ab4671cb

### start
- sig: `start() -> Continue`
- does: rejects an empty epic parameter
- raises: raises `WorkflowFailed` with failure class `story-split-missing-epic` for an empty epic
- verify: count(subject="empty story-split epic failures", equals=1)
- returns: returns a continuation targeting `split_stories` for a valid run
- verify: count(subject="story-split starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.start` @9e26ab4671cb

### split_stories
- sig: `split_stories(reworks: int = 0, answers: int = 0, rework_notes: str = "", note: str = "", prior: str = "") -> Continue | Done`
- does: asks a high-power agent to split the selected epic's seeds into stories using the current rework notes, the PM ledger and the note
- verify: count(subject="story-split planning turns", equals=1)
- does: sends a complete result to `check_coverage`
- verify: count(subject="story-split coverage checks", equals=1)
- does: sends a blocked or standoff result to `ask_pm` while fewer than two answers were used
- verify: count(subject="story-split PM questions", equals=1)
- does: returns a blocked result once the answer budget is spent
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.split_stories` @9e26ab4671cb

### check_coverage
- sig: `check_coverage(reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: keeps each story's non-empty services that stay inside its covered seeds' union, and writes the union otherwise
- verify: count(subject="story-split service derivations", equals=1)
- does: validates the selected epic's seed and story coverage without requiring authored story prose
- verify: json_path(path="$.ok", equals=True)
- does: sends mechanical errors back to the splitter as rework notes
- verify: count(subject="story-split mechanical reworks", equals=1)
- does: sends a clean lint to `review`
- verify: count(subject="story-split PM reviews", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.check_coverage` @9e26ab4671cb
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/services.py::derive_story_services` @bfeae9e6d0dc
- tests: `workflows/tests/author/story_split/test_services.py::test_a_story_keeps_a_narrower_list_inside_its_seeds_union`
- tests: `workflows/tests/author/story_split/test_services.py::test_a_story_naming_a_book_outside_its_seeds_takes_the_union`

### review
- sig: `review(reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: hands the epic directory to the PM review at the `story-split` stage with the previous findings
- verify: count(subject="story-split PM review handoffs", equals=1)
- does: returns an accepted result when every angle passed
- verify: json_path(path="$.status", equals="accepted")
- does: sends findings back to the splitter as rework notes otherwise
- verify: count(subject="story-split PM reworks", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.review` @9e26ab4671cb

### ask_pm
- sig: `ask_pm(question: str, reworks: int = 0, answers: int = 0, rework_notes: str = "", prior: str = "") -> Continue`
- does: hands the splitter's question to the PM gap answer
- verify: count(subject="story-split PM answers", equals=1)
- does: resumes `split_stories` with the answer as the note and the answer counter incremented
- verify: json_path(path="$.answers", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.ask_pm` @9e26ab4671cb

### _rework
- sig: `_rework(result: object, notes: str, reworks: int, answers: int, prior: str) -> Continue | Done`
- does: routes findings back to `split_stories` with incremented rework count while fewer than three reworks have occurred
- verify: count(subject="bounded story-split rework continuations", equals=1)
- does: returns a blocked result when the rework budget is spent
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._rework` @9e26ab4671cb

### _blocked
- sig: `_blocked(notes: str, reworks: int, answers: int) -> Done`
- does: returns a blocked `StorySplitDone` that carries the notes and both counters
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._blocked` @9e26ab4671cb

### _epic_dir
- sig: `_epic_dir() -> str`
- does: resolves the selected epic directory from the workflow repository root and epic name
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- returns: returns the repository-relative epic directory used by the split and review stages
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._epic_dir` @9e26ab4671cb

## Downstream Boundaries

The flow delegates configuration loading and epic-scoped coverage validation to shared Author
nodes, and the review and the answer to the PM package. Those modules are separate source-layer
contracts and are documented independently.

- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::load_config` @1e565a154642
- code: `workflows/src/workhorse_workflows/author/shared/nodes/coverage.py::validate_coverage` @2c46e3beb9ac
- detail: [author coverage validator](coverage-validator.md)
- detail: [author load_config documentation roles](author-load-config-documentation-roles.md)
