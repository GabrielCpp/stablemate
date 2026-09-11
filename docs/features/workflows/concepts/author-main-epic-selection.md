---
type: concept
slug: author-main-epic-selection
title: Author main epic selection
---
# Author main epic selection

The Author main graph selects one epic from the worklist and returns its resolved directory, or a
reason explaining why no epic can be selected. Both selectors share the same algorithm. The
document selector considers an epic complete only when its epic document and at least one seed
exist; the story-authoring selector delegates completion to Ostler's `epic_authored` verdict, which
also requires every listed story document to contain its required prose. A selected bare slug is
resolved back to Ostler's numbered directory name before it is passed to later nodes.

- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_pick_epic`
- detail: [Epic selection and choice roles](epic-selection-and-choice-roles.md)
- detail: [Epic selection documentation roles](epic-selection-documentation-roles.md)
- detail: [Author main package](author-main-package.md)
- detail: [Author shared schemas](author-shared-schemas.md)
- detail: [Epic choice](../epic-choice.md)

## Methods

### _milestone_ordered_epics
- sig: `_milestone_ordered_epics(okf: Ostler) -> list[str]`
- does: returns milestone epic slugs in the order listed by the graph
- verify: count(subject="milestone-ordered epic slugs", equals=1)
- does: removes blank and duplicate milestone epic slugs while preserving first-seen order
- verify: removed(subject="blank and duplicate milestone epic slugs")
- verify: count(subject="unique milestone epic slugs", equals=1)
- returns: returns the graph epic names in graph order when no milestone supplies an epic
- verify: count(subject="graph-order epic fallback", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_milestone_ordered_epics`

### _roadmap_ordered_epics
- sig: `_roadmap_ordered_epics(okf: Ostler, roadmap: str) -> list[str]`
- does: selects the milestone whose source items contain the supplied roadmap path
- verify: count(subject="roadmap-owned milestones", equals=1)
- raises: raises `ValueError` when the roadmap sources zero or multiple milestones
- verify: absent(subject="roadmap epic selection after invalid ownership")
- returns: returns the non-blank epic slugs from the selected milestone in listed order
- verify: count(subject="roadmap milestone epic slugs", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_roadmap_ordered_epics`

### _epic_documented
- sig: `_epic_documented(okf: Ostler, epic: str) -> bool`
- does: finds the named epic through Ostler's graph lookup
- verify: count(subject="epic graph lookups", equals=1)
- returns: returns true only when the epic has an epic document and at least one seed
- verify: json_path(path="$.epic_documented", equals=true)
- returns: returns false when the epic is absent, lacks its epic document, or has no seeds
- verify: json_path(path="$.epic_documented", equals=false)
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_epic_documented`

### _pick_epic
- sig: `_pick_epic(logger: logging.Logger, repo_dir: str, *, roadmap: str, done: Callable[[Ostler, str], bool], finished_reason: str, selected_reason: str) -> EpicChoice`
- does: resolves the consuming repository from `repo_dir` and opens its Ostler graph
- verify: count(subject="epic-selection repository resolutions", equals=1)
- does: uses the roadmap-owned milestone when `roadmap` is supplied, otherwise uses the legacy todo queue and then milestone or graph order
- verify: count(subject="epic-selection queue sources", equals=1)
- does: marks each queued epic done according to the supplied completion predicate before selecting the first pending item
- verify: count(subject="epic worklist completion statuses", equals=1)
- does: resolves a selected bare slug to Ostler's numbered epic directory name
- verify: json_path(path="$.epic", matches="^\\d{4}-.+")
- raises: converts an Ostler or worklist read failure into an `EpicChoice` without a selected epic
- verify: absent(subject="epic choice after worklist read failure")
- returns: returns a reason-only choice when the queue is empty
- verify: json_path(path="$.has_epic", equals=false)
- returns: returns a reason-only choice with progress when every queued epic is complete
- verify: json_path(path="$.progress", matches=".+")
- returns: returns `EpicChoice` with `has_epic`, resolved epic, repo-relative epic directory, selection reason, and worklist progress
- verify: json_path(path="$.has_epic", equals=true)
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_pick_epic`

### select_epic_document
- sig: `select_epic_document(logger: logging.Logger, repo_dir: str = "", roadmap: str = "") -> EpicChoice`
- does: selects the first queued epic whose epic document or researched seed inputs are incomplete
- verify: json_path(path="$.reason", equals="epic needs epic.md completion or researched seeds")
- returns: returns an `EpicChoice` for the selected epic or the completed-worklist reason
- verify: count(subject="epic document selection choices", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::select_epic_document`
- code: `workflows/tests/author/test_workflow.py::test_roadmap_authoring_selects_only_its_milestone_epics`
- tests: `workflows/tests/author/test_workflow.py::test_roadmap_authoring_selects_only_its_milestone_epics`

### select_epic
- sig: `select_epic(logger: logging.Logger, repo_dir: str = "", roadmap: str = "") -> EpicChoice`
- does: selects the first queued epic that Ostler does not report as fully authored
- verify: json_path(path="$.reason", equals="epic missing stories, or a story is still unwritten")
- does: treats a completed queue as normal progress rather than a failure
- verify: json_path(path="$.has_epic", equals=false)
- returns: returns the selected epic's resolved directory and worklist progress, or the completion reason
- verify: count(subject="epic selection choices", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::select_epic`
- code: `workflows/tests/author/test_workflow.py::test_author_nodes_use_milestones_when_todo_is_absent`
- code: `workflows/tests/author/test_workflow.py::test_roadmap_authoring_selects_only_its_milestone_epics`
- tests: `workflows/tests/author/test_workflow.py::test_author_nodes_use_milestones_when_todo_is_absent`
- tests: `workflows/tests/author/test_workflow.py::test_roadmap_authoring_selects_only_its_milestone_epics`
