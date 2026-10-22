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
  - holder-a — a claim holder
    - is: holder-a@example.com
  - holder-b — a second claim holder
    - is: holder-b@example.com
  - adjuster — carries the adjuster role claim
    - is: adjuster@example.com

## Steps

### seed-accounts

- kind: seed
- run: docker compose run --rm seed
