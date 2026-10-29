---
type: concept
title: Run control
---
# Run control

An operator steers a run that is already going without killing it. A live run listens on
`control.sock` in its [run directory](run-directory.md). The [`control`](../workhorse.md#control)
command sends it one request and prints the reply. When the socket path is longer than 100
characters, the run listens on a short path elsewhere and writes that path into
`control.sock.path`.

Every operator command picks its run the same way. `--run` takes a run id, a run-directory name
or a path. A name that matches no local directory is asked of the groom dashboard, at
`$GROOM_URL`, default `http://127.0.0.1:8787`. Without `--run`, the command takes the newest run under `--runs-dir`
that has not finished.

The verbs split by whether the run must be live:

- **Live verbs** talk over the socket. `status` asks the run where it is. `questions` lists the
  gates it is parked on. `answer` writes an answer into the gate, as in the
  [operator inbox](operator-inbox.md). `stop` interrupts the run and keeps its checkpoint. `reload`
  re-imports the workflow package and re-enters the checkpoint, and `--core` reloads workhorse
  too. `switch-cli` is a reload onto another agent CLI. `switch-profile` changes the models the
  next turn resolves, as in [profiles and config](profiles-and-config.md).
- **Offline verbs** read the run directory. `rewind` moves a stopped run's checkpoint to the state
  `--to` names. `resume` relaunches a stopped run detached from its recorded command line, in its own
  systemd user scope where one is available so it survives the caller exiting, and waits until it
  serves. `status --params` prints the checkpoint from disk, so it answers for a
  live run and a stopped one alike. A run [dispatched into a worktree](run-launch.md) also gets a
  `worktree` block: its `path`, `branch` and `base`, and the `outcome` its ending recorded, `null`
  while the run has not ended. A reload or a rewind on such a run does not end it, so the run stays
  in that worktree until it reaches a terminal state.

A reload or a switch cuts the streaming turn by default. `--at-boundary` lets the turn finish and
acts at the next state entry. When a live verb finds no listener, the command says whether the
recorded process is still alive.

A rewind validates before it writes. The target state must exist in the flow the checkpoint
names. The carried params must fit the state's signature. `--param` and `--param-from-turn` set
params, and `--keep` limits which checkpoint params carry over. The rewind copies the old
checkpoint to `checkpoint.rewound-<UTC stamp>.json`, clears the gate the run waited on, sets aside
each sub-flow the rewound visit left unfinished, and logs a `rewind` event. The
[inspect a stopped run](../flows/inspect-stopped-run.md) journey reads a run's checkpoint.

- code: `workhorse/workhorse/control.py::SocketChannel` @074fb59a453c
- code: `workhorse/workhorse/control.py::listening` @ef74d8823ed3
- code: `workhorse/workhorse/control.py::send` @74b8703a44d6
- code: `workhorse/workhorse/cli/target.py::groom_live_run` @9eedeca9ae29
- code: `workhorse/workhorse/cli/offline.py::refuse_if_running` @e01fed3a3bf7
- code: `workhorse/workhorse/cli/offline.py::wait_gone` @a2c3f6470927
- code: `workhorse/workhorse/rewind.py::rewind` @71550797f2a2
- code: `workhorse/workhorse/rewind.py::RewindError` @3c82ae1b32fe
- code: `workhorse/workhorse/reload.py::ReloadRequested` @efeb2f44f6b2
- code: `workhorse/workhorse/reload.py::cut_requested` @21ec9269d306
- code: `workhorse/docs/RELOAD.md` @3204f97e0a12
