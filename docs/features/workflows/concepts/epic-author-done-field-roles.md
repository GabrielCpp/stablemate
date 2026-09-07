---
type: concept
slug: epic-author-done-field-roles
title: Epic author completion field roles
---
# Epic author completion field roles

`EpicAuthorDone` records the completed authoring boundary rather than accepting alternate ways
to identify or control the epic. Its fields are complementary: `status` marks successful
completion, `epic` identifies the validated epic, `epic_dir` scopes its canonical directory,
`epic_path` identifies its validated `epic.md` document, `seed_count` reports researched seeds,
and `operator_resolutions` reports automatic resolution turns used before success.

No ranking exists among these fields. Consumers select the field whose representation or
completion evidence they need; none replaces another.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- rule: use `status` for completion, `epic` for identity, `epic_dir` for the canonical directory, `epic_path` for the validated document, `seed_count` for researched-seed evidence, and `operator_resolutions` for resolution-turn evidence; none supersedes another
