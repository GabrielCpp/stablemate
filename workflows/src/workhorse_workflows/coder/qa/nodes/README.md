# nodes

The non-agent steps only the coder QA lane calls, grouped by subject.

## Map

- `evidence.py`: the evidence gate as a QA node. The check itself lives in `kit/qa/evidence.py`.
- `hygiene.py`: the pre-commit hygiene rules a QA pass must clear: no stray root screenshots, no fabricated sentinel IDs.
- `qa.py`: the steps of one QA run, from clearing the last pass's evidence to tearing the stack down.
- `regression.py`: which committed journey suites a story put at risk, and what they said when run.
