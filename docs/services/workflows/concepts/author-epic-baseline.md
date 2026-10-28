---
type: concept
slug: author-epic-baseline
title: Author epic baseline
---
# Author epic baseline

The epic baseline records which seed subsections and stories each epic held when an author run began. The epics live untracked in the artifacts dir, so git cannot say what the run started with. The baseline is the run's own record.

The run takes the baseline in its start step, before any planning runs. The recorded value travels to the finalize sub-flow as a JSON string. The reconcile gate compares the epics on disk with it and fails when a seed or a story the run began with is gone.

- code: `workflows/src/workhorse_workflows/author/shared/baseline.py` @9899064edd1a
- rule: record the baseline once at run start, because epics outside the repository have no committed history to compare with
- rule: an empty baseline skips the reconcile gate, because a run that began with no epics cannot drop any
- rule: read epic scope from the epic folders by seed subsection and story folder name, never from git
- tests: `workflows/tests/author/finalize/test_reconcile.py::test_a_run_that_drops_a_story_it_started_with_fails_the_gate`
