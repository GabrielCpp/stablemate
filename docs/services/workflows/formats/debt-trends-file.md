---
type: format
slug: debt-trends-file
title: Debt register trends file
---
# Debt register trends file

- file: `<artifacts>/backlogs/trends.md`
- code: `workflows/src/workhorse_workflows/review_debt/nodes/trends.py::render` @ac34e86db8ae
- detail: [review-debt flow](../flows/review-debt.md)
- detail: [debt register](../../ostler/concepts/the-debt-register.md)

The [review-debt flow](../flows/review-debt.md) writes this file at the root of the register,
beside its repository folders. The register reads records only at `<repo>/<area>/<id>/record.md`,
so it does not read this file back as a record. The flow renders the file from a
[trend report](trend-report.md) that passed accounting and from the read it covers. The same
report over the same read renders the same text. The file sits on the untracked shelf, so the
flow never commits it.

## Layout

1. The heading `# Debt register trends`.
2. The line `<n> records reviewed`, where `<n>` counts the ids of the read.
3. The report's summary on one line.
4. One `## <name>` section per cluster, in the report's order. Each holds the cause on one line,
   then one bullet per record in the order of the read.
5. A `## Singletons` section when the report has any. Each bullet ends with
   `(cause: <cause>)`.

Each record bullet reads `- <id> (<repo>/<area>, <status>): <summary>`. Every id of the read
appears on exactly one bullet. The renderer joins the report's names, causes and summary onto one
line each, so no text from the turn can start a line of its own.

- verify: contents(subject="trends.md", matches="(?m)^# Debt register trends$")
- code: `workflows/src/workhorse_workflows/review_debt/nodes/trends.py::render` @ac34e86db8ae
- tests: `workflows/tests/review_debt/test_nodes.py::test_the_rendered_file_is_the_same_text_for_the_same_report`
- tests: `workflows/tests/review_debt/test_nodes.py::test_a_file_at_the_shelf_root_is_never_read_as_a_record`
