---
type: concept
slug: promote-a-record
title: Promoting a record into a story
---
# Promoting a record into a story

A maintainer turns one open record of the
[debt register](../../ostler/concepts/the-debt-register.md) into a story of an existing epic. The
record names the work, the story plans and builds it, and the record closes as `promoted` with the
story it became. Two paths do this. Author's story mode runs
`workhorse-author run --params '{"mode":"story","epic":"<slug>","record":"<id>"}'`. An epic edit
that adds a story from a record does it inside the [epic edit flow](../flows/author-epic-edit.md).

The `record` input is a record id or its short handle. Literal story text is refused, because the
story comes from a record that is already filed. A record not yet on the register is filed first
with `ostler backlog add`.

Story mode takes these steps in order:

1. `seed_story` finds the record and checks that the epic exists. It reuses a story of the epic
   whose `covers` already holds the record id. Otherwise it requires the record to be open, adds
   a seed to the epic from the record's summary and body with `sourceRecord` set to the record
   id, and creates a story slugged from the summary that covers the record.
2. The story author writes the story's sections.
3. `promote_record` closes the record as `promoted` with the reason
   `promoted to story <slug> in epic <epic>`. The register commits the close in the artifacts
   repository as `chore(<repo>): close <id> as promoted`.

Story mode commits nothing in the code repository. A resumed run after the close reuses the story
and closes nothing again, so it commits nothing more.

- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py` @ec2020d13cf3
- detail: [promoted record result](../formats/promoted.md)
- detail: [author main flow intake](author-main-intake.md)

## Methods

### seed_story

- sig: `seed_story(logger, epic: str = "", record: str = "", layers: str = "", services: str = "", repo_dir: str = "") -> SeededStory`
- does: refuses an empty epic, an empty record token, an epic with no `epic.md`, and a token that names no record on the register
- verify: count(subject="story mode refusals", equals=1)
- does: returns the story of the epic whose `covers` holds the record id, whatever the record's status, and creates nothing
- verify: count(subject="stories covering one record", equals=1)
- does: refuses a record that is not open when no story covers it yet
- verify: count(subject="closed records seeded", equals=0)
- does: adds a `researched` seed to the epic whose summary is the record's summary followed by its body
- verify: created(subject="a researched seed in the epic")
- does: sets `sourceRecord` and the optional `layers` and `services` in the seed's meta
- verify: count(subject="seeds with sourceRecord", equals=1)
- does: creates a story slugged from the record's summary, cut to sixty characters, that covers the record id
- verify: created(subject="a story covering the record id")
- returns: the epic directory, story slug, story directory, story path and record id
- verify: json_path(path="$.record_id", equals="b1")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::seed_story` @ec2020d13cf3
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_promotes_an_open_record_and_does_not_commit_the_code_repo`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_picks_a_record_by_its_short_handle`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_refuses_a_token_that_names_no_record`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_refuses_a_record_that_is_not_open`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_takes_no_literal_text`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_refuses_an_epic_that_does_not_exist`

### promote_record

- sig: `promote_record(logger, record_id: str = "", epic: str = "", story: str = "", repo_dir: str = "") -> Promoted`
- does: refuses an empty record id
- verify: count(subject="promotions with no record id", equals=0)
- does: takes the story slug it is given, or else finds the story of the epic whose `covers` holds the record id, and refuses when it finds none
- verify: count(subject="promotions with no story", equals=0)
- does: closes the record as `promoted` with the reason `promoted to story <slug> in epic <epic>`, and refuses when the register refuses the close
- verify: json_path(path="$.reason", equals="promoted to story export-the-account-data in epic accounts")
- returns: the record id and the close reason
- verify: json_path(path="$.record_id", equals="b1")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::promote_record` @ec2020d13cf3
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_resumed_after_the_close_fails_nothing_and_commits_nothing_more`
- tests: `workflows/tests/author/test_workflow.py::test_story_edit_add_authors_one_story_and_promotes_its_record`
- tests: `workflows/tests/author/test_workflow.py::test_epic_edit_add_story_from_a_record_closes_it_as_promoted`
