---
type: concept
slug: author-epic-author-subflow
title: Author epic-author subflow
---
# Author epic-author subflow

The `epic_author` package is the standalone Author subflow for authoring exactly one explicitly
named epic. It accepts the epic name and an optional `note`, loads author configuration, resolves the
requested epic without consulting a worklist, gives one high-power agent turn the epic prose and
researched-seed pass, and validates the resulting epic document before returning evidence. A
failed validation sends the errors back to the writer, up to three reworks. A blocked writer is
answered by the [PM](author-pm-gap-answer.md) up to twice, and the answer reaches it as a note.
Past either budget the subflow returns a `blocked` result. The subflow never creates a branch or
authors stories. The parent [Author workflow
composition root](author-workflow-composition-root.md) registers the flow and its package-local
node registry. The parent's `epics` drain dispatches this subflow with each pending epic and the row's note. On
return, the drain settles the epic's work item, and a blocked result keeps the row blocked for the
completion gate.

- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor` @dc8c1749d6e7
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/_blueprint.py::blueprint` @52b7dc7c36b1
- tests: `workflows/tests/author/epic_author/test_flow.py::test_authors_only_the_explicit_epic_and_returns_document_evidence`
- tests: `workflows/tests/author/epic_author/test_flow.py::test_a_blocked_writer_is_answered_by_the_pm_then_retries`
- detail: [author write-epic prompt](../formats/author-write-epic-prompt.md)
- detail: [author PM gap answer](author-pm-gap-answer.md)

## Methods

### blueprint
- sig: `Blueprint("author-epic-author") -> Blueprint`
- does: provides the registration target for the deterministic epic-author nodes
- returns: returns a blueprint named `author-epic-author`
- verify: json_path(path="$.name", equals="author-epic-author")
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/_blueprint.py::blueprint` @52b7dc7c36b1

### setup
- sig: `setup() -> EpicAuthorContext`
- does: loads author configuration in `epic` mode
- verify: count(subject="epic-mode author configurations loaded", equals=1)
- does: resolves the one caller-selected epic and merges its paths into the workflow context
- verify: count(subject="prepared explicit epic-author contexts", equals=1)
- returns: returns context containing the configured repository root
- verify: json_path(path="$.repo_root", equals="docs/stories")
- returns: returns context containing the configured milestone path
- verify: json_path(path="$.milestone_path", equals="docs/milestones/acme-launch/milestone.md")
- returns: returns context containing the configured epics directory
- verify: json_path(path="$.epics_dir", equals="docs/stories/acme-story")
- returns: returns context containing the configured feature-book directory
- verify: json_path(path="$.services_dir", equals="docs/stories/acme-story")
- returns: returns context containing the resolved epic
- verify: json_path(path="$.epic", equals="acme-epic")
- returns: returns context containing the resolved epic directory
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- returns: returns context containing the resolved epic document path
- verify: json_path(path="$.epic_path", equals="docs/stories/acme-story/epic.md")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.setup` @dc8c1749d6e7
- emits: [epic-author-context](../formats/epic-author-context.md)

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the selected epic as `work_id` and `epic`
- returns: returns progress text identifying authoring of one epic
- verify: json_path(path="$.epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.labels` @dc8c1749d6e7

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds integer state counters under the `epic_author` telemetry prefix
- returns: returns the base epic-author labels plus `epic_author.reworks` and `epic_author.answers` when the state supplies integer counts
- verify: count(subject="epic_author budget labels", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.state_labels` @dc8c1749d6e7

### _blocked
- sig: `_blocked(notes: str, reworks: int, answers: int) -> Done`
- does: returns an `EpicAuthorDone` with `status: blocked` that carries the notes and both counters
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor._blocked` @dc8c1749d6e7

### start
- sig: `start() -> Continue`
- does: begins authoring by forwarding to the `author_epic` state
- returns: returns a continuation targeting `author_epic`
- verify: count(subject="epic-author starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.start` @dc8c1749d6e7

### author_epic
- sig: `author_epic(reworks: int = 0, answers: int = 0, note: str = "") -> Continue | Done`
- does: asks the high-power agent to research and write the selected epic's narrative and durable seeds
- verify: count(subject="epic-author writing turns", equals=1)
- does: passes the selected epic, its canonical directory, the approved milestone path, the feature-book directory, the note and the PM ledger path to the writing turn
- verify: json_path(path="$.epic", equals="acme-epic")
- does: sends a blocked writing result to `ask_pm` while fewer than two answers were used
- verify: count(subject="epic-author PM questions", equals=1)
- does: returns a blocked result when the answer budget is spent
- verify: json_path(path="$.status", equals="blocked")
- does: validates the selected epic after a non-blocked writing result
- verify: count(subject="epic-author document validations", equals=1)
- does: sends failed document validation back to the writer with its errors while fewer than three reworks were used
- verify: count(subject="epic-author validation reworks", equals=1)
- does: returns `Done` only when validation reports `ok`
- verify: json_path(path="$.status", equals="authored")
- returns: returns the validated epic identity, document path, seed count, and both counters with status `authored`
- verify: count(subject="completed epic-author results", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic` @dc8c1749d6e7
- emits: [epic-author-done](../formats/epic-author-done.md)

### ask_pm
- sig: `ask_pm(question: str, reworks: int = 0, answers: int = 0) -> Continue`
- does: hands the writer's question to the PM gap answer
- verify: count(subject="epic-author PM answers", equals=1)
- does: resumes `author_epic` with the answer as the note and the answer counter incremented
- verify: json_path(path="$.answers", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.ask_pm` @dc8c1749d6e7

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
- emits: [epic-target](../formats/epic-target.md)
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/epic.py::prepare_epic_target` @4cff2229e3b9

### method: validate_authored_epic
- sig: `validate_authored_epic(logger: logging.Logger, epic: str, repo_dir: str = "") -> EpicEvidence`
- does: resolves the requested epic from the Ostler graph
- verify: count(subject="epic-author document validations", equals=1)
- does: reports an error and zero seeds when the requested epic is absent
- verify: json_path(path="$.ok", equals=False)
- does: reports an error when the epic has no `epic.md`
- verify: json_path(path="$.errors", matches="epic\\.md")
- does: reports an error when the epic has no researched seeds
- verify: json_path(path="$.errors", matches="no researched seeds")
- does: returns successful evidence only when the epic document exists and at least one seed is present
- verify: json_path(path="$.ok", equals=True)
- returns: returns the epic identity, canonical document path, seed count, and newline-separated validation errors
- verify: json_path(path="$.seed_count", matches="^[0-9]+$")
- emits: [epic-evidence](../formats/epic-evidence.md)
- code: `workflows/src/workhorse_workflows/author/epic_author/nodes/epic.py::validate_authored_epic` @4cff2229e3b9
