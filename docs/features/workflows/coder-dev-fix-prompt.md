---
type: format
slug: coder-dev-fix-prompt
title: Coder dev-fix prompt
---
# Coder dev-fix prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-fix.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.fix`
- code: `workflows/tests/coder/dev/test_flow.py::lint_gate`
- detail: [coder development flow](flows/coder-dev.md)
- detail: [failure report](failure-report.md)
- detail: [dev-fix result](dev-fix-result.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_gate_lane_repairs_and_re_runs_until_clean`

The `lint_gate` fixture stands up `api` against `agents.yml`'s `lint: api: sh lint.sh` with a
shell command that fails while a marker file is absent, so the repair turn has a real gate to
satisfy and the second run is genuinely clean rather than a scripted claim of one. The marker
path returned is what the scripted `dev-fix` handler creates to clear the gate.

The repair envelope gives one failed gate report and the files already changed by the story. It
requires reproduction of the exact gate command, investigation of every reported location, a
minimal cause-level repair, a clean rerun, and a story-linked commit. It handles lint,
verification, and regression reports through the same input shape and returns the flow's fix
result; it must not weaken or delete the gate.

## Fields

### report
- type: `FailureReport`
- required: true
- semantics: exact gate identity, command, working directory, captured output, findings, and lap
- verify: json_path(path="$.report", matches=".+")

### changed_files
- type: list of string paths
- default: empty list
- required: false
- semantics: files already changed by this story in the selected service
- verify: json_path(path="$.changed_files", matches=".*")

### epic
- type: string
- default: empty string
- required: false
- semantics: epic identity used by the repair commit protocol
- verify: json_path(path="$.epic", matches=".*")

### story_slug
- type: string
- required: true
- semantics: story slug used to scope the repair and its commit
- verify: json_path(path="$.story_slug", matches=".+")

### story_id
- type: string
- required: true
- semantics: story identifier used as the repair commit trailer identity
- verify: json_path(path="$.story_id", matches=".+")

### result_schema
- type: string
- required: true
- semantics: rendered JSON contract the reply must satisfy as a fix result
- verify: json_path(path="$.result_schema", matches=".+")
