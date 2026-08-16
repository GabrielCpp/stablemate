Write the **failing tests** for the worklist packet below — tests only, no production code. This is the first half of a two-turn TDD split: you translate the packet's acceptance criteria into tests that fail because the behavior does not exist yet; a separate turn will make them pass.

- Digest: `{{ workhorse_var('plan_digest') }}`
- Repository: `{{ workhorse_var('repo_root') }}`
- Packet: `{{ workhorse_var('task') }}`
- Test command the gate will run: `{{ workhorse_var('test_command') }}`

```markdown
{{ workhorse_var('plan_text') }}
```

{% if gate_feedback %}
## Rework — the red gate rejected the previous attempt

> {{ workhorse_var('gate_feedback') }}

What each rejection means:

- `all_green` — the suite passed with the behavior still unimplemented. The tests exercise nothing missing: they assert on existing behavior, mock away the thing under test, or never call the new code path. Rewrite them to genuinely depend on the missing behavior.
- `impure` — the diff contained **production code**: a source, markup, style, SQL or terraform file that is not test code. Revert every listed file and express the setup inside test files instead. Fixtures, data files, docs and config are *not* impure — only code the code turn owes is.
- `no_tests` — you wrote no test file. Write the tests; if something genuinely blocks you, return `status: "blocked"` naming it instead of doing nothing.
- `unattributed_red` — the suite failed, but no reported failure named any file you wrote: the red belongs to something already broken, not to your tests. Make the scenarios actually run (a skipped, uncollected or never-imported test proves nothing) and confirm your own test names appear in the failure output.
{% endif %}

Read the plan, repository instructions, and the existing test suite around the packet's paths before writing anything, so new tests land in the right files, follow the local naming signature, and reuse established fixtures. Inspect the current worktree first: this state is resumable, so a prior attempt may have left correct partial tests to complete rather than restart.

For each of the packet's acceptance criteria, write the test(s) that will prove it. Assert on the **behavior the criterion describes**, not on implementation details — the code turn must be free to implement the plan's design without rewriting your assertions. **Each test must fail because the behavior is missing** — a compile error in the test itself, an import typo, or a broken fixture is not a meaningful red. Where the language allows, reference the planned entry points so the failure is an assertion failure or a missing-symbol error at the planned seam, not noise.

Run the test command above (or, if it is blank, the touched area's test command from the repository instructions) and **confirm the new tests fail for the right reason**. Pre-existing tests must still pass; if your additions broke an unrelated test's collection or build, fix the test code until only the intended failures remain.

A deterministic gate re-runs that command after your turn and inspects the diff. It loops the work back to you when the suite exits green, when the diff contains production code, when no test file was written, or when the failures it sees name none of your files — so the fastest path through is a pure diff that is red **on your tests**.

**Never do this:**

- Create or edit **any production code file** — no source, no markup, no styles, no SQL, no terraform, no generated code. Fixtures, test data and test-local config are yours; the implementation is the code turn's.
- Write a test that passes against the current code. Red is the deliverable.
- Stub or mock the very behavior under test so the test can pass without it.
- Delete or weaken existing tests to make room.
- Touch paths outside the packet's ownership, the source plan, the worklist, run artifacts, or `.git`. Do not commit or push.

Return this JSON object as the last thing in your response:

```json
{"status":"done|blocked","notes":"which acceptance criteria each test covers and the red you observed, or the exact blocker"}
```

`done` is a report, not the gate: the workflow independently re-runs the suite and inspects the diff.
