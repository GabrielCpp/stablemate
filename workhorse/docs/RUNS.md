# The run directory — identity, resume, and what a run leaves behind

Every launch resolves to one run dir, and everything a run can be diagnosed from afterwards
is in it. This document is that contract in full: how the `(workflow, run-id)` pair is
derived and what each branch of "checkpoint or no checkpoint" does, the controller flags
that override it, and every file a run writes — the per-visit turn dirs, the session
manifest and the transcript captures. See [README.md](../README.md) for running a workflow,
and [RELOAD.md](RELOAD.md) for reaching a run that is still going.

## Resuming and run identity

The controller is **auto-resume-in-place** by default. Each `(workflow, run-id)`
pair maps to one stable run dir (`<workflow>-<run-id>`). When you don't pass
`--run-id`, the id defaults to a short **digest of `--params`** (e.g.
`okf-builder-p1c7e4b2a`), or to `default` when the run carries no params. This keeps
the resume contract while stopping distinct targets from colliding: a build for
`{service: report}` and one for `{service: api}` get different dirs automatically, so
the second never silently resumes the first (and drops its `--params`). Re-running
the *same* params re-derives the *same* id, so a crash/reboot/plain re-run still
resumes the existing checkpoint — which is why it's a digest, not a random id.
On start the controller looks for a checkpoint there:

- **No checkpoint** → start fresh from the workflow's `start` state in that dir, which
  is **emptied first**. A finished run leaves its per-node subdirectories behind, and
  since the id is derived from the params they are sitting in the next run's dir under
  the next run's name — a post-mortem then reads a clean run as having entered nodes it
  never reached, with nothing on disk to catch the misreading. **Copy the directory
  aside before relaunching if you want the previous run's artifacts**; an archive left
  *inside* `runs/` would be counted as a run by anything aggregating the tree.
- **Checkpoint present** → resume from the checkpointed state, restoring the frozen
  inputs, `ctx` and the state's parameters. Resume re-enters that state from the top,
  which is why idempotency — not merely determinism — is the contract a state body
  owes; see [Checkpoints and renaming](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#checkpoints-and-renaming).

This is what lets an unattended run survive a crash or reboot: relaunching the
same workflow continues where it left off. To start over, delete the run dir. To
keep independent runs of the same workflow side by side, pass distinct run ids.

**Ctrl-C is recorded, not silent.** An interrupt pauses the run the same way a crash
does — `terminal` stays `null` so the next launch resumes in place — but it also
stamps `run.json` with `interrupted_at`/`error` and appends an `error` event for the
node that was in flight. Without that, a stopped run and a run wedged in a node are
byte-identical on disk: the node's `enter` event has no `done` either way, and the
only record that a human hit Ctrl-C lives in the agent CLI's session transcript. The
stamp is cleared by the resume that follows it.

Controller flags (passed to `workhorse`; `--resume-*` are manual overrides
of the auto behavior above):

| Flag | Purpose |
|---|---|
| `--run-id <id>` | Name the stable run dir (`<workflow>-<id>`); default: a digest of `--params`, else `default` |
| `--resume-run <path-or-name>` | Resume a specific run dir from its checkpoint |
| `--resume-latest` | Resume the most recent unfinished run under `--runs-dir` |
| `--params '<json>'` / `--params-file <path>` | Set the workflow's declared inputs on a fresh start (also keys the default run dir) |

"Survives reboot" therefore covers both the *work products* (commits, sessions,
artifacts) **and** position in the machine — an interrupted run auto-resumes mid-flight.

## Run artifacts

Each workflow execution writes a timestamped directory:

```
runs/
└── <workflow-name>-<timestamp>-<id>/
    ├── run.json                  # start/end time, terminal state, interrupt stamp
    ├── context.json              # final context snapshot
    ├── sessions.jsonl            # one line per agent turn: the node, its visit key, and its CLI session
    ├── turns/                    # one directory per agent-node visit, keyed <gen>-<seq>-<node>,
    │                             # holding that visit's own copy of the files below
    ├── transcripts/              # one capture per agent turn, same key + the session id:
    │                             # <gen>-<seq>-<node>__<session-id>.{jsonl,d,tee.jsonl,meta.json}
    └── <step-id>/                # the LATEST visit of this step
        ├── prompt.md             # rendered prompt, written before agent invocation
        ├── output.json           # extracted JSON outputs
        └── context_after.json    # context state after this step
```

Artifacts are written under `--runs-dir` (default `<cwd>/.agents/runs`). Before
each agent turn, workhorse writes the rendered `prompt.md` and logs only that path
so failed or interrupted nodes remain inspectable without dumping variables. A
prompt above 96 KiB also uses this artifact for delivery: OpenCode and Copilot attach
it natively, Cline receives a short instruction to read it, and stdin-native Claude
and Codex continue receiving the complete prompt on stdin. This keeps large prompt
content out of the subprocess argument vector and below operating-system argv limits.
A `<step-id>/` directory is overwritten on every visit, so a node in a loop leaves only
its last prompt there; `turns/` keeps the earlier ones, which are what a node that
re-decided the same thing five times has to be diagnosed from. The
Docker harness redirects artifacts to a persistent volume instead — see
[docs/DOCKER.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/DOCKER.md).

`prompt.md` and `output.json` capture a step's *input* and *final* answer, not the
agent's step-by-step reasoning and tool calls in between — that transcript lives in
the agent CLI's own session store, keyed by session id. `sessions.jsonl` records the
`node → session_id` map for every agent turn so you can recover it afterward (e.g.
`opencode export <session_id>`). It is an append-only manifest because the live
`.session_id` file holds only the *current* node's session; a node can appear more
than once (loop revisits, compact/reframe within a node), so the mapping is
`node → sessions` and consumers dedup on read. With telemetry on the same
session id is also set as the `session.id` attribute on the agent-turn span.

That store is on one host and the CLI prunes it whenever it likes, so the run also keeps
its own copy: each turn is captured into `transcripts/` under the same visit key. Workhorse
prefers a resolvable backend session store; for OpenCode it invokes the public
`opencode export <session_id>` command, whose JSON includes reasoning, tool, file, patch,
snapshot and subtask parts; otherwise it keeps a redacted tee of the live stream. OpenCode
runs also enable `--thinking`, so the tee still includes completed reasoning parts while the
full export is unavailable. An OpenCode export can remain incomplete briefly after its process
exits; when that happens, the next turn retries the settled session and promotes the provisional
tee to the full export. Every capture's `.meta.json` records its source, bytes, the head observed
at the time, and whether the per-turn cap truncated it.
Bounds are `WORKHORSE_CAPTURE_TRANSCRIPTS` (default on) and
`WORKHORSE_TRANSCRIPT_MAX_BYTES` (default 32 MiB per turn).
