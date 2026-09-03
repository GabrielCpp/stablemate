---
name: stablemate-workhorse-operate
description: "Acting on a live workhorse run from the terminal — list the runs groom sees, resolve one to its `workflow` and `run_dir`, then `control` it over its socket: `status`, `reload` (pushed code), `switch-cli`, `switch-profile`, `questions`/`answer` (gates), and `inbox read`/`reply`. Load when asked to reload, restart, switch, answer, poke, or find a run — including one named from the groom dashboard. Reading *why* a run is stuck is groom-telemetry; groom's own architecture is groom; writing nodes is workhorse-engine."
metadata:
  generated_by: farrier
  source: library/skills/workhorse/operate/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-workhorse-operate/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [cli]
---

# Operating a live workhorse run

Load this skill when the ask is to **do something to a run that is already going**:
reload it onto pushed code, move it to another agent CLI or model profile, answer the
gate it is parked on, or just find where it is. The run is a process holding a control
socket in its run dir; groom already indexes every live one. Nothing here requires
searching a disk.

## The recipe

Three commands, in this order. From a stablemate checkout, prefix each with `uv run`.

```bash
groom status --json                                    # every live run: run_id, workflow, run_dir
workhorse-<workflow> control --run <run_dir> status    # proves this pid serves that dir
workhorse-<workflow> control --run <run_dir> reload [--at-boundary]
```

The first command's fields are the arguments of the next two:

| groom field | Feeds | Example |
|---|---|---|
| `workflow` | the console script name, `workhorse-<workflow>` | `research` → `workhorse-research` |
| `run_dir` | `control --run` / `inbox --run`, as the **absolute** path groom printed | `--run /srv/acme/.agents/runs/research-01hx…` |
| `run_id` | `groom status --run`, `groom logs --run`, `/api/run/{run_id}/…` | `--run research-01hx…` |

The human-readable `groom status` prints the same `control :` line per run, ready to
paste. `groom status --run <run_id> --json` narrows to one run when the id is known.

## The rules, and why each holds

- **Never search the filesystem for a run dir.** groom's `/api/live` is the index of
  every run that has heartbeat recently, with its `run_dir`. A `find` over the disk
  is slower, finds finished runs and stale copies, and still cannot say which one is
  live.
- **Pass `run_dir` as an absolute path.** A bare `--run <id>` resolves under
  `./.agents/runs` of the *current directory*, which is empty from any repo but the
  target's. That "no run dir" is not a missing run; it is the wrong cwd. (With groom
  up, `control` asks it before failing — but the absolute path never depends on that.)
- **`control status` before any mutating verb.** `launch.json`'s pid can belong to a
  process that has since died or been relaunched; `status` is answered by the socket,
  so it is the only proof of *who* serves the dir.
- **Change backend or models with `switch-cli` / `switch-profile`, never kill and
  resume.** Other sessions may be watching the run; a kill makes each watcher relaunch
  it, and three engines end up writing one run dir.
- **Reload, do not restart, to pick up pushed code.** A reload re-enters from the last
  checkpoint in the same process, pid, root span and wall-clock budget. A restart
  costs the in-flight turn and opens a second run generation groom reads as a failure.
- **groom down:** `groom status` says so on stderr and exits 1. Then point `control`
  at the target repo yourself: `control --runs-dir <target-repo>/.agents/runs …` with
  no `--run` takes the newest unfinished run there, and `--run <run_dir>` still works
  as an absolute path.

## Verbs

`workhorse-<workflow> control [--run RUN_DIR] [--gate|--text|--core|--at-boundary] <verb> [NAME]`

| Verb | Does | Reach for it when | Over HTTP (groom) |
|---|---|---|---|
| `status` | asks the socket what the process is doing: pid, node, whether a turn is streaming | first, always; and to confirm a reload landed | `GET /api/live?run=<run_id>` |
| `reload` | unwinds to the outermost frame, re-imports the workflow package, re-enters from the checkpoint | code under `workflows/` was pushed | — |
| `reload --at-boundary` | same, but held until the current state finishes | the streaming turn is legitimate work the fix does not change | — |
| `reload --core` | re-execs the process image so `workhorse` itself is replaced | the fix is in `workhorse/`, not a workflow | — |
| `questions` | lists the gates the run is parked on | the run shows an operator wait | `GET /api/run/{run_id}/outbox` |
| `answer` | posts the answer to the open gate (`--gate` picks one, `--text` inlines it) | the cause is fixed **and verified**, never to make it move | `POST /api/run/{run_id}/outbox` |
| `switch-cli NAME` | moves later turns to another agent backend | the current CLI is wedged or rate-limited | — |
| `switch-profile NAME` | moves later turns to another model profile | cost or capability needs a different model | — |
| `inbox read [--all]` | reads what the run left for its operator: a `failure` handoff, notes | on any wake, before diagnosing | `GET /api/run/{run_id}/inbox` |
| `inbox reply` | appends an operator message the run reads on its next wait | handing a decision back to the run | `POST /api/run/{run_id}/inbox` |

groom's own `POST /reload` is a different thing: it reloads the *container sidecar* in
the dev loop. It never reaches a run's control socket.

## Confirming a reload landed

An `--at-boundary` request is acknowledged immediately and then held, so the
acknowledgement is not the reload. Before sending it, check the run's interpreter
resolves your source tree and not a wheel in `site-packages` — that is how a reload
reports success over code it never loaded. After it, watch the run dir's
`events.jsonl` for the re-entry and confirm the pid did not change. The full four-step
procedure, with the source-tree check and the `--at-boundary` / `--core` choice, is
**[references/reloading-a-live-run.md](references/reloading-a-live-run.md)**; the
engine mechanics — what closes, what the spans are stamped with, what a `--core` reload
re-execs — are stablemate's `workhorse/docs/RELOAD.md`.

## What this skill is not

Reading *why* the run is where it is — the idle columns of `groom status`, `logs`,
`loops`, `cost`, `transcript` — is [[groom-telemetry]]. The dashboard, the sidecar and
the gate-file convention are [[groom]]. The code a reload pushes is written under
[[workhorse-engine]].
