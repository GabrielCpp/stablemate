---
name: design
description: "The universal contract for a test that can actually fail, language-neutral — name the defect it catches, watch it go red before trusting it, derive fixtures from the producer instead of restating them, assert on evidence of work rather than status, and cover the composition and not only the units. Load whenever writing or reviewing tests; a stack skill (go-testing, python-testing, flutter-testing, react-router-qa, pulumi-qa) supplies the concrete mechanics, and the e2e-testing skill layers the end-to-end-specific contract (locators, waits, flake diagnosis) on top. Applies to test files in any language."
applyTo: "**/*_test.go,**/test_*.py,**/*_test.py,**/*_test.dart,**/*.test.ts,**/*.test.tsx,**/*.spec.ts,**/*.spec.tsx,tests/**,**/__tests__/**"
tags: [standards, tests]
---

# The Test-Design Contract

This is the language-neutral definition of what makes a test worth having. It states the
*contract*; the mechanics of meeting it — runner, assertion library, fixture syntax, mocking
tool — are stack-specific. Pair this with the matching stack skill:

- Go → the `go-testing` skill
- Python → the `python-testing` skill
- Flutter / Dart → the `flutter-testing` skill
- React Router / TypeScript → the `react-router-qa` skill
- End-to-end / journey specs (any driver) → the `e2e-testing` skill, plus the stack's driver mechanics (e.g. `react-router-playwright`)

**A green suite is not evidence. A suite that has failed for the right reason is.** Expensive
bugs rarely survive because nobody wrote a test; they survive because the tests that were
written could not detect them. Correct, well-named, fast, green — and blind. Every rule below
exists to make a test *capable of failing*.

## 1. Name the defect before writing the test

Complete the sentence **"this test fails when ______"** with a specific, plausible defect. If
the blank can only be filled with "the code changes" or "something breaks", you are writing a
change-detector, not a test. Delete it and write the one that names a real failure.

Put the answer in the test name or a one-line comment. A reader six months out needs to know
what the test is guarding, not what it calls.

## 2. See it red before you trust it

**Never trust a test you have not watched fail.** A test that has only ever been green is
untested itself — the assertion may not reach the code, the fixture may not exercise the path,
the mock may be absorbing the call.

- **Building new behavior → write the test first, full stop.** The test exists before the
  code it exercises, and it fails *because the behavior is missing* — not because an import
  is broken or a fixture won't load. Then write the code that turns it green. Test-after
  always degenerates into asserting what the code already does, which is §9's blind spot
  built in from day one.
- Fixing a bug → write the test **first**, watch it fail *for the reported reason*, then fix.
- Adding a test to existing code → break the code deliberately, confirm red, restore.
- Neither is possible → assert on a hand-built value that is wrong on purpose once, read the
  failure message, then correct it.

