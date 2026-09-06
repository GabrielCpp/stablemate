---
type: format
slug: committed
title: Author commit result
---
# Author commit result

The commit result says whether the author flow actually created its requested commit.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Committed`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### committed
- type: boolean
- default: false
- required: false
- semantics: whether the author operation created a commit
- verify: json_path(path="$.committed", equals=False)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Committed`
