---
type: concept
slug: author-story-author-subflow
title: Author story-author subflow
---
# Author story-author subflow

The `story_author` package is the directly invokable Author subflow for one explicitly selected
story. It resolves and scaffolds that story, optionally designs a story-local mockup, delegates
story writing and independent audit turns, validates structure and feature-book grounding, and
handles feedback, bounded rework, and operator resolution. A passing run records a digest-bound
audit receipt. It does not select another story, create a branch, or commit changes.

The [author workflow composition root](author-workflow-composition-root.md) registers the flow and
its package-local blueprint. Its state-machine contract is the [author story-author flow](../flows/author-story-author.md).

- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor`
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/story_author/test_flow.py::test_flow_prepares_explicit_story_before_authoring_without_git_side_effects`

## Methods

### blueprint
- sig: `Blueprint("author-story-author") -> Blueprint`
- does: provides the registration target for deterministic story-author nodes
- returns: returns a blueprint named `author-story-author`
- verify: json_path(path="$.name", equals="author-story-author")
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/_blueprint.py::blueprint`

### setup
- sig: `setup() -> Config`
- does: loads author configuration in `story-author` mode
- returns: returns the resolved author configuration to the flow context
- verify: count(subject="story-author configuration loads", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the selected story and epic
- returns: returns progress text `authoring one story`
- verify: json_path(path="$.progress", equals="authoring one story")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.labels`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds the `reworks`, `resolves`, and `audit_reworks` counters to run labels
- returns: returns the base story labels combined with counter labels
- verify: json_path(path="$.reworks", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.state_labels`

### start
- sig: `start() -> Continue`
- does: resolves and prepares the explicitly selected epic/story target
- does: routes to mockup design when the story requires a mockup
- does: routes directly to story writing when no mockup is required
- verify: count(subject="story-author starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.start`

### design_mockup
- sig: `design_mockup(target: StoryTarget) -> Continue`
- does: asks the high-power design agent for a story-local mockup
- returns: carries the mockup reference into story writing
- verify: count(subject="story-author mockup turns", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.design_mockup`

### write_story
- sig: `write_story(target: StoryTarget, mockup: str = "", reworks: int = 0, resolves: int = 0, audit_reworks: int = 0, audit_findings: str = "") -> Continue | Await | Done`
- does: asks the high-power writing agent to author the selected story
- does: routes a blocked writing result through the story operator gate
- does: sends a non-blocked writing result to story checks
- verify: count(subject="story-author writing turns", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.write_story`

### check_story
- sig: `check_story(target: StoryTarget, mockup: str = "", reworks: int = 0, resolves: int = 0, audit_reworks: int = 0, audit_findings: str = "") -> Continue | Await | Done`
- does: validates the story document structure
- verify: count(subject="story-author structure validations", equals=1)
- does: validates story grounding against the parent epic and feature book
- verify: count(subject="story-author grounding validations", equals=1)
- does: sends a valid, grounded story to independent audit
- verify: count(subject="story-author audit handoffs", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.check_story`

### audit_story
- sig: `audit_story(target: StoryTarget, mockup: str = "", reworks: int = 0, resolves: int = 0, audit_reworks: int = 0, audit_findings: str = "") -> Continue | Await | Done`
- does: asks an independent agent to audit the selected story
- verify: count(subject="story-author audit turns", equals=1)
- does: routes complete audits with no findings to feedback polling
- verify: count(subject="story-author passing audit continuations", equals=1)
- does: routes findings to one audit rework before gating
- verify: count(subject="story-author audit reworks", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.audit_story`

### rework_story
- sig: `rework_story(target: StoryTarget, notes: str, mockup: str = "", reworks: int = 0, resolves: int = 0, audit_reworks: int = 0, audit_findings: str = "") -> Continue`
- does: records the failed attempt in the story's attempts ledger
- verify: persists(subject="the story attempts ledger")
- does: asks the rework agent to revise the story using validation or audit notes
- verify: count(subject="story-author rework turns", equals=1)
- does: resumes story checks with an incremented rework counter
- verify: count(subject="story-author rework continuations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.rework_story`

### resolve_story
- sig: `resolve_story(target: StoryTarget, notes: str, mockup: str = "", resolves: int = 0) -> Await`
- does: asks the shared operator resolver to diagnose a blocked story write or validation
- verify: count(subject="story-author operator resolutions", equals=1)
- does: returns an operator-awaiting context that resumes story writing with an incremented resolution count
- verify: visible(locator="operator-awaiting context", text="blocked")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.resolve_story`

### story_feedback
- sig: `story_feedback(target: StoryTarget, mockup: str = "", reworks: int = 0, resolves: int = 0) -> Continue | Done`
- does: applies an available feedback message through the rework agent
- verify: count(subject="story-author feedback reworks", equals=1)
- does: records the passing story audit when no feedback is present
- verify: created(subject="audit-receipt.json")
- does: returns the authored story result after recording the passing audit
- verify: json_path(path="$.status", equals="authored")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.story_feedback`

### apply_feedback
- sig: `apply_feedback(target: StoryTarget, notes: str, mockup: str = "", reworks: int = 0, resolves: int = 0) -> Continue`
- does: asks the rework agent to apply operator feedback to the selected story
- verify: count(subject="story-author feedback application turns", equals=1)
- does: resumes structural and grounding checks without changing the resolution count
- verify: count(subject="story-author feedback check continuations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.apply_feedback`

## Nodes

### prepare_story
- sig: `prepare_story(logger: logging.Logger, epic: str = "", story: str = "", repo_dir: str = "") -> StoryTarget`
- does: rejects blank epic or story inputs
- raises: raises `WorkflowFailed` stating that explicit non-empty `epic` and `story` inputs are required
- verify: count(subject="blank story-author target failures", equals=1)
- does: resolves the named story only within the requested epic through Ostler
- raises: raises `WorkflowFailed` naming the missing story and epic
- verify: count(subject="cross-epic story-author target failures", equals=1)
- does: completes missing story sections through Ostler's idempotent scaffold operation
- verify: count(subject="story-author missing-section scaffolds", equals=1)
- returns: returns normalized epic, story, epic directory, story directory, and story document paths
- verify: json_path(path="$.story_path", matches="/story\\.md$")
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/story.py::prepare_story`

### record_story_audit
- sig: `record_story_audit(logger: logging.Logger, story_path: str, repo_dir: str = "") -> AuditReceipt`
- does: hashes the exact current story document bytes with SHA-256
- verify: json_path(path="$.story_digest", matches="^[0-9a-f]{64}$")
- does: writes a passing `audit-receipt.json` beside the story document containing the digest
- verify: created(subject="audit-receipt.json")
- returns: returns the digest and repository-relative receipt path
- verify: json_path(path="$.path", matches="audit-receipt\\.json$")
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/story.py::record_story_audit`
