---
name: no-shell-scripts
description: "The standing rule against ad-hoc shell scripts: a new capability goes into the repo's one CLI in a real language, never a new .sh beside the last one, because a shell script sits outside every gate the repo has — the linter, the type checker and the test runner all skip it. Carries the two-layer enforcement (a PreToolUse hook that refuses to write one, a tracked-tree sweep that catches what the hook could not see) and names the one exception: shell where another program dictates the interface."
---

## No ad-hoc shell scripts (load-bearing)

A capability goes into the **unified CLI** — a subcommand or module in the
package that owns the concern, or a guard under
`{{ template.guard_dir | default("scripts") }}/` for a repo-level check. Never a
new `.sh` beside the last one.

The reason is mechanical, not aesthetic. A shell script is outside every gate
this repo has: the linter does not read it, the type checker does not read it,
and the test runner cannot import it. So the discipline that holds everywhere
else stops at its first line — and because a script is the cheapest thing to
write, they accumulate: three files that each do two-thirds of the same job
under names that do not say so, and no test that would notice when one of them
stops working. "I'll just add a quick script" is how a codebase acquires a
second, unversioned, untested build system.

The rewrite is usually smaller than it looks. A script that greps a tree and
exits non-zero is a function plus a `main()`; what it gains is a name in an
import graph, a test that can call it directly, and a reviewer who can see it.

Shell is allowed exactly where **another program dictates the interface** — git
execs a hook, Docker execs an entrypoint as PID 1. Those files delegate on their
second line to the real language, which is the shape this rule asks for. They
are named in the guard's `ALLOWED` set, and adding to it is a decision somebody
makes on purpose, not a step in getting a task done.

```bash
{{ template.check_no_shell_command | default("make check-no-shell") }}
```

Two enforcement points, one rule, one file —
`{{ template.check_no_shell_script | default("scripts/check_no_shell.py") }}`.
A `PreToolUse` hook runs it with `--hook` and denies the tool call *before* the
file exists — the point at which the decision is still free — and the sweep
above scans every **tracked** file, because a hook only ever covers the machine
it is installed on. A script committed from a clone with no hook configured is
in the tree forever otherwise.
