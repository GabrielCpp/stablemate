# Claims desk backlog

Benchmark worklist for the standalone-QA fixture. The app is an insurance claims desk — a
holder files a claim against a policy they hold, reads the claims that are theirs, and an
adjuster approves or denies it. One surface, three bullets: everything a person would touch
is an HTTP request, which is the property this fixture exists to exercise.

Surfaces this app ships:

- **api** — Go service generated from `app/api/openapi.yml`, the only writer of stored data,
  and the only surface there is. There is no client and no bundle; a browser is not a way in.

Identity is not one of the surfaces. The desk mints no credential and stores no password: a
caller arrives holding a bearer token from the Firebase Auth emulator that runs beside it, and
every rule below is a rule about what that token's subject and role may do.

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope for
decomposition and none may be dropped.

## Filing a claim against a policy

## Reading back the claims that are yours

## Approving and denying a claim
