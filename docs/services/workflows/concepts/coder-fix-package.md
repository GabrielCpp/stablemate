---
type: concept
slug: coder-fix-package
title: Coder fix package
---
# Coder fix package

The `fix` machine drains the open `qa` records of the run's workspace repositories on the
[debt register](../../ostler/concepts/the-debt-register.md). A QA run files those records for the
items its owner left for later. Each drawn record becomes a one-criterion story and receives one
owner turn that fixes and QAs it. The machine then gates, documents and commits each item on its
own and closes its record as `done`. The main coder flow hands off to it once a story's QA passes,
and `workhorse-coder run fix` runs it alone.

Records filed by the dev turn as `coder` follow-ups and the `qa-deferred` book checks stay on the
register, because the drain draws only `qa` records. A gate still red after the last repair lap,
or an owner turn that reports a block, goes to an operator gate. An item no repository landed a
commit for leaves its record open.

- code: `workflows/src/workhorse_workflows/coder/fix/flow.py` @047343956550
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix` @047343956550
- detail: [coder backlog contract](coder-backlog-contract.md)

## Methods

### render_gate

- sig: `render_gate(report: FailureReport) -> str`
- does: format a FailureReport as markdown with source gate name, working directory, command, and output
- verify: json_path(path="$.rendered", matches="(?s)^The `[^`]+` gate failed in `[^`]+`\\.\\n\\nCommand: `[^`]+`\\n\\n```\\n.*\\n```$")
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::render_gate` @047343956550
- tests: `workflows/tests/coder/fix/test_flow.py`

