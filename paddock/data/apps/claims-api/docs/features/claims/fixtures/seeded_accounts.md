---
type: fixture
title: Seeded accounts
---
# Seeded accounts

The app's own seeder, `auth/seed.mjs` — the same file the `seed` compose service runs at boot —
so the identities the QA lane authenticates as are the identities the app itself considers
seeded. There is no second copy of the arrangement to drift from the first. Re-running it is
safe: the seeder treats an account that already exists as done.

- provides:
  - holder-a — a claim holder, `holder-a@example.com`
  - holder-b — a second claim holder, `holder-b@example.com`
  - adjuster — `adjuster@example.com`, carrying the adjuster role claim

## Steps

### seed-accounts

- kind: seed
- run: docker compose run --rm seed
