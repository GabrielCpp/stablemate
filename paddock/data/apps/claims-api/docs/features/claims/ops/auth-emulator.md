---
type: environment
slug: auth-emulator
title: Local auth emulator
---
# Local auth emulator

- selector: the default and only environment; the compose stack is the whole of it.
- local-only: true
- services:
  - claims-api: `http://localhost:18085` — the service under test, published from the `app` container.
  - auth: `http://localhost:18086` — the Firebase Auth emulator's REST surface, published from the
    `auth` container, which the API container reaches as `auth:9099`.
- backing:
  - auth emulator: project `claims-api-example`, started by `firebase emulators:start --only auth`
    at a pinned `firebase-tools`. It holds identities in memory and issues real, verifiable tokens
    for that project and no other.
  - claim ledger: a JSON file on a named volume at `/data/claims.json` inside the `app` container.
  - seeded identities: `holder-a@example.com` and `holder-b@example.com` as holders, and
    `adjuster@example.com` carrying the custom claim `role: adjuster`, all created by a one-shot
    `seed` service the API waits on.

There is no credential anywhere in this stack, and that is the point rather than a shortcut. The
emulator mints identities for anyone who asks — `accounts:signUp` accepts any string as its API key
— and the service verifies against it because `FIREBASE_AUTH_EMULATOR_HOST` is set in the API
container. So *acquiring a token is free, and acquiring three is as free as acquiring one*. Nothing
about this environment makes it easier to prove a rule with the identity already in hand than to
prove it with a second identity that should be refused.

The emulator's own port is published on `18086` rather than left at the tool's default `9099`,
because the default is what any other project's emulator on the same machine would take.

Passwords for the seeded identities are fixed strings in `auth/seed.mjs` and are not secrets:
they authenticate against a process that will accept anything and that forgets everything when the
container stops.
