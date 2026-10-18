---
type: fixture
slug: cli-scenario-arrangement
title: cli scenario arrangement
---
# cli scenario arrangement

Seeds every piece of state `ostler env check` and `ostler artifact scaffold`'s claims depend on:
a scratch repo `env-check-scratch/` whose book's `ops/stack.yml` is a YAML list instead of a mapping, and an empty
`cli-book-scaffold-spec/` under the repo root so `--spec cli-book-scaffold-spec` resolves there instead of
under the specs root.

## Steps

### write-malformed-stack

- kind: seed
- run: mkdir -p env-check-scratch/docs/features/env-check-fixture/ops && printf -- '- a\n- b\n' > env-check-scratch/docs/features/env-check-fixture/ops/stack.yml

### seed-empty-spec-dir

- kind: seed
- run: rm -rf cli-book-scaffold-spec && mkdir -p cli-book-scaffold-spec
