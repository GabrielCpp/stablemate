story: none
date: 2026-11-21
elements: Run
sources: workhorse/workhorse/runner/process.py, workhorse/workhorse/runner/failure.py::TurnDeadlineExceeded

A node may declare a `deadline` in seconds. One attempt of its turn is cut once it has run that long, whether it is still
streaming or has gone quiet. Without a deadline nothing cuts a turn that keeps streaming, and only the silence bound ends
a quiet one.

The deadline is per attempt, so each call to the turn starts its own clock. The run multiplies it by the same
`timeout_scale` as the node's other budgets. A cut kills the turn's process group as a silence cut does. It is never
retried, compacted or reframed, and its session file is kept, so the turn can start again on the same conversation. The
cut reaches the calling state as `AgentTimeout` with `deadline_s` set. A silence cut reaches it with `deadline_s` empty, so
a state can tell which budget ran out.

A state that does not catch `AgentTimeout` ends the run as failed, so every call that passes a `deadline` catches it.

A node's `deadline` must be a finite number above zero. The call refuses any other value before the turn starts.
