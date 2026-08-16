Implement the worklist packet below and **make the observed-red tests green**. This is the second half of a two-turn TDD split: a previous turn wrote the failing tests for the packet's acceptance criteria, and a deterministic gate ran them.

- Digest: `{{ workhorse_var('plan_digest') }}`
- Repository: `{{ workhorse_var('repo_root') }}`
- Packet: `{{ workhorse_var('task') }}`
- Red gate status: `{{ workhorse_var('red_status') }}`
- Red gate log: `{{ workhorse_var('red_log_path') }}`

```markdown
{{ workhorse_var('plan_text') }}
```

## Read the red first

The red gate's status above says what the gate observed after the tests turn:

- `red` — the suite genuinely failed. Read the log at the path above: those failures are your contract. **Done means exactly those tests pass** — plus everything else this prompt requires.
- `skipped` (or blank) — the gate could not run the suite (no resolved test command, or the run never returned). The tests still exist in the worktree; run them yourself with the touched area's test command, observe what fails, and proceed with those failures as the contract.
- `unattributed` — the suite failed, but the run stopped before it ever named one of the new test files (a multi-project suite halting on an unrelated failure, for instance), so the gate observed nothing about them. Read the log to see where it stopped, then run the new tests directly — narrow the command to their files — and use *that* failure as your contract. Do not treat the gate's exit code as evidence, and do not repair the unrelated failure: it is not this packet's.
- `all_green` / `impure` / `no_tests` — the tests turn exhausted its reworks and the gate let the packet proceed. Treat the tests in the worktree as a starting point, not a contract: audit them against the packet's acceptance criteria, repair or add what is missing, then implement.

**The failing tests are the specification of done, not an obstacle.** Editing a test is allowed only when the test itself is wrong — asserting something the plan contradicts, or broken as code — and every such edit must be declared in your result `notes` with the reason. Weakening an assertion so it passes is the failure mode the review gate audits for.

## Implement

Read the plan, repository instructions, relevant existing code, and tests before editing. Inspect the current worktree first: this state is resumable, so a prior attempt may have left correct partial changes. Complete or repair those changes rather than starting over.

Change only paths owned by the packet. Meet every acceptance criterion, preserve compatibility required by the plan, and run the packet's verification commands. A behavior you add beyond the written tests still gets its own test. Do not edit the source plan, worklist, run artifacts, generated agent adapters, or `.git`. Do not commit or push; deterministic workflow nodes own both operations and will reject out-of-scope changes.

Return this JSON object as the last thing in your response:

```json
{"status":"done|blocked","notes":"what changed, how the red went green, and any tests-turn test you edited with the reason — or the exact blocker"}
```

`done` is a report, not the gate: the workflow independently checks changed paths and commands.
