---
type: concept
slug: artifact-derived-author-stage-selection
title: Artifact-derived author stage selection
---
# Artifact-derived author stage selection

The Author main flow fills its work list from the approved milestone's persisted epic, story, and
receipt artifacts. The ostler graph is the source of truth, and a stage never writes items of its
own. Three kinds sit on the run's work list: `epic`, `story-split`, and `story`. A barrier state
fills one kind, and the drain after it hands each pending item to its stage in turn.

- code: `workflows/src/workhorse_workflows/author/main/nodes/fill.py::fill_work` @0a6247ab8773
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author` @41e4cc0d4cfc
- rule: fill a kind completely before the drain that empties it; file an item the artifacts already satisfy as `done`, so the list shows the whole milestone; never refile an id already on the list
- tests: `workflows/tests/author/test_fill.py::test_epics_are_filed_in_milestone_order_and_written_ones_are_done`
- tests: `workflows/tests/author/test_fill.py::test_stories_follow_dag_order_inside_milestone_epic_order`
- tests: `workflows/tests/author/test_fill.py::test_a_second_fill_files_nothing_and_keeps_every_status`

The epic split runs only while the milestone lists no valid ordered epics. A missing, duplicated,
or unknown epic name on the milestone fails that check, and the flow hands off to the epic split
before it fills anything. The `epic` kind holds one item per milestone epic, in milestone order,
with the id `epic:<epic>`. An epic is `done` when it has an epic document and at least one seed.

The `story-split` kind holds one item per epic whose `epic` item is done, with the id
`story-split:<epic>`. An epic is `done` when its story graph is valid and its story-split receipt
is passed and digest-current. A valid graph has unique slugs, local dependencies, local seed
coverage, a document for every story, and no cycle, and every active seed is covered.

The `story` kind holds one item per story of an epic whose `story-split` item is done, with the id
`<epic>/<story>`. Items run in milestone epic order, then story DAG order. A story is pending when
ostler's author-need report would select it, or when its audit receipt is not current. A receipt
is current when its status is `passed` and its recorded SHA-256 digest matches the story bytes.
Every other story is filed `done`.
