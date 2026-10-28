---
type: cli
slug: workhorse-author
title: workhorse-author
---
# workhorse-author

- binary: `workhorse-author`
- code: `workflows/src/workhorse_workflows/author/workflow.py::main` @1a18dc6ba866

Runs the author registry described by the [author workflow composition root](concepts/author-workflow-composition-root.md). `run` selects its default Author flow or one of the registered authoring flows; Workhorse owns parsing and execution mechanics.

The [workhorse-author driver runbook](ops/workhorse-author.md) exercises this CLI in dry-run mode with checkpointed inputs.

## Commands


### run
- usage: `workhorse-author run [<flow>] [--params JSON] [--dry-run]`
- flags:
  - `--context-file PATH` selects the context manifest for this run.
  - `--params JSON` supplies checkpointed inputs to the selected flow.
  - `--params-file PATH` supplies workflow parameters from a JSON object.
  - `--cli NAME`, `--profile NAME`, and `--config PATH` select the agent harness and configuration.
  - `--runs-dir DIR` and `--run-id ID` select the run-artifact location and stable identity.
  - `--dry-run` runs registered deterministic stand-ins.
  - `--resume-run PATH`, `--resume-latest`, and `--no-cache` select resume or fresh-run behavior.
- args:
  - `<flow>` selects `surveyor`, `parity-surveyor`, `epic-edit`, `story-edit`, `milestone`, `epic-split`, `epic-author`, `story-split`, `story-author`, or `finalize`; omitting it starts Author.
- does: starts the selected registered authoring flow
- fixture: none, because the command reads only the installed package
- run: invoke(argv=["run", "--dry-run"])
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main` @1a18dc6ba866
- detail: [author surveyor flow](flows/author-surveyor.md)
- detail: [author parity surveyor flow](flows/author-parity-surveyor.md)
- detail: [author epic edit flow](flows/author-epic-edit.md)
- detail: [author story edit flow](flows/author-story-edit.md)
- detail: [workhorse-author command selection](concepts/workhorse-author-command-selection.md)

### dot
- usage: `workhorse-author dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does: renders the registered Author and selectable-flow state graphs
- fixture: none, because the command reads only the installed package
- run: invoke(argv=["dot"])
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main` @1a18dc6ba866
- detail: [workhorse-author command selection](concepts/workhorse-author-command-selection.md)

### version
- usage: `workhorse-author version`
- does: prints the installed Workhorse engine version
- fixture: none, because the command reads only the installed package
- run: invoke(argv=["version"])
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main` @1a18dc6ba866
- detail: [workhorse-author command selection](concepts/workhorse-author-command-selection.md)

## Invocations

### plan-and-dispatch
- on: [run command](#run)
- run: invoke(argv=["run", "--dry-run"])
- trigger: after setup, then after each filled kind drains
- when: the approved milestone and its current planning artifacts are available
- fixture: none, because the dry run stands in for every agent turn and the fill reads only the artifacts that `when:` names
- does: files each kind of work from the current artifacts, drains it, and walks the run to its close
- verify: exit_status(code=0)
- verify: stdout(matches="dry-run ok")
- code: `workflows/src/workhorse_workflows/author/main/nodes/fill.py::fill_work` @0a6247ab8773
- code: `workflows/src/workhorse_workflows/author/main/nodes/completion.py::contract_digest` @becb105386f9
- code: `workflows/src/workhorse_workflows/author/main/nodes/completion.py::check_completion` @becb105386f9
- code: `workflows/src/workhorse_workflows/author/shared/digests.py::milestone_body_digest` @24786c0f94cd
- detail: [artifact-derived author stage selection](concepts/artifact-derived-author-stage-selection.md)
- tests: `workflows/tests/author/test_fill.py::test_stories_follow_dag_order_inside_milestone_epic_order`
- tests: `workflows/tests/author/test_workflow.py::test_a_story_nobody_can_fix_is_parked_and_the_epic_carries_on`
