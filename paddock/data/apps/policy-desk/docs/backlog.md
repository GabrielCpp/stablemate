# Policy desk backlog

Benchmark worklist for the workload run. The app is an insurance policy register — the
desk where a policy is written to the books, read back, amended and cancelled — a JSON
API with a browser client over it. Two surfaces, three bullets: enough scope that the
stories form a queue with real dependencies in it, which is the property this spec
exists to exercise.

Surfaces this app ships:

- **api** — Go service, the only writer of stored data, and the origin the bundle is
  served from
- **web** — React single-page app, the only surface a person touches

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope
for decomposition and none may be dropped.

## Writing a policy to the books

## Reading the register back

## Amending and cancelling a policy
