# Pushing a fix into a run that is already going (`control reload`)

The failure this exists for is not a crash. It is watching a healthy run spend real money
on a flow you have already fixed on disk: a prompt that sends the agent in circles, a gate
handing back the same worklist every pass. Stopping and restarting the run costs the
in-flight turn, opens a second run generation, and reads in groom exactly like the failure
it is not.

This document is the full mechanics — what a reload cuts, what it re-imports, what the
spans are stamped with, and the three sibling commands that reach a live run over the same
channel (`status`, `switch-cli`, `switch-profile`). The short version is in
[README.md](../README.md#reaching-a-run-that-is-already-going).

For the recovery ladder whose waits a reload interrupts, see
[GUARDRAILS.md](GUARDRAILS.md). For what the stamped spans mean to a collector, see
[TELEMETRY.md](TELEMETRY.md).

## Reloading

```bash
workhorse-coder control --run <id> reload                 # cut the turn, re-enter on the pushed code
workhorse-coder control --run <id> reload --at-boundary   # let the turn land first
workhorse-coder control --run <id> reload --core          # …and replace workhorse itself
```

With no `--run`, the most recent unfinished run under `--runs-dir` is taken, and the
command prints which one, whether its pid answers, and the state it last checkpointed.
It does not block on the reload landing.

What the run then does:

1. **The turn is cut, within about a second.** A turn can last hours, so waiting for the
   next state boundary would deliver hours of the exact waste you are stopping.
   `--at-boundary` is the opt-out, for a turn that is 95% through expensive work and is
   *not* the broken part.
2. **The turn's span closes with the usage it really accrued**, and every scope above it
   closes on the unwind, each one stamped `workhorse.cut=reload`. A reload costs no
   dangling spans — that is what keeps it from looking like an abort — and the stamp is
   what keeps the closed ones from being read as *completed* work: groom excludes a cut
   visit from its churn rule, so pushing five fixes into a broken flow does not page as
   the loop you were breaking. The reload itself is a log record, so `groom logs` shows
   which state was re-entered and when.
3. **The cut consumes no recovery budget.** Not a retry, not a reframe, not a compaction
   attempt, and no backoff: the turn was interrupted on purpose.
4. **The pushed code is re-imported from disk** and the run re-enters the checkpoint the
   state wrote on entry — same process, same run dir, same root span, same wall-clock
   budget. Not a new run.

## Reaching a run that is asleep

The recovery ladder's waits — a spending-cap
window, a transient backoff at its 30-minute cap, the pause before a reframe — go through
the same channel, so a reload ends them at once instead of at the end of a window that can
be days out. Those are the waits an operator most wants to reach into (the cap is often
*why* you are switching something), and until the channel existed they were exactly the
ones nothing polled. A request the wait declines — `--at-boundary`, or an action this run
does not know — leaves the window intact: it is answered and held, not obeyed, so being
delivered can never shorten a six-day sleep. Nothing is cut in these cases, since there is
no turn in flight; the ladder unwinds and the node re-enters on the pushed code.

## Asking where a run is (`control status`)

The same channel answers a question as well as carrying an instruction:

```bash
workhorse-coder control --run <id> status
```

Everything it reports — the workflow, the run id, the pid, the state and flow the last
checkpoint named — is also on disk, and reading the disk is what the command falls back to.
What only a reply can establish is that *this process is still serving this run dir*: a pid
in `run.json` outlives the process that wrote it, and a checkpoint says where a run got to,
not whether anything is still there. So a `status` that answers is liveness, and one that
does not is not an error — a script node with no wait in it reads the channel only between
turns, and the command says which of the two it saw rather than smoothing them together.

`status` is answered *below* every wait rather than by one, which is what makes it safe to
ask of the run most worth asking about: a run six days into a cap window is answered from
inside that window, and the window is not shortened by having been asked. When the run is
parked on an operator gate, `status` also names it: `waiting_on` carries the gate file's
path and `wait_kind` what sort of wait it is.

## Answering an operator gate (`control questions` / `control answer`)

An `Await(kind="operator")` parks the run on a gate file until someone answers. The same
channel that carries a reload carries that conversation, so the operator (or groom on
their behalf) talks to the run instead of to its files:

```bash
workhorse-coder control --run <id> questions                    # what is this run asking?
workhorse-coder control --run <id> answer --text "ship it"      # answer the gate it waits on
workhorse-coder control --run <id> answer --gate /abs/path.md   # …naming the gate explicitly
```

`questions` is answered in-band under every wait, like `status` — it never ends one. The
reply is `{"ok": true, "questions": [{"path", "question", "kind", "since"}]}`, with the
question text read live from the gate file, and an empty list when the run is not blocked
on a gate.

`answer` is the one verb that *ends* a wait, so only the operator wait accepts it; at any
other wait it is refused with `{"ok": false, "error": "this run is not blocked on an
operator gate right now"}` and the window is left intact. At the gate itself:

- a `--gate` path that is not the gate this run is waiting on is refused by name —
  `{"ok": false, "error": "this run is waiting on <path>, not <that>"}` — and the wait
  continues; omitted, the answer lands on whichever gate the run is parked on;
- a gate already answered is refused with `{"ok": false, "error": "already answered"}`,
  so a second answer can never overwrite the first;
- otherwise the run **persists first** — it writes the answer into its own gate file
  (`STATUS: ANSWERED` plus the operator's prose) — and only then replies
  `{"ok": true, "path": ...}`. The file is the durable record: if the process dies right
  after replying, the resume reads the answered gate and proceeds.

The socket is the prompt path, not the only one. The wait keeps re-reading the gate file
every `WORKHORSE_AWAIT_POLL_S` (15s), so an answer written to the file by hand — or by a
groom falling back because nothing was listening — still lands; the socket only makes it
immediate. Symmetrically, a `reload` or `switch-cli` delivered to a parked operator wait
cuts the wait *now* rather than after the answer: the checkpoint already carries
`waiting_on`, so the resume re-arms the same wait on the same gate and the run parks
again, having lost nothing.

## Moving a run onto another agent CLI (`control switch-cli`)

When the CLI a run is driving is the thing that is broken — a harness wedged mid-turn, a provider outage that
outlasts the retry ladder — the fix is not new code but a different agent:

```bash
workhorse-coder control --run <id> switch-cli claude
```

It travels as a `--core` reload carrying the CLI name, and it is core whether or not
`--core` was typed: the backend is bound once at the process edge from `--cli` and handed
to the run, so re-importing the workflow package could not move a live run onto another
agent however plainly the request asked. What comes back is the same run re-entering the
same checkpointed state, with `--cli <name>` appended to the resume argv — the one thing a
resume cannot read off the checkpoint, because it was never in it.

## Moving a run onto another set of models (`control switch-profile`)

The other axis — the run is fine, it is just spending more than it is worth — needs no
reload at all:

```bash
workhorse-coder control --run <id> switch-profile cheap
```

The runner re-loads and re-narrows the config on **every** turn, so a new profile name
reaches the next turn by itself. It applies at the next node boundary in the same process:
same pid, same root span, same run dir, same wall-clock budget — so `workhorse.profile` on
the root span names the profile the run *finished* on, the honest single answer for a run
that was moved mid-flight.

`run.json` still records the profile the run was **launched** with, which is why a later
`--core` reload (a `switch-cli`, say) carries the live profile in its re-exec argv: without
that the new image would read the record and silently resolve from the set the operator
switched away from.

The checkpoint is written *before* the state runs, so nothing durable is lost. If the
pushed code renamed or retyped a workflow field the checkpoint still holds, the run stops
at that checkpoint with pydantic naming the field, which is the honest outcome of an
incompatible edit — the stored value is meaningful, and mapping it onto the new contract
is a judgement only you can make.

A field the pushed code **deleted** is not that case, and is dropped rather than fatal:
nothing left in the workflow can read it, so carrying the value forward and discarding it
are the same run. The reload logs the names it dropped. Failing there would be worse than
useless, because `--resume-run` rebuilds the workflow from the same stored `inputs` — a
run killed by a deletion would hit the identical error on every resume after it, and the
only recovery would be hand-editing `inputs` out of `checkpoint.json`. A week-long run
should not be lost to a field removal that costs it nothing.

The relaxation is for **checkpoints only**. An unknown key in `--params` on a fresh run is
still rejected by name: there it is a typo you just typed, and catching it is the point.

## What "the pushed code" covers

It is wider than the workflow package, because a defect
usually is. A workflow is several distributions deep — the state machine calls a doc-graph
validator, a shared kit — and a reload that replaced only the entry package would
re-import the workflow against the *stale* copy of the library you just fixed, then log a
successful reload over code that never changed. So the rule is **replace the working tree,
keep the environment**: the workflow's own package always, plus every other top-level
package whose module file lies outside the interpreter's stdlib and site-packages — i.e.
an editable or source-tree install, which is the only kind you can fix while a run holds
it open. A wheel in site-packages is left alone, and so is anything with a live frame on
the stack. That line is the safety invariant rather than a guess about which packages
matter: workhorse's own dependencies are environment-installed, so keeping the environment
is what guarantees no surviving frame is left holding a class whose module was swapped
underneath it. The reload log record names the packages it replaced, so a reload is
something you can audit rather than take on faith:

```
[workhorse] reload: re-entering 'implement' on the pushed code (replaced: workhorse_workflows, ostler)
```

A dependency installed as a wheel therefore needs `--core` (or a plain resume) to be
picked up — reinstalling it is an environment change, not a working-tree one.

`--core` asks for workhorse's own modules too, which cannot be replaced from a frame
executing them — the driver, the ladder and the stream loop are all on that frame — so it
costs a new process image. Everything above still happens first (the turn is cut, its span
closes with its usage, the scopes close on the unwind, the run is stamped `reload` and
flushed), and only then does the run `os.execv` itself as
`run --resume-run <dir>`: same pid, no supervisor, identical in a container and on a
laptop. The price of the new image is a new root span and a new resume generation, so the
seconds between the two show up as a resume gap where a workflow-only reload costs
nothing — which is why `--core` is something you ask for rather than the default. If the
exec cannot happen at all, the run exits `3`, the reserved reload code: under
`supervisor.py` that is a restart (with the source re-staged first, which is also how a
core that has to be *staged* rather than exec'd is picked up), and without one it is a
stop over a run dir that is still resumable by hand.
