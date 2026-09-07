---
type: concept
slug: epic-evidence-field-roles
title: Epic evidence field roles
---
# Epic evidence field roles

`EpicEvidence` records whether one explicit epic has its document and durable researched seeds.
Its fields are complementary evidence, not alternate implementations: `ok` records the overall
validation result; `epic`, `epic_dir`, and `epic_path` retain the resolved identity and locations;
`seed_count` records the researched seeds found; and `errors` retains validation findings.

No ranking exists among these fields. Consumers select the field needed for the question they are
answering; no field replaces another.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- rule: use `ok` for the validation result, `epic` for identity, `epic_dir` for the attempted or resolved directory, `epic_path` for the document location, `seed_count` for researched-seed evidence, and `errors` for validation findings; none supersedes another
