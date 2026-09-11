---
type: concept
slug: author-main-story-processing
title: Author main story processing
---
# Author main story processing

The Author main story-processing module contains the deterministic nodes that register a story,
choose the next story in dependency order, gate visual design, validate the story contract and
grounding, retain failed approaches, consume operator feedback, and prune a consumed backlog item.
These nodes use Ostler as the source of truth for planning and document structure; they do not
invent epic paths or duplicate the graph's story semantics.

- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::seed_story`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::remove_story`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::check_mockup_needed`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::select_story`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::validate_story`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::check_story_grounding`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::record_attempt`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::check_story_feedback`
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::prune_bullet`
- detail: [Author main package](author-main-package.md)

## Methods

### seed_story
- sig: `seed_story(logger, epic: str = "", bullet: str = "", layers: str = "", services: str = "", repo_dir: str = "") -> SeededStory`
- does: resolves a backlog id, backlog text, or literal bullet into one story id
- verify: json_path(path="$.bullet_id", matches="^[A-Za-z0-9][A-Za-z0-9._-]*$")
- does: carries the resolved source bullet into the seed and story records
- verify: persists(subject="the resolved source bullet in the seed and story records")
- does: requires an existing epic and raises a workflow failure when the epic or bullet is missing
- verify: count(subject="workflow failures for missing story inputs", equals=1)
- does: reuses an existing story that already covers the resolved bullet id without adding a duplicate
- verify: count(subject="stories covering the resolved bullet after reuse", equals=1)
- does: adds a researched seed with source bullet metadata and optional layer/service metadata when the seed is new
- verify: created(subject="the researched seed for the resolved bullet")
- verify: persists(subject="the researched seed metadata")
- does: creates one story covering the seed
- verify: created(subject="the story covering the seeded bullet")
- does: returns the story's epic directory
- verify: json_path(path="$.epic_dir", matches=".+")
- does: returns the story's directory
- verify: json_path(path="$.story_dir", matches=".+")
- does: returns the story's path
- verify: json_path(path="$.story_path", matches=".+")
- does: returns the resolved bullet id
- verify: json_path(path="$.bullet_id", matches="^[A-Za-z0-9][A-Za-z0-9._-]*$")
- does: returns whether the resolved bullet came from the backlog
- verify: json_path(path="$.from_backlog", equals=true)
- does: returns the creation or reuse reason
- verify: json_path(path="$.reason", matches=".+")
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::seed_story`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_authors_one_bullet_and_does_not_commit`

### remove_story
- sig: `remove_story(logger, story: str = "", force: bool = False, repo_dir: str = "") -> StoryMutation`
- does: returns an unchanged idempotent result when the requested story is already absent
- verify: count(subject="story deletions for an absent story", equals=0)
- does: refuses to delete a story whose status is not `Not started` unless `force` is true
- verify: count(subject="unforced deletions of started stories", equals=0)
- does: deletes the requested story
- verify: removed(subject="the requested story")
- does: returns the requested story's epic
- verify: json_path(path="$.epic", matches=".+")
- does: returns the requested story's story directory
- verify: json_path(path="$.story_dir", matches=".+")
- does: returns the requested story's story path
- verify: json_path(path="$.story_path", matches=".+")
- does: returns a changed flag set to true
- verify: json_path(path="$.changed", equals=true)
- does: returns the deletion result message
- verify: json_path(path="$.reason", matches=".+")
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::remove_story`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_remove_refuses_a_started_story_without_force`

### check_mockup_needed
- sig: `check_mockup_needed(logger, story_slug: str = "", repo_dir: str = "") -> MockupGate`
- does: returns a required gate when the story is absent, has no covered seed evidence, or has an unclassified seed layer
- verify: json_path(path="$.required", equals=false)
- does: unions distinct `layers` and `services` from every covered seed in source order
- verify: json_path(path="$.layers", matches=".+")
- tests: `workflows/tests/author/test_mockup_gate.py::test_the_gate_is_the_union_of_the_covered_seeds_layers`
- does: requires visual design when any covered frontend seed has `design: required`
- verify: json_path(path="$.evidence", matches="required")
- does: skips visual design when all covered frontend seeds are `design: preserve` or when the story has no frontend layer
- verify: json_path(path="$.required", equals=false)
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::check_mockup_needed`
- tests: `workflows/tests/author/test_mockup_gate.py::test_one_required_visual_change_requires_design`

