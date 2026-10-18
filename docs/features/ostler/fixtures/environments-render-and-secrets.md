---
type: fixture
slug: environments-render-and-secrets
title: environments render and secrets
---
# environments render and secrets

Seeds two new books under `docs/features/`: `env-render-fixture`, one service with no `${NAME}`
references, and `env-secrets-fixture`, one service whose template references a secret no source
supplies. Neither book declares `secrets:` (only the stack root may), so the catalog's secret
source is the null one and the reference is unconditionally missing.

## Steps

### write-render-fixture-stack

- kind: seed
- run: mkdir -p docs/features/env-render-fixture/ops && printf 'services:\n  demo:\n    about: a demo service with no secrets\n    define: service.yml\n' > docs/features/env-render-fixture/ops/stack.yml

### write-render-fixture-define

- kind: seed
- run: printf 'image: busybox\n' > docs/features/env-render-fixture/ops/service.yml

### write-secrets-fixture-stack

- kind: seed
- run: mkdir -p docs/features/env-secrets-fixture/ops && printf 'services:\n  worker:\n    about: a worker needing a secret no source supplies\n    define: service.yml\n' > docs/features/env-secrets-fixture/ops/stack.yml

### write-secrets-fixture-define

- kind: seed
- run: printf 'image: busybox\ncommand: ["sh", "-c", "echo ${OKF_BOOK_PROBE_SECRET}"]\n' > docs/features/env-secrets-fixture/ops/service.yml
