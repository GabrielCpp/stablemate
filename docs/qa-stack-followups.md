# QA stack lifecycle — follow-on backlog

Deferred work from the durable QA-stack change (the `ensure_stack` node + `workhorse.stack`
supervisor + `qa-stack.yml` manifest). The reliability fix itself has landed; each item below
is a self-contained increment that was consciously left out of that first pass, ordered
roughly by value. See [qa-stack-manifest.md](qa-stack-manifest.md) and workhorse
`docs/GUARDRAILS.md` ("Long-lived processes must be owned, not backgrounded").

## Consuming repos author their `qa-stack.yml`

The base ships the contract, the supervisor, and the scaffold, but no repo has a manifest
yet — so `ensure_stack` reports `skip` everywhere and the durable path is exercised only by
unit tests. First real consumers:

- **The greenfield benchmark app** (`benchmarks/todo-app`) — give it a stack with services to
  bring up and seed so the author→coder loop actually drives `ensure_stack`. This is the
  cheapest end-to-end proof.
- **A rewrite-style consumer** — author its manifest from the existing documented targets
  (a `dev-stack-*` bring-up, a `stack-health` gate, an emulator/DB seed), with a
  self-freshening `launch` (`docker compose up -d --build`) so the case that used to be
  backgrounded-and-killed now runs through the supervisor. Verify adopt-if-serving and the
  leave-up policy on a re-run.

**Done when:** at least one repo's coder QA run brings its stack up via `ensure_stack` (not an
agent shell), and a second run on an unchanged tree adopts instead of rebuilding.

## Epic-level teardown bookend

`teardown_stack` exists and is unit-tested, but no workflow node calls it: the default policy
is leave-up (an expensive shared stack is cheaper to adopt next story than to rebuild), and
threading a per-story teardown through the QA flow's many exit paths would fight that policy.
What is missing is an **epic-scoped** bookend — reap a stack this run *owns* (a foreground
`launch` with a real `app_pgid`, or one with a documented `stop`) when the epic finishes, so a
CI/container run does not leak it.

- Add a teardown node on the epic's terminal path (after `merge`/`open_pr`, before the run
  ends) that calls `teardown_stack` with the handles `ensure_stack` returned.
- Respect the leave-up contract: no owned pgid and no `stop` → skip, exactly as today.

**Done when:** an owned stack is reaped at epic end; an adopted or leave-up stack is not.

## Skip the expensive re-seed when adopting

Today a cold `launch` is always followed by the `seed` steps, and `reuse: always` skips both.
The middle case is unaddressed: a code-independent stack that is *freshly brought up* pays the
full seed cost even when a prior run already seeded the same durable volume. A cheap
`seed`-level idempotency signal (a marker row / sentinel file the seed writes and checks)
would let `ensure_stack` skip a seed that has already run against a persistent backing store,
without weakening determinism.

- Option A (manifest-level): a `seeded_probe` command (exit 0 ⇔ already seeded) gating the
  `seed` block, mirroring `fresh` for `launch`.
- Option B (leave it to the repo): document that `seed` steps should self-check and no-op — no
  engine change. Prefer this unless a repo demonstrates the probe is worth the surface.

**Done when:** a re-brought-up code-independent stack does not re-run an already-applied seed,
and the choice (A vs B) is recorded.

## A reusable `fresh` fingerprint helper

`reuse: if-fresh` needs a `fresh` probe (exit 0 ⇔ the running stack reflects current code), and
every repo hand-writes one. A small shared helper — compare the running image digest(s) to a
digest of the source tree / Dockerfile inputs — would make `if-fresh` adoption viable without
per-repo probe authorship, which is what makes the expensive-code-stack case (rebuild only on
drift) practical rather than theoretical.

- Ship it as a documented one-liner or a tiny script the scaffold references, not as engine
  code — it is repo-shaped (which images, which inputs).

**Done when:** a repo can enable `if-fresh` on a code-embedding stack without writing its own
drift check from scratch.

## Saddlebag env-pool phase 4

Orthogonal but adjacent: the stack a manifest brings up often needs `.env`-shaped config the
agent may not read. [saddlebag-environment-pool.md](saddlebag-environment-pool.md) phases 1–3
shipped; **phase 4 (workflow adoption)** is outstanding — the `ensure_env` bookend
(`saddlebag env render … --run-id`), the `setup-fix.md` rewrite to stop touching `.env` files,
and denying agent reads of `.env*`. This pairs naturally with `ensure_stack`: render the
environment, then bring the stack up. Track it there; noted here so the two are sequenced
together when a repo needs both.

## End-to-end coverage of the `ensure_stack` path

The supervisor and node are unit-tested, and the QA topology test asserts the new routing, but
no whole-flow test drives a real bring-up (the existing `test_story_mode`/`test_flow_phases`
runs fail in the documentation phase, upstream, independent of this change). Once a benchmark
manifest exists (item 1), add a flow test that asserts `ensure_stack` ran, gated `run_qa_plan`
on `stack_ready`, and that a `no` result routed to the setup loop rather than QA.

**Done when:** a flow test exercises `ensure_stack` → `run_qa_plan` with a real manifest, and
the stale-adoption guard is covered end to end.
