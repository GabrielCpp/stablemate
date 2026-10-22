---
type: flow
slug: trim-the-parse-cache
title: Trim the parse cache
---
# Trim the parse cache

- start: the shared parse cache grows
- steps:
  - [ostler cache clean](../planning.md#ostler-cache-clean)
- end: the caller reads how many entries were removed
- verify: exit_status(code=0)
- verify: json_path(path="removed", equals=0)
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with no state of its own, since the cache is shared
