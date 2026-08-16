---
description: "Push a code change into the workhorse runs that are already going — find the live runs, check they resolve your source tree, and reload them in place"
argument-hint: "[what changed, or a run id]"
metadata:
  generated_by: farrier
  source: library/prompts/stablemate/reload-runs.md
  resolve: "farrier source .claude/commands/stablemate-reload-runs.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Reload the runs already holding the old code

A push does not reach a run that is already going. Its process imported the
workflow modules when it started, and a Python process does not notice that a
file on disk changed — so a live run keeps spending real money executing the
exact code you just fixed, and keeps doing it for however many hours or days it
has left.

$ARGUMENTS

## 1. Find the live runs

```bash
.venv/bin/groom status                        # which runs are live, and where
workhorse-<name> control status --run <id>    # is this process really serving that run dir
```

## 2. Check the run resolves your source tree, not a wheel

This is the way a reload silently reports success over code it did not load. A
reload replaces the entry package plus every top-level package installed from a
source tree; a wheel in `site-packages` is deliberately left alone.

```bash
<run's venv>/bin/python -c "import workhorse_workflows as w; print(w.__file__)"
```

If that prints a `site-packages` path, reloading will change nothing — reinstall
editable, or restart the run knowingly.

## 3. Reload

```bash
workhorse-<name> control reload --run <id> --at-boundary
```

This is a message on the run's control socket, not a restart. The run unwinds to
the outermost frame, re-imports the workflow package, and re-enters from the
checkpoint it just wrote — **same process, same pid, same root span, same run
dir, same wall-clock budget.** Restarting instead costs the in-flight turn and
opens a second run generation that groom reads as a failure.

Two choices to make deliberately:

- **`--at-boundary`, or cut the turn.** The default cuts the streaming turn
  within about a second, which is right when that turn *is* the waste you are
  stopping. Pass `--at-boundary` when the turn is doing legitimate work your fix
  does not change — throwing it away buys nothing.
- **`--core` only for the engine.** A plain reload replaces the workflow package
  and anything else editable. `workhorse` itself is on the stack doing the
  reload, so changing *it* needs `--core`, which costs a process image. Do not
  reach for it for a `workflows/` change.

## 4. Confirm it landed

An `--at-boundary` request is acknowledged (`{'ok': True, 'cut': False}`) and
then **held** until the current state finishes — so the acknowledgement is not
the reload. Watch the run's `events.jsonl` for the re-entry, and check the pid is
unchanged. Do not block on a long poll: if the turn is still streaming, say the
reload is pending and move on.

Full mechanics — what closes, what the spans are stamped with, what a `--core`
reload re-execs — are in stablemate's `workhorse/docs/RELOAD.md`.
