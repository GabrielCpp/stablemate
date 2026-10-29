---
type: fixture
slug: environments-variables-page
title: environments variables page
---
# environments variables page

Seeds one new book under `docs/services/`, `env-vars-fixture`, whose `ops/` holds an `environment`
page with the slug `okf-book-env-vars-probe` and two literal `variables:`,
`OKF_BOOK_PROBE_LEVEL: debug` and `OKF_BOOK_PROBE_PORT: 8080`. The page marks no variable
`secret`, so a command run under it needs no saddlebag record and no daemon, and a dotenv rendered
from it holds no blank name.

## Steps

### write-vars-fixture-page

- kind: seed
- run: mkdir -p docs/services/env-vars-fixture/ops && printf -- '---\ntype: environment\nslug: okf-book-env-vars-probe\ntitle: Env vars probe\n---\n# Env vars probe\n\n- selector: the probe environment the book seeds for its own checks\n- local-only: true\n- variables:\n  - OKF_BOOK_PROBE_LEVEL: debug\n  - OKF_BOOK_PROBE_PORT: 8080\n' > docs/services/env-vars-fixture/ops/env-vars-probe.md
