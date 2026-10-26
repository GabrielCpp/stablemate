---
type: concept
slug: author-main-story-processing
title: Author main story processing
---
# Author main story processing

The story-processing nodes the Author main flow reaches through its story subflows register a
story, gate visual design, validate the story contract and grounding, retain failed approaches,
consume operator feedback, and close a consumed register record as promoted. The record comes
from the [debt register](../../ostler/concepts/the-debt-register.md), and
[promoting a record](promote-a-record.md) describes the path as a whole.
These nodes use Ostler as the source of truth for planning and document structure; they do not
invent epic paths or duplicate the graph's story semantics.

- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::seed_story` @ec2020d13cf3
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/mockup.py::check_mockup_needed` @16f77856eb81
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::validate_story` @61ad4510b612
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::check_story_grounding` @61ad4510b612
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::record_attempt` @61ad4510b612
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/feedback.py::check_story_feedback` @8125ecb8d1d2
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::promote_record` @ec2020d13cf3
- detail: [Author main package](author-main-package.md)

## Methods

### seed_story
- sig: `seed_story(logger, epic: str = "", record: str = "", layers: str = "", services: str = "", repo_dir: str = "") -> SeededStory`
- does: resolves a record id or short handle to one register record of any status
- verify: json_path(path="$.record_id", matches="^[A-Za-z0-9][A-Za-z0-9._-]*$")
- does: raises a workflow failure naming the token when it matches no record, so literal text is rejected
- verify: count(subject="workflow failures for a token naming no record", equals=1)
- does: requires an existing epic and raises a workflow failure when the epic or record input is blank or the epic is missing
- verify: count(subject="workflow failures for missing story inputs", equals=1)
- does: reuses an existing story of the epic that already covers the record id without adding a duplicate
- verify: count(subject="stories covering the record after reuse", equals=1)
- does: raises a workflow failure when a story must be created and the record is not open
- verify: count(subject="workflow failures for a closed record", equals=1)
- does: adds a researched seed whose id is the record id, whose summary is the record summary followed by its body, and whose `sourceRecord` metadata holds the record id
- verify: created(subject="the researched seed for the record")
- verify: persists(subject="the researched seed metadata")
- does: creates one story covering the seed, named by the kebab form of the record summary
- verify: created(subject="the story covering the seeded record")
- does: returns the story's epic directory
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- does: returns the story's directory
- verify: json_path(path="$.story_dir", equals="docs/stories/acme-story")
- does: returns the story's path
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")
- does: returns the record id
- verify: json_path(path="$.record_id", equals="b1")
- does: returns the creation or reuse reason
- verify: json_path(path="$.reason", equals="The slice works without it.")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::seed_story` @ec2020d13cf3
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::find_record` @ec2020d13cf3
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::seed_text` @ec2020d13cf3
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_promotes_an_open_record_and_does_not_commit_the_code_repo`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_refuses_a_token_that_names_no_record`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_takes_no_literal_text`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_refuses_a_record_that_is_not_open`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_refuses_an_epic_that_does_not_exist`

### check_mockup_needed
- sig: `check_mockup_needed(logger, story_slug: str = "", repo_dir: str = "") -> MockupGate`
- does: fails the workflow when the story is absent
- does: requires a mockup when any of the story's `services` names a web or mobile book
- verify: json_path(path="$.required", equals=true)
- does: skips the mockup when no service of the story is a web or mobile book
- verify: json_path(path="$.required", equals=false)
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/mockup.py::check_mockup_needed` @cbcbbaf4e981
- tests: `workflows/tests/author/test_mockup_gate.py::test_the_gate_is_the_union_of_the_covered_seeds_services`
- tests: `workflows/tests/author/test_mockup_gate.py::test_a_story_the_graph_cannot_resolve_fails_the_run`
- tests: `workflows/tests/author/test_mockup_gate.py::test_an_api_only_story_needs_no_mockup_whatever_the_seed_says`

### validate_story
- sig: `validate_story(logger, story_dir: str = "", repo_dir: str = "") -> Defects`
- does: reports an error when no story directory is supplied
- verify: json_path(path="$.ok", equals=false)
- does: reports an error when the supplied story directory's `story.md` is missing
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
- does: returns one newline-separated error per finding
- verify: json_path(path="$.errors", matches=".+\\n.+")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::validate_story` @29a54157b737
- tests: `workflows/tests/author/test_story_contract.py::test_technical_notes_require_a_grounded_code_pointer`

### check_story_grounding
- sig: `check_story_grounding(logger, story_dir: str = "", epic_dir: str = "", services_dir: str = "", repo_dir: str = "") -> Defects`
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
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::check_story_grounding` @29a54157b737
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
- code: `workflows/src/workhorse_workflows/author/shared/nodes/stories.py::record_attempt` @61ad4510b612
- tests: `workflows/tests/author/test_workflow.py::test_a_story_that_is_not_a_contract_is_reworked_against_the_gate`

### check_story_feedback
- sig: `check_story_feedback(logger, run_dir: str = "") -> Feedback`
- does: polls the run-scoped inbox without blocking and returns no feedback when no message is outstanding
- verify: json_path(path="$.present", equals=false)
- does: consumes the oldest outstanding message by replying that it was folded into story rework
- verify: emitted(event="story feedback folded", count=1)
- does: returns the message content, scope, and `present` flag for one consumed operator note
- verify: count(subject="consumed operator feedback messages", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/feedback.py::check_story_feedback` @8125ecb8d1d2
- tests: `workflows/tests/author/test_workflow.py::test_an_operator_note_dropped_mid_run_reworks_the_story_once`

### promote_record
- sig: `promote_record(logger, record_id: str = "", epic: str = "", story: str = "", repo_dir: str = "") -> Promoted`
- does: raises a workflow failure when the record id is blank
- verify: count(subject="workflow failures for a blank record id", equals=1)
- does: names the story by the `story` input, or by the story of the epic whose `covers` lists the record when the input is blank
- verify: json_path(path="$.reason", equals="promoted to story users-can-sign-in in epic accounts")
- does: raises a workflow failure when no story of the epic covers the record
- verify: count(subject="workflow failures for an uncovered record", equals=1)
- does: closes the record as promoted with the reason `promoted to story <story> in epic <epic>`
- verify: persists(subject="the record's promoted status and reason")
- does: raises a workflow failure carrying Ostler's message when the close is refused
- verify: count(subject="workflow failures for a refused close", equals=1)
- does: leaves the code repository uncommitted, because the close is one commit in the artifacts repo
- verify: unchanged(subject="the code repository history")
- returns: `Promoted` with the record id and the reason
- verify: json_path(path="$.record_id", equals="b1")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::promote_record` @ec2020d13cf3
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_promotes_an_open_record_and_does_not_commit_the_code_repo`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_resumed_after_the_close_fails_nothing_and_commits_nothing_more`

