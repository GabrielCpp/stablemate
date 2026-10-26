---
type: fixture
slug: environments-render-and-secrets
title: environments render and secrets
---
# environments render and secrets

Seeds two new books under `docs/services/`: `env-render-fixture`, one service with no `${NAME}`
references, and `env-secrets-fixture`, one service whose template references a secret no source
supplies. Neither book declares `secrets:` (only the stack root may), so the catalog's secret
source is the null one and the reference is unconditionally missing. `env-render-fixture`'s
`demo` service also declares a `okf-book-probe-missing` fixture set naming a file no step ever
creates; nothing lists it under `default-fixtures:`, so only a run that asks for it by name sees
it is gone.

## Steps

### write-render-fixture-stack

- kind: seed
- run: mkdir -p docs/services/env-render-fixture/ops && printf 'services:\n  demo:\n    about: a demo service with no secrets\n    define: service.yml\n    fixtures:\n      okf-book-probe-missing:\n        - absent.env\n' > docs/services/env-render-fixture/ops/stack.yml

### write-render-fixture-define

- kind: seed
- run: printf 'image: busybox\n' > docs/services/env-render-fixture/ops/service.yml

### write-secrets-fixture-stack

- kind: seed
- run: mkdir -p docs/services/env-secrets-fixture/ops && printf 'services:\n  worker:\n    about: a worker needing a secret no source supplies\n    define: service.yml\n' > docs/services/env-secrets-fixture/ops/stack.yml

### write-secrets-fixture-define

- kind: seed
- run: printf 'image: busybox\ncommand: ["sh", "-c", "echo ${OKF_BOOK_PROBE_SECRET}"]\n' > docs/services/env-secrets-fixture/ops/service.yml
