# Depot infrastructure backlog

Benchmark worklist for the declare-only fixture. The depot is the build platform's storage
half: one bucket holds published artifacts, one service account writes to it, one group reads
it, and a nightly job expires what has aged out. Every one of those is *declared* — the repo
contains no code that runs against Google, and nothing here is ever applied.

Surfaces this app ships:

- **pulumi** — a Go Pulumi program under `pulumi/`, and the only surface there is. It exposes
  no endpoint, opens no port and answers no request. What it produces is a plan, and the plan
  is the artifact every claim in this book is about.

There is no identity to authenticate and no data to read back. A preview needs no credential
and reaches no Google API; it resolves the provider plugin locally and reports what it would
create. That is the property this fixture exists to exercise: a QA lane whose only evidence is
a document the build emits.

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope for
decomposition and none may be dropped.

## Publishing artifacts to a bucket only the build group can read

## Giving the deploy pipeline one identity, scoped to that bucket

## Expiring aged artifacts on a schedule
