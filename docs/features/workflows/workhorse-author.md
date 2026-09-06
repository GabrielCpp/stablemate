---
type: cli
slug: workhorse-author
title: workhorse-author
---
# workhorse-author

- binary: `workhorse-author`
- code: `workflows/src/workhorse_workflows/author/workflow.py::main`

Runs the author registry described by the [author workflow composition root](concepts/author-workflow-composition-root.md). `run` selects its default Author flow or one of the registered authoring flows; Workhorse owns parsing and execution mechanics.

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
- does:
  - starts the selected registered authoring flow
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main`
- detail: [author epic edit flow](flows/author-epic-edit.md)
- detail: [author story edit flow](flows/author-story-edit.md)

### dot
- usage: `workhorse-author dot [--name ID] [-o out.dot]`
- flags:
  - `--name ID` overrides the rendered graph identifier.
  - `-o, --output PATH` writes DOT output to a file instead of standard output.
- does:
  - renders the registered Author and selectable-flow state graphs
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main`

### version
- usage: `workhorse-author version`
- does:
  - prints the installed Workhorse engine version
- verify: exit_status(code=0)
- code: `workflows/src/workhorse_workflows/author/workflow.py::main`
