---
type: concept
slug: story-split-subflow
title: Author story-split subflow
---
# Author story-split subflow

The `story_split` package is the standalone Author subflow for decomposing one explicitly named
epic into stories and converging its seed coverage. It loads the configured repository paths,
delegates story splitting and semantic coverage review to high-power agent turns, applies at most
three coverage reworks and two automatic split-resolution turns, and parks unresolved decisions
at the epic context for operator input. A passing review is recorded as a digest-bound receipt
before the flow returns its accepted result. It does not author epic prose, select another epic,
or create a commit.

The [author workflow composition root](author-workflow-composition-root.md) registers this flow
alongside the other author stages. Configuration loading, coverage validation, path resolution,
operator resolution, and telemetry labeling are existing shared author capabilities; this package
only composes them for one story-split run.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow`
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/story_split/test_flow.py::test_accepts_one_epic_graph_without_selecting_authoring_or_git`
- detail: [story split completion](../story-split-done.md)
- detail: [story split review receipt](../story-split-receipt.md)
- detail: [story split agent result](../story-split-agent-result.md)
- detail: [story split coverage review](../coverage-review.md)
- detail: [story split coverage defects](../coverage-defects.md)

## Fields

### epic
- type: `str`
- default: `""` — no epic is selected until the caller supplies one
- required: true
- semantics: identifies the single epic whose story graph is split and reviewed
- verify: json_path(path="$.epic", matches=".+")
- verify: count(subject="story-split runs with one selected epic", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow`

### operator_mode
- type: literal `auto` or `human`
- default: `"auto"` — blocked decisions first receive automatic resolution attempts
- required: true
- semantics: `human` sends blocked or exhausted work directly to the operator context
- semantics: `auto` permits up to two automatic split-resolution turns before the operator context
- verify: json_path(path="$.operator_mode", equals="auto")
- verify: count(subject="human-mode story-split operator gates", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow`

## Methods

### blueprint
- sig: `Blueprint("author-story-split") -> Blueprint`
- does: provides the package-local registration target for deterministic story-split nodes
- returns: returns a blueprint named `author-story-split`
- verify: json_path(path="$.name", equals="author-story-split")
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/_blueprint.py::blueprint`

### setup
- sig: `setup() -> Config`
- does: loads author configuration in `story-split` mode
- returns: returns the configured repository, epic, document-root, and feature paths
- verify: count(subject="prepared story-split configurations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the selected epic as `work_id` and `epic`
- does: labels progress as `splitting stories`
- returns: returns labels identifying the one selected epic
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.labels`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds `cov_reworks` and `split_resolves` counters to the base run labels
- returns: returns labels containing both story-split budget counters
- verify: json_path(path="$.cov_reworks", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.state_labels`

### start
- sig: `start() -> Continue`
- does: rejects an empty epic parameter
- does: rejects an operator mode other than `auto` or `human`
- raises: raises `WorkflowFailed` with failure class `story-split-missing-epic` for an empty epic
- verify: count(subject="empty story-split epic failures", equals=1)
- raises: raises `WorkflowFailed` with failure class `story-split-invalid-operator-mode`
- verify: count(subject="invalid story-split operator-mode failures", equals=1)
- returns: returns a continuation targeting `split_stories` for a valid run
- verify: count(subject="story-split starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.start`

### split_stories
- sig: `split_stories(split_resolves: int = 0, cov_reworks: int = 0, rework_notes: str = "") -> Continue | Await`
- does: asks a high-power agent to split the selected epic's seeds into stories using the current rework notes
- verify: count(subject="story-split planning turns", equals=1)
- does: sends a non-blocked, non-standoff result to `check_coverage`
- verify: count(subject="story-split coverage checks", equals=1)
- does: sends a standoff result to the coverage gate with the standoff notes appended to prior rework notes
- verify: visible(locator="story-split coverage gate", text="declined this rework")
- does: returns an operator-awaiting context for blocked work in human mode or after two split resolutions
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: routes auto-mode blocked work to `resolve_split` while fewer than two split resolutions have occurred
- verify: count(subject="story-split resolution continuations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.split_stories`

### resolve_split
- sig: `resolve_split(notes: str, split_resolves: int = 0, cov_reworks: int = 0, rework_notes: str = "") -> Await`
- does: asks the shared operator resolver to diagnose a blocked story-split decision
- verify: count(subject="story-split operator resolutions", equals=1)
- does: returns an operator-awaiting context that resumes `split_stories` with the resolution counter incremented
- verify: visible(locator="operator-awaiting context", text="blocked")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.resolve_split`

### check_coverage
- sig: `check_coverage(cov_reworks: int = 0, split_resolves: int = 0) -> Continue | Await | Done`
- does: validates the selected epic's seed and story coverage without requiring authored story prose
- verify: json_path(path="$.ok", equals=True)
- does: asks an independent high-power agent to review coverage when mechanical validation passes
- verify: count(subject="story-split coverage review turns", equals=1)
- does: records a digest-bound receipt and returns `StorySplitDone` when semantic review status is `ok`
- verify: created(subject="story-split review receipt")
- does: routes a blocked semantic review through the coverage gate
- verify: visible(locator="story-split coverage gate", text="blocked")
- does: routes a non-blocked failed review to story rework
- verify: count(subject="story-split coverage reworks", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.check_coverage`

### resolve_coverage
- sig: `resolve_coverage(notes: str, split_resolves: int = 0) -> Await`
- does: asks the shared operator resolver to diagnose a coverage decision
- verify: count(subject="story-split coverage resolutions", equals=1)
- does: returns an operator-awaiting context that resumes `split_stories` with the resolution counter incremented
- verify: visible(locator="operator-awaiting context", text="blocked")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow.resolve_coverage`

### _rework_coverage
- sig: `_rework_coverage(result: object, notes: str, cov_reworks: int, split_resolves: int) -> Continue | Await`
- does: routes coverage findings back to `split_stories` with incremented rework notes while fewer than three reworks have occurred
- verify: count(subject="bounded story-split rework continuations", equals=1)
- does: sends exhausted coverage rework to the coverage gate
- verify: visible(locator="story-split coverage gate", text="coverage")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._rework_coverage`

### _gate_coverage
- sig: `_gate_coverage(result: object, notes: str, split_resolves: int) -> Continue | Await`
- does: returns an operator-awaiting context for human mode or after two split resolutions
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: routes automatic unresolved coverage to `resolve_coverage` while its resolution budget remains
- verify: count(subject="automatic story-split coverage resolutions", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._gate_coverage`

### _epic_dir
- sig: `_epic_dir() -> str`
- does: resolves the selected epic directory from the workflow repository root and epic name
- verify: json_path(path="$.epic_dir", matches=".+")
- returns: returns the repository-relative epic directory used by the split and coverage stages
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._epic_dir`

### _context
- sig: `_context() -> str`
- does: derives `context.md` beneath the selected epic directory
- verify: json_path(path="$.context_path", matches="context\\.md$")
- returns: returns the operator context path used by blocked split and coverage decisions
- verify: json_path(path="$.context_path", matches="context\\.md$")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._context`

### _abs
- sig: `_abs(relative: str) -> Path`
- does: joins a repository-relative path to the workflow repository root
- verify: json_path(path="$.absolute_path", matches=".+")
- returns: returns an absolute path for an operator-await context file
- verify: json_path(path="$.absolute_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._abs`

### _resolve
- sig: `_resolve(stage: str, notes: str) -> OperatorResolution`
- does: invokes the shared operator resolver with the epic context, stage, and block notes
- verify: count(subject="story-split operator resolver turns", equals=1)
- does: gives the resolver high power and no time limit
- verify: count(subject="unbounded story-split resolver turns", equals=1)
- returns: returns the resolver's operator decision
- verify: json_path(path="$.decision", matches=".+")
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow._resolve`

## Downstream Boundaries

The flow delegates configuration loading and epic-scoped coverage validation to shared Author
nodes. Those modules are separate source-layer contracts and are descended independently; path
resolution, telemetry labels, receipt persistence, and the agent result formats are already
documented by the linked shared concepts and formats.

- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`
- code: `workflows/src/workhorse_workflows/author/main/nodes/coverage.py::validate_coverage`
- detail: [author coverage validator](coverage-validator.md)

## Nodes

### record_story_split_review
- sig: `record_story_split_review(logger: logging.Logger, epic: str, repo_dir: str = "") -> StorySplitReceipt`
- does: resolves the repository root and locates the named epic in the Ostler graph
- verify: count(subject="story-split receipt epic resolutions", equals=1)
- does: rejects an absent epic
- raises: raises `WorkflowFailed` stating that no epic with the requested name exists
- verify: count(subject="missing story-split receipt epic failures", equals=1)
- does: rejects an epic without a persisted `epic.md`
- raises: raises `WorkflowFailed` stating that the epic has no `epic.md`
- verify: count(subject="epics without story-split receipt paths", equals=1)
- does: computes the current active-seed and story-topology digest
- verify: json_path(path="$.graph_digest", matches="^[0-9a-f]{64}$")
- does: writes `story-split-receipt.json` beside `epic.md` with status `passed` and the graph digest
- verify: created(subject="story-split-receipt.json")
- returns: returns the digest and repository-relative receipt path
- verify: json_path(path="$.path", matches="story-split-receipt\\.json$")
- code: `workflows/src/workhorse_workflows/author/story_split/nodes/review.py::record_story_split_review`