Red-first is not ceremony. It is the only evidence that the test is wired to the thing.
Keep the red run's output — a captured failing run is the proof a reviewer can check;
"I saw it fail" is not. A harness that separates the test-writing pass from the
implementing pass (as the coder workflow's red gate does) is this rule made structural:
the tests land alone, are *observed* red by deterministic tooling, and only then does the
implementation begin.

## 3. Derive fixtures from the producer; never restate them

When a fixture stands in for something the system generates — a scaffold, a schema, a
serialized payload, a config file — **generate it by calling the real producer**, not by
copying its output into the test file.

```
# wrong: a snapshot of what the scaffolder emitted, the day someone looked
FIXTURE = "## Context\n\n## Acceptance Criteria\n"

# right: the scaffolder itself, so the fixture cannot drift from the contract
def fixture(): return scaffolder.build_body(slug)
```

A hand-copied fixture stops being the truth at the exact moment the contract changes — which
is the moment the test was supposed to catch something. Drift is silent and the suite stays
green.

## 4. Test both sides of every predicate

For any boolean gate — `is_valid`, `is_done`, `has_access`, `should_retry` — assert the true
case *and* the false case, and be deliberate about which side is dangerous. A predicate that
wrongly answers **yes** skips work; one that wrongly answers **no** merely repeats it. The
first is almost always the costly direction, and it is the one usually left untested.

Give the predicate the input that is *most likely to fool it*, not the input that obviously
should pass. If "is this thing complete?" is answered by looking for a marker, the test that
matters is the one where an incomplete thing carries that marker.

## 5. Assert on evidence of work, not on status

`assert result.ok` passes when nothing happened at all. Status is the system's own opinion of
itself; a pipeline that performs zero work and reports success is the highest-severity class of
bug there is, and it satisfies every status assertion in the suite.

Assert on counts, contents, and side effects: *how many* records were written, *what* the output
actually contains, *which* steps executed. "Reported success" and "did the work" are different
claims and need different assertions.

## 6. Cover the composition, not only the units

A suite of isolated unit tests cannot see a **wiring** defect: the handler that is never
registered, the middleware left out of the chain, the pipeline stage the router skips, the
branch that routes past the step doing the real work. Every unit passes; the system does
nothing.

At least one test must run the **real composition** with the edges intact — the graph, the
router, the state machine, the DI container — and assert on *which steps executed*, not only on
the final value. Fake the expensive leaves (network, model calls, clock), never the wiring.

An end-to-end spec driving the running system through its UI is the outermost composition test,
and it carries failure modes of its own (locator brittleness, wait races, cold-start noise) — the
[`{{ instruction_file("e2e-testing") }}`]({{ instruction_file("e2e-testing") }}) skill is this
contract extended to that layer.

## 7. Every gate needs a test that proves it rejects

A validator, guard, or lint rule exercised only on valid input is not known to be a gate. For
each one, assert: valid input passes, invalid input **fails**, and the failure message *names
the offender*. A gate that fails without saying what failed sends the next person to read the
code instead of the output.

## 8. Never skip a suite to green

A test that skips when a dependency is absent reports success having exercised nothing — the
same silent degradation the tests exist to catch, relocated into the harness. If the code under
test genuinely requires a tool, declare that requirement so the environment fails loudly and
early; do not teach the suite to shrug.

Reserve skips for things that are legitimately not applicable (a platform-specific path on
another platform), never for "the thing this suite tests isn't installed".

## 9. Get ground truth from outside the code's own assumptions

Tests written from the same mental model as the implementation inherit its blind spots — they
can catch typos, never a wrong contract. If four places in a system agree on a wrong definition,
tests written alongside them agree too, and all of it is green.

Anchor assertions to something the implementation does not own: the spec, the upstream
producer's real output, a captured artifact from a real failed run, the consumer's actual
requirement. When a bug escapes to production, the artifact it produced belongs in the suite as
a fixture — that is ground truth no amount of shared assumption can bend.

## 10. Do not assert on incidentals

The counterweight to everything above. Do not pin whitespace, key order, log wording, or private
call sequences — a test that fails on a harmless refactor trains people to fix tests reflexively
rather than read them, and that habit is how a real failure gets waved through.

Assert the behaviour a caller depends on. If nobody would notice the change, no test should.

## 11. A test that runs is one that has to clean up after itself

A test owns everything it spawns. A fixture that opens a file has to close it; a
subprocess a test launches has to be reaped (the `Popen` object, not just the
process); an environment variable it sets has to be unset; a temp directory it
creates has to be removed. The state a test leaves behind leaks into the next
one — a port held open, a half-written file a later test trips over, a global
flag a sibling fixture patches over because it assumed no one else would set it.
The next person to debug a flaky test will spend hours tracing the contamination
back to a test that ran minutes earlier and never finished cleaning up.

The same rule for **the system, not just the test process.** Do not touch state
the test did not put there: do not write into the user's home directory, do not
modify the shell's `PATH`, do not bind a privileged port, do not create global
files in `/tmp` with predictable names, do not `git init` outside the test's
`tmp_path`. A test that contaminates the developer's machine is a test that
makes the suite the reason CI broke for a different commit.

The harness that ships with the suite is part of the contract: `pytest`'s
`tmp_path` is per-test and auto-cleaned, `monkeypatch` reverts on teardown,
`capsys` does not leak stdout. Use them; do not roll your own with `tempfile.mkdtemp()`
and a manual `rm -rf` that someone will forget to wire into a fixture.

## 12. Fix the warning before you commit, or the next person will lose it

A test suite that ships with warnings is a test suite with broken windows. The
next person to add a test sees a warning they cannot interpret and assumes it
is theirs — then learns to ignore the whole stream. The third person sees a
real `DeprecationWarning` that the framework emitted for the bug they just
introduced, glances at the warning pile, scrolls past, and ships the broken
change. The warning was theirs, but the noise was ours.

Treat every warning as an error at the runner level (`filterwarnings = ["error"]`
in the package's pytest config is the load-bearing line). A warning emitted by
a third-party library that cannot be fixed belongs in a `filterwarnings` entry
narrowly scoped to that library and category — never in the broad default. A
warning emitted by the code under test means there is a `with` block missing,
a `Popen` that was never `.wait()`-ed, a fixture that monkeypatched without
restoring. Fix it before commit, not "later".

## 13. A test asserts what its module owns — not what the rest of the repo does

A test in `<package>/tests/<topic>.py` is responsible for `<package>`'s
contract. It is not a place to re-assert that the root `Makefile` runs, that
the workspace's other package imports cleanly, that the docs build, or that a
sister package's CLI exits zero. Those are checks, and they belong in a guard
under `scripts/` (or in the package that owns them), not in a test suite that
will fail next time a sibling changes its public surface for unrelated reasons.

The test that broke a CI run because it reached across packages was the test
that taught the next person to mistrust the suite. Two tests fail for the
same reason — "sibling X is broken" — and the operator spends the morning
bisecting a problem that has nothing to do with the package they were working
on. Reach only into the unit under test; let the gates that own the cross-
package contract run elsewhere.

## Review checklist

Before approving a test — yours or someone else's:

- [ ] I can name the defect this fails on.
- [ ] It has been observed failing for that reason.
- [ ] Its fixtures come from the producer, not from a copy.
- [ ] It asserts work happened, not that status says so.
- [ ] The dangerous side of the predicate is the side under test.
- [ ] Something in the suite exercises the real wiring.
- [ ] It cannot skip itself into green.
- [ ] It cleans up after itself — files, subprocesses, env, network state (§11)
- [ ] It does not emit a warning the package's pytest config would convert to an error (§12)
- [ ] It does not assert a contract a sibling package owns (§13)

## Smells

| Symptom | What it usually means |
| --- | --- |
| Suite green while a known bug is live | Fixtures encode the same assumption as the code (§3, §9) |
| Every test asserts `ok == true` | Status assertions, no evidence of work (§5) |
| A step "runs" but has zero executions in production | No composition test (§6) |
| A gate has only passing-input tests | It has never been shown to reject (§7) |
| Tests skip on the CI box, pass locally | Skipped-to-green suite (§8) |
| A refactor breaks 40 tests, no behaviour changed | Asserting incidentals (§10) |
| A test passes alone, fails after another test | Leaked state across tests (§11) |
| The warning pile grows by 5 per commit | A real warning is being lost in the noise (§12) |
| A test in package A fails because package B changed | Test reached outside its module (§13) |
