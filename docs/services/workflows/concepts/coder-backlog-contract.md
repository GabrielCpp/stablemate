---
type: concept
slug: coder-backlog-contract
title: Coder backlog contract
---
# Coder backlog contract

The coder files the work it leaves undone onto the
[debt register](../../ostler/concepts/the-debt-register.md) and drains part of it back out. Three
filers write records. QA's leftovers become `qa` records, the book pages QA could not check become
`qa-deferred` records, and a dev turn's follow-ups become `coder` records. Each filer places a
record under the workspace repository it names, skips a record the register already holds, and
commits what it filed as one artifacts commit with hooks off. No filer writes to a code repository.

The fix drain reads only the open `qa` records of the run's workspace repositories. It draws the
oldest one, seeds it as a one-criterion story in the `fixes` epic, and closes the record as `done`
once a commit of the fix lands. `coder` and `qa-deferred` records stay on the shelf for a person or
the review-debt workflow: no coder lane drains them.

- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::filed_backlog` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::unfiled` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_backlog_items` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_follow_up_backlog` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_deferred_obligations` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::select_fix_item` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::seed_fix_story` @a57d509225b0
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::close_fix_item` @a57d509225b0
- rule: a dev turn's follow-up `area` is checked against the register's one-kebab-segment rule when the turn returns its result, so a file path costs the agent one correction prompt and never a dropped record
- tests: `workflows/tests/coder/shared/test_qa_leftovers_backlog.py::test_each_item_becomes_a_qa_record_in_one_artifacts_commit`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_the_filed_follow_ups_are_committed_to_the_artifacts_repo_and_leave_the_code_repo_clean`
- tests: `workflows/tests/coder/shared/test_deferred_obligations_backlog.py::test_each_page_with_deferred_checks_becomes_one_record_in_one_artifacts_commit`
- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_committed_and_closed`
- detail: [The debt register](../../ostler/concepts/the-debt-register.md)
- detail: [Coder standalone fix flow](../flows/coder-fix.md)

## Placing a record

Every filer resolves the run's workspace to its repositories by name. A filing that names one of
them goes there. A filing that names none goes to the only repository when the workspace has one.
In a workspace of two or more, a filing that names none is skipped, and the log line lists the
repository names the workspace knows. A filing the register refuses, such as one with an invalid
summary, is logged with ostler's reason and counted as skipped.

The artifacts commit takes the repository as its scope when every filed record belongs to one
repository, and no scope otherwise. A batch that filed nothing commits nothing.

## Methods

### filed_backlog

