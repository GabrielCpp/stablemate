# runner

One agent turn: the process that runs it, how its end is classified, and the fail-soft recovery ladder around it. Each supported agent CLI is a backend under `backends/`.

## Map

- `backends/`: the agent-CLI port and one adapter per supported CLI.
- `caps.py`: how long to wait out a scheduled-reset cap, and the visible sleep through it.
- `extract.py`: recovering a node's declared outputs from an agent's free-form reply.
- `failure.py`: how a finished turn is classified: the failure markers, the typed errors and the one classifier.
- `ladder.py`: the recovery ladder of retry, cap wait, compact, reframe and stop, and the live run's model profile.
- `process.py`: spawning the agent CLI in its own process group, the silence watchdog and the stream loop.
- `redact.py`: removing known secret values and secret shapes from CLI output before it is stored.
- `reframe.py`: the corrective prompts the ladder sends in place of the node's own.
- `spec.py`: what the runner is handed for one turn: the prompt, its arguments and the expected outputs.
- `transcript.py`: keeping each turn's session transcript in the run dir beside its prompt.
- `turn_record.py`: `turn.json`, what one turn started with, enough to start it again.
- `usage.py`: each CLI's token and cost report mapped onto one canonical shape.
- `waits.py`: the cumulative recovery-wait budget one agent-node visit may spend.
- `worktree_guard.py`: the `git` shim that stops an agent turn from discarding uncommitted work it does not own.