### select_story
- sig: `select_story(logger, epic_dir: str = "", repo_dir: str = "", parked: tuple[str, ...] = ()) -> StoryChoice`
- does: returns no story when `epic_dir` is blank or Ostler reports no epic or no stories
- verify: json_path(path="$.has_story", equals=false)
- does: asks Ostler for the first story needing authoring in dependency order and skips parked slugs
- verify: count(subject="selected unparked stories", equals=1)
- does: builds progress from Ostler's completed and remaining story counts
- verify: json_path(path="$.remaining_count", matches="^[0-9]+$")
- does: returns the selected story slug, path, directory, progress, remaining count, and report reason
- verify: count(subject="selected authoring stories", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::select_story`
- tests: `workflows/tests/author/test_planner.py::test_story_author_uses_story_dag_order_and_author_current`

### validate_story
- sig: `validate_story(logger, story_dir: str = "", repo_dir: str = "") -> Defects`
- does: reports an error when no story directory is supplied
- verify: json_path(path="$.ok", equals=false)
- does: reports an error when the supplied story directory's `story.md` is missing
- verify: json_path(path="$.ok", equals=false)
- does: requires the status bullet to be present
- verify: count(subject="missing required story status bullets", equals=0)
- does: requires every Ostler-declared story section to be present
- verify: count(subject="missing required story sections", equals=0)
- does: requires every Ostler-declared story section to contain content
- verify: count(subject="empty required story sections", equals=0)
- does: requires the Ostler-declared story sections to follow their declared order
- verify: count(subject="misordered required story sections", equals=0)
- does: requires Technical Notes to contain an existing repository-grounded `path::symbol` pointer or the exact greenfield statement
- verify: count(subject="grounded Technical Notes contracts", equals=1)
- does: rejects Technical Notes pointers outside the repository and rejects prose containing unresolved decision phrases or standalone TODO markers
- verify: count(subject="rejected ungrounded or unresolved story notes", equals=1)
- does: returns `ok` only when all deterministic checks pass
- verify: json_path(path="$.ok", equals=false)
- does: returns one newline-separated error per finding
- verify: json_path(path="$.errors", matches=".+\\n.+")
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::validate_story`
- tests: `workflows/tests/author/test_story_contract.py::test_technical_notes_require_a_grounded_code_pointer`

### check_story_grounding
- sig: `check_story_grounding(logger, story_dir: str = "", epic_dir: str = "", features_dir: str = "", repo_dir: str = "") -> Defects`
- does: reports an error when story or epic directory input is blank or the epic seed list cannot be read
- verify: json_path(path="$.ok", equals=false)
- does: derives the story and epic identifiers from the supplied directory basenames and reads the epic seed set through Ostler
- verify: count(subject="story grounding epic seed reads", equals=1)
- does: rejects every story coverage id that is absent from the epic's seed set
- verify: count(subject="phantom story seed references", equals=0)
- does: when the graph has UI nodes, requires the story to cite at least one resolvable UI surface node and rejects missing citations
- verify: count(subject="resolvable UI nodes cited by the story", equals=1)
- does: does not require UI citations while the Ostler graph has no UI nodes
- verify: absent(subject="UI citation requirement on an empty UI graph")
- does: returns `ok` with newline-separated findings only when seed scope and the armed UI citation contract hold
- verify: json_path(path="$.ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::check_story_grounding`
- tests: `workflows/tests/author/test_workflow.py::test_a_story_that_is_not_a_contract_is_reworked_against_the_gate`

### record_attempt
- sig: `record_attempt(logger, ledger_path: str = "", label: str = "", note: str = "", repo_dir: str = "") -> Ledger`
- does: returns an empty ledger when no ledger path is supplied
- verify: json_path(path="$.ledger", absent=true)
- does: creates an attempts ledger with a failed-approach heading and note when the ledger is absent
- verify: created(subject="the attempts ledger")
- does: appends one labeled failed approach and returns the complete ledger text
- verify: persists(subject="the labeled failed approach in the attempts ledger")
- does: treats an existing matching attempt heading as an idempotent no-op
- verify: count(subject="duplicate attempt headings", equals=1)
- does: preserves readable prior content when the ledger cannot be written
- verify: persists(subject="the labeled failed approach in the attempts ledger")
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::record_attempt`
- tests: `workflows/tests/author/test_workflow.py::test_a_story_that_is_not_a_contract_is_reworked_against_the_gate`

### check_story_feedback
- sig: `check_story_feedback(logger, run_dir: str = "") -> Feedback`
- does: polls the run-scoped inbox without blocking and returns no feedback when no message is outstanding
- verify: json_path(path="$.present", equals=false)
- does: consumes the oldest outstanding message by replying that it was folded into story rework
- verify: emitted(event="story feedback folded", count=1)
- does: returns the message content, scope, and `present` flag for one consumed operator note
- verify: count(subject="consumed operator feedback messages", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::check_story_feedback`
- tests: `workflows/tests/author/test_workflow.py::test_an_operator_note_dropped_mid_run_reworks_the_story_once`

### prune_bullet
- sig: `prune_bullet(logger, bullet_id: str = "", from_backlog: bool = False, repo_dir: str = "") -> Pruned`
- does: leaves the backlog unchanged when the bullet is literal, missing, absent from the file, or the backlog cannot be read
- verify: unchanged(subject="the backlog")
- does: removes only the matching parsed backlog scope item when it came from the backlog
- verify: removed(subject="the consumed backlog scope item")
- does: counts remaining items using the same bracketed-id predicate as removal and preserves nested children when the parent is not removable
- verify: count(subject="remaining identified backlog items", equals=2)
- does: returns removed and remaining counts and treats write failure as a best-effort continuation
- verify: removed(subject="the consumed backlog scope item")
- code: `workflows/src/workhorse_workflows/author/main/nodes/stories.py::prune_bullet`
- tests: `workflows/tests/author/test_workflow.py::test_story_prune_preserves_a_parent_with_nested_work`
