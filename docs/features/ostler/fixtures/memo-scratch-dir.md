---
type: fixture
slug: memo-scratch-dir
title: memo scratch dir
---
# memo scratch dir

Seeds an empty `memo-scratch/` directory to stand in for a repo root and hold the verdict
memo's own on-disk cache, both scoped to the scratch tree so no run touches the checkout the
book itself lives in.

## Steps

### make-memo-scratch

- kind: seed
- run: mkdir -p memo-scratch/cache
