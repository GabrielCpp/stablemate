---
type: concept
slug: author-epic-author-subflow
title: Author epic-author subflow
---
# Author epic-author subflow

The `epic_author` package is the standalone Author subflow for authoring exactly one explicitly
named epic. It accepts the epic name and `operator_mode`, loads author configuration, resolves the
requested epic without consulting a worklist, gives one high-power agent turn the epic prose and
researched-seed pass, and validates the resulting epic document before returning evidence. A
blocked turn or failed validation is routed through the operator resolver and then resumes the
same epic; the subflow never creates a branch or authors stories. The parent [Author workflow
composition root](author-workflow-composition-root.md) registers the flow and its package-local
node registry. The roadmap planner dispatches this subflow with the selected epic and the parent's
operator mode; on return, the parent resumes planning from the artifacts currently on disk.

- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor`
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/epic_author/test_flow.py::test_authors_only_the_explicit_epic_and_returns_document_evidence`
- detail: [author write-epic prompt](../author-write-epic-prompt.md)
- detail: [author resolve-operator prompt](../author-resolve-operator-prompt.md)

## Methods

### blueprint
- sig: `Blueprint("author-epic-author") -> Blueprint`
- does: provides the registration target for the deterministic epic-author nodes
- returns: returns a blueprint named `author-epic-author`
- verify: json_path(path="$.name", equals="author-epic-author")
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/_blueprint.py::blueprint`

### setup
- sig: `setup() -> EpicAuthorContext`
- does: loads author configuration in `epic` mode
- does: resolves the one caller-selected epic and merges its paths into the workflow context
- returns: returns context containing the configured repository root
- verify: json_path(path="$.repo_root", matches=".+")
- returns: returns context containing the configured backlog path
- verify: json_path(path="$.backlog_path", matches=".+")
- returns: returns context containing the configured roadmap path
- verify: json_path(path="$.roadmap_path", matches=".+")
- returns: returns context containing the configured epics directory
- verify: json_path(path="$.epics_dir", matches=".+")
- returns: returns context containing the configured feature-book directory
- verify: json_path(path="$.features_dir", matches=".+")
- returns: returns context containing the resolved epic
- verify: json_path(path="$.epic", matches=".+")
- returns: returns context containing the resolved epic directory
- verify: json_path(path="$.epic_dir", matches=".+")
- returns: returns context containing the resolved epic document path
- verify: json_path(path="$.epic_path", matches=".+")
- verify: count(subject="prepared explicit epic-author contexts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.setup`
- emits: [epic-author-context](../epic-author-context.md)

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the selected epic as `work_id` and `epic`
- returns: returns progress text identifying authoring of one epic
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.labels`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds integer state counters under the `epic_author` telemetry prefix
- returns: returns the base epic-author labels plus `epic_author.resolves` when the state supplies an integer resolution count
- verify: count(subject="epic_author resolution labels", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.state_labels`

### start
- sig: `start() -> Continue`
- does: begins authoring by forwarding to the `author_epic` state
- returns: returns a continuation targeting `author_epic`
- verify: count(subject="epic-author starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.start`

### author_epic
- sig: `author_epic(resolves: int = 0) -> Continue | Await | Done`
- does: asks the high-power agent to research and write the selected epic's narrative and durable seeds
- verify: count(subject="epic-author writing turns", equals=1)
- does: passes the selected epic, its canonical directory, the approved roadmap path, and the feature-book directory to the writing turn
- verify: json_path(path="$.epic", matches=".+")
- does: routes a blocked writing result through the gate with the result notes and current resolution count
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: validates the selected epic after a non-blocked writing result
- verify: count(subject="epic-author document validations", equals=1)
- does: sends a blocked agent result to the gate with its notes
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: sends failed document validation to the gate with its validation errors
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: sends blocked work to the operator gate when `operator_mode` is `human`
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: sends blocked work to the operator gate when two automatic resolutions have already been attempted
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: sends unresolved work to the automatic resolver when automatic resolution remains available
- verify: count(subject="epic-author resolution turns", equals=1)
- does: returns `Done` only when validation reports `ok`
- verify: json_path(path="$.status", equals="authored")
- returns: returns the validated epic identity, document path, seed count, and resolution count with status `authored`
- verify: count(subject="completed epic-author results", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`
- emits: [epic-author-done](../epic-author-done.md)

### _context_path
- sig: `_context_path() -> Path`
- does: resolves the operator context file beneath the repository root and the epic-author context filename
- verify: json_path(path="$.context_path", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor._context_path`

### _gate
- sig: `_gate(result: object, notes: str, resolves: int) -> Continue | Await`
- does: returns `Await` with the epic context path and `author_epic` as the resume state in human mode
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: returns `Await` with the epic context path and `author_epic` as the resume state after two automatic resolutions
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: otherwise schedules `resolve_epic` with the blocked result notes and current resolution count
- verify: count(subject="epic-author resolution continuations", equals=1)

### resolve_epic
- sig: `resolve_epic(notes: str, resolves: int = 0) -> Await`
- does: asks the shared operator resolver to diagnose the blocked write or validation result
- verify: count(subject="epic-author resolution turns", equals=1)
- does: passes the epic context path, epic directory, write stage, and block notes to the resolver
- verify: json_path(path="$.block_stage", equals="write-epic")
- does: returns an operator-awaiting transition using the epic context path and `author_epic` resume state
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: increments the resolution count before the resumed authoring state
- verify: count(subject="incremented epic-author resolutions", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.resolve_epic`

## Nodes

### prepare_epic_target
- sig: `prepare_epic_target(logger: logging.Logger, epic: str, repo_dir: str = "") -> EpicTarget`
- does: resolves the repository root from `repo_dir`
- verify: count(subject="epic-author repository resolutions", equals=1)
- consistency: epic-name — rejects a blank epic name by raising `WorkflowFailed` with `an explicit epic is required`
- verify: count(subject="blank epic target failures", equals=1)
- verify: json_path(path="$.exception.message", equals="an explicit epic is required")
- does: rejects a name that is absent from the Ostler epic graph
- raises: raises `WorkflowFailed` naming the missing epic
- verify: count(subject="missing epic target failures", equals=1)
- does: resolves the canonical epic directory and `epic.md` path for the found epic
- verify: json_path(path="$.epic_path", matches="/epic\\.md$")
- returns: returns the normalized explicit epic identity and its canonical paths
- verify: json_path(path="$.epic", matches=".+")
- emits: [epic-target](../epic-target.md)
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/epic.py::prepare_epic_target`

### method: validate_authored_epic
- sig: `validate_authored_epic(logger: logging.Logger, epic: str, repo_dir: str = "") -> EpicEvidence`
- does: resolves the requested epic from the Ostler graph
- verify: count(subject="epic-author document validations", equals=1)
- does: reports an error and zero seeds when the requested epic is absent
- verify: json_path(path="$.ok", equals=False)
- does: reports an error when the epic has no `epic.md`
- verify: json_path(path="$.ok", equals=False)
- does: reports an error when the epic has no researched seeds
- verify: json_path(path="$.errors", matches="no researched seeds")
- does: returns successful evidence only when the epic document exists and at least one seed is present
- verify: json_path(path="$.ok", equals=True)
- returns: returns the epic identity, canonical document path, seed count, and newline-separated validation errors
- verify: json_path(path="$.seed_count", matches=".+")
- emits: [epic-evidence](../epic-evidence.md)
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/epic.py::validate_authored_epic`