- sig: `filed_backlog(logger, spec_dir: str = "", repo_dir: str = "", workspace: str = "") -> FiledBacklog`
- does: returns the open `qa` records of the workspace repositories as `filed`, each id mapped to its summary
- verify: count(subject="open qa records listed for judging", equals=1)
- does: returns the items QA left in `<spec_dir>/backlog-items.json` as `items`, each kebab id mapped to its one-line description, less the items with no id or no description
- verify: count(subject="pending qa items listed for judging", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::filed_backlog` @a57d509225b0
- tests: `workflows/tests/coder/shared/test_qa_leftovers_backlog.py::test_filed_lists_the_open_qa_records_of_the_workspace_repos_and_the_pending_items`

### unfiled

- sig: `unfiled(judge, logger, reports: Mapping[str, str], filed: Mapping[str, str]) -> list[str]`
- does: asks a low-power judge which pending item restates the cause of an open `qa` record, and logs each match under the record it matched
- verify: count(subject="pending items matched to an open record", equals=1)
- returns: the ids of the items that restate no open record
- verify: count(subject="pending items left to file", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::unfiled` @a57d509225b0

### file_backlog_items

- sig: `file_backlog_items(logger, spec_dir: str = "", repo_dir: str = "", workspace: str = "", drop: list[str] | None = None) -> BacklogDrain`
- does: files each item in `<spec_dir>/backlog-items.json` as a `qa` record whose area and pattern are the item's own, turned into lowercase kebab segments, or `untriaged` when the item gives none
- verify: count(subject="qa leftovers filed as records", equals=1)
- does: takes the summary from the first non-empty line of the item's description and keeps a multi-line description whole as the body
- verify: count(subject="qa record summaries", equals=1)
- does: sets `source_story` to the story id the spec dir's QA context names
- verify: count(subject="qa records naming their story", equals=1)
- does: skips an item with no id or no description, an item whose id is in `drop`, and an item whose normalized description matches an open `qa` record of the same repository
- verify: count(subject="skipped qa leftovers", equals=1)
- does: commits the filed records as `chore(<repo>): file the qa leftovers of <story>`
- verify: count(subject="qa leftover commits", equals=1)
- does: removes the items file afterwards, whether or not anything was filed
- verify: removed(subject="backlog-items.json")
- returns: `BacklogDrain` with the filed and skipped counts and a note `filed N to the register, skipped K (duplicate/invalid)`, followed by whether the items file was removed
- verify: json_path(path="$.notes", matches="^filed [0-9]+ to the register, skipped [0-9]+ \\(duplicate/invalid\\); (removed backlog-items\\.json|backlog-items\\.json left in place)$")
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_backlog_items` @a57d509225b0
- tests: `workflows/tests/coder/shared/test_qa_leftovers_backlog.py::test_a_dropped_item_is_not_filed`
- tests: `workflows/tests/coder/shared/test_qa_leftovers_backlog.py::test_an_item_that_restates_an_open_qa_record_is_skipped`
- tests: `workflows/tests/coder/shared/test_qa_leftovers_backlog.py::test_a_two_repo_workspace_places_each_item_by_its_repo`
- tests: `workflows/tests/coder/shared/test_qa_leftovers_backlog.py::test_nothing_filed_commits_nothing_and_still_clears_the_items`

### file_follow_up_backlog

- sig: `file_follow_up_backlog(logger, parent: str = "", follow_ups: list[FollowUp] | None = None, repo_dir: str = "", workspace: str = "") -> BacklogDrain`
- does: files each follow-up as a `coder` record whose summary is the follow-up's title
- verify: count(subject="follow-ups filed as coder records", equals=1)
- does: writes the follow-up's reason as the record body
- verify: count(subject="coder records whose body is the reason", equals=1)
- does: copies the follow-up's area, pattern and symbols onto the record
- verify: count(subject="coder records with the follow-up's area", equals=1)
- does: sets the record's `source_story` to `parent`
- verify: count(subject="coder records citing the parent story", equals=1)
- does: skips a follow-up with no title, a follow-up that names no workspace repository while the workspace has more than one, and a follow-up with no area or no pattern, logging which one it lacks
- verify: count(subject="refused follow-ups", equals=1)
- does: skips a follow-up an open record of the same repository already holds: its title or reason cites the record id in brackets, its title's id words differ from the record id's by at most one word when both have three or more, or its title matches the record summary's text before the first `: `
- verify: count(subject="follow-ups already on the register", equals=1)
- does: counts a record filed earlier in the same batch as open, so a repeated follow-up is filed once
- verify: count(subject="repeated follow-ups in one batch", equals=1)
- does: commits the filed records as `chore(<repo>): file the deferred follow-ups of <parent>`
- verify: count(subject="follow-up commits", equals=1)
- returns: `BacklogDrain` with the filed and skipped counts
- verify: json_path(path="$.appended", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_follow_up_backlog` @a57d509225b0
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_a_record_carries_what_the_proposal_said_and_an_id_ostler_minted`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_a_follow_up_without_an_area_or_a_pattern_is_refused_with_a_reason`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_a_follow_up_that_cites_an_open_record_is_not_filed_again`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_a_batch_files_a_repeated_follow_up_once_and_a_distinct_one_still`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_a_bookkeeping_commit_is_not_refused_by_the_repository_hooks`

### file_deferred_obligations

- sig: `file_deferred_obligations(logger, spec_dir: str = "", repo_dir: str = "", workspace: str = "") -> BacklogDrain`
- does: reads the required obligations ostler marked deferred in the spec dir's QA context and groups them by the book page that owes their check
- verify: count(subject="book pages with deferred checks", equals=1)
- does: files one `qa-deferred` record per page in area `book` with pattern `add-runnable-check`
- verify: count(subject="deferred book checks filed as records", equals=1)
- does: gives the record the summary ``Book page `<page>` gives QA no check it can run``
- verify: count(subject="deferred records naming their page", equals=1)
- does: lists the page's path under the services root as the record's one symbol
- verify: count(subject="deferred records with one symbol", equals=1)
- does: writes a body naming each skipped claim with what the book has to add for it
- verify: count(subject="skipped claims in the record body", equals=1)
- does: places the record under the repository whose book prefix holds the page
- verify: count(subject="deferred book checks placed by book prefix", equals=1)
- does: skips a page that already has an open `qa-deferred` record citing the same path
- verify: count(subject="book pages already on the register", equals=1)
- does: commits the filed records as `chore(<repo>): file the book checks qa could not run`
- verify: count(subject="deferred book check commits", equals=1)
- returns: `BacklogDrain` with the filed and skipped counts, or a note that there was no QA context to read
- verify: json_path(path="$.appended", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_deferred_obligations` @a57d509225b0
- tests: `workflows/tests/coder/shared/test_deferred_obligations_backlog.py::test_the_same_page_twice_files_once`
- tests: `workflows/tests/coder/shared/test_deferred_obligations_backlog.py::test_a_two_repo_workspace_places_the_page_by_its_book_prefix`
- tests: `workflows/tests/coder/shared/test_deferred_obligations_backlog.py::test_the_fix_lane_leaves_book_checks_for_the_book`

### select_fix_item

- sig: `select_fix_item(logger, repo_dir: str = "", workspace: str = "") -> FixPick`
- does: reads the open `qa` records of the workspace repositories and draws the oldest without changing it
- verify: count(subject="drawn qa records", equals=1)
- does: orders an id with no ULID, such as an imported one, before every minted id, and minted ids by their ULID
- verify: count(subject="qa records drawn oldest first", equals=1)
- returns: `FixPick` with `has_fix` true and the record's id, repo, area, summary and body, or `has_fix` false with the reason `no open qa record in <repos> — nothing to drain`
- verify: count(subject="fix draws", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::select_fix_item` @a57d509225b0
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_drain_keeps_going_until_no_open_qa_record_is_left`

### seed_fix_story

- sig: `seed_fix_story(logger, record_id: str = "", summary: str = "", epics_dir: str = "", epic: str = "", repo_dir: str = "", repo: str = "", area: str = "", body: str = "") -> FixStorySeed`
- does: creates the `fixes` epic, or the named one, as a follow-up bucket that needs no milestone when it does not exist yet
- verify: created(subject="the fixes epic")
- does: reuses a story of that epic whose `covers` holds the record id, and fills only its empty sections
- verify: count(subject="reused fix stories", equals=1)
- does: otherwise registers a researched seed with meta `sourceRecord: <record id>` and creates one story that covers the record id, slugged from the summary within 60 characters
- verify: created(subject="a fix story covering the record id")
- does: writes the record summary as the story's one acceptance criterion
- verify: count(subject="fix story acceptance criteria", equals=1)
- does: writes a Context section that names the record, its `<repo>/<area>`, the one-record scope and the record's body
- verify: count(subject="fix story bodies", equals=1)
- raises: `WorkflowFailed` when the record id or the summary is empty, or when the story cannot be created
- verify: count(subject="refused fix story seeds", equals=1)
- returns: a `FixStorySeed` carrying `story_id`: the reused story's own id, or `create_story`'s `entity_id` for a newly created one
- verify: json_path(path="$.story_id", equals="S-1")
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::seed_fix_story` @a57d509225b0
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_story_of_a_record_covers_the_record_id`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_the_fixes_bucket_the_coder_creates_needs_no_milestone`
- tests: `workflows/tests/coder/shared/test_follow_up_backlog.py::test_the_fix_story_seed_names_the_record_it_came_from`

### close_fix_item

- sig: `close_fix_item(logger, record_id: str = "", landed: dict[str, str] | None = None, repo_dir: str = "") -> FixClosed`
- does: closes the record as `done` with the reason `fixed in <repo>@<sha7>, ...`, one entry per repository that landed a commit
- verify: count(subject="closed fix records", equals=1)
- does: closes nothing when the record id or the landed map is empty
- verify: unchanged(subject="the drawn record")
- returns: `FixClosed` with `closed` true on success, or false with ostler's reason
- verify: count(subject="fix close results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::close_fix_item` @a57d509225b0
- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_committed_and_closed`
