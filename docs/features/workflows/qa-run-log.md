---
type: format
slug: qa-run-log
title: Coder QA run log
---
# Coder QA run log

- file: `<spec_dir>/qa/qa-run.ndjson` or `<spec_dir>/qa/<scenario>/qa-run.ndjson`
- code: `workflows/src/workhorse_workflows/coder/shared/qa_support.py::assert_records`
- detail: [coder shared library](concepts/coder-shared-library.md)

Each line is one JSON object written by the QA runner. The parser ignores malformed lines and
non-assertion objects, while retaining the complete object for assertion records.

## Fields

### kind

- type: `string`
- required: true
- semantics: record discriminator; assertion records use the literal `assert`
- verify: json_path(path="$.kind", equals="assert")

### id

- type: `string`
- default: absent; failed-assertion routing substitutes `?`
- required: false
- semantics: assertion identifier used in failure notes
- verify: json_path(path="$.id", matches=".*")

### scenario

- type: `string`
- default: absent in single-scenario logs
- required: false
- semantics: scenario name used to group failed assertions
- verify: json_path(path="$.scenario", matches=".*")

### result

- type: `string`
- required: true
- semantics: assertion outcome; `FAIL` after trimming and case normalization is treated as failed
- verify: json_path(path="$.result", matches="PASS|FAIL")
