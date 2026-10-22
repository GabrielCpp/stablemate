---
type: concept
title: Agent turns
---
# Agent turns

An agent turn is one call to an agent CLI on behalf of one node. The engine renders the node's
prompt, writes it to `prompt.md` before the call so a failed node stays inspectable, starts the
CLI, and validates the reply into the node's declared output type. The CLI itself is chosen as
[agent backends](agent-backends.md) describes.

The classifier sorts a finished turn in this order, and the first match wins:

1. A usage or spending cap. The run waits it out.
2. A silence timeout whose diagnostics look like a provider outage. The run retries.
3. A silence timeout. The run retries with a prompt that says the last attempt went quiet.
4. A context window overflow. The run compacts the session.
5. A non-zero exit code. The run retries when the diagnostics look transient.
6. No reply text after spending generation tokens. The run treats it as an overflow.
7. No reply text at all. The run retries.

Diagnostics look transient when they carry a status of 429, 500, 502, 503 or 504, or a known
outage marker.

The recovery ladder runs retry, then cap wait, then compact, then reframe, then stop. A reply
that does not parse is sent back with the parse error, up to two times by default. A failed call
backs off from 15 seconds up to 30 minutes, up to 60 times. A cap with a stated reset time sleeps
until that time plus a two-minute margin. A cap with no readable reset time sleeps ten minutes.
One node visit has a separate sleep budget for cap waits, retry waits, reframe waits and exec
retries. A wait that would overrun its budget fails the node with a `wait budget exhausted`
message instead of sleeping. The
settings come from `AGENT_*` environment variables, which a run reads once when it starts.

The agent CLI's own output passes through a redactor before it reaches a transcript, a checkpoint
or telemetry. The redactor masks the values of known secrets and the recognisable shapes of
others. The run writes `turn.json` with what the turn was started with, and keeps the transcript
beside the prompt. While the turn runs, its events are also written as Agent Client Protocol
updates to `transcripts/live/<slug>.jsonl`, and that file is filed beside the turn's capture when
the turn ends, so a dashboard can follow a turn before it finishes. In a tree other runs share, the turn's git commands that would discard their
uncommitted work are refused. These are `stash`, `checkout`, `switch`, `restore` of the working
tree, a hard, merge or keep `reset`, and a `clean` that is not a dry run.

The [`replay`](../workhorse.md#replay) command runs one recorded turn again from the tree it
started on, a given number of times, to size a prompt variant. The
[size a replay variant](../flows/size-replay-variant.md) journey shows its refusal of a turn whose
tree has moved.

- code: `workhorse/workhorse/runner/ladder.py::AgentRunner` @d22216e866b4
- code: `workhorse/workhorse/runner/turn_record.py::TurnRecord` @50530978b759
- code: `workhorse/workhorse/runner/spec.py::AgentNode` @ea80f1fc2fed
- code: `workhorse/workhorse/runner/failure.py::classify_turn` @67f43d6fb9ef
- code: `workhorse/workhorse/runner/failure.py::is_transient` @67f43d6fb9ef
- code: `workhorse/workhorse/runner/caps.py::cap_delay_seconds` @57869724201e
- code: `workhorse/workhorse/runner/caps.py::parse_reset_seconds` @57869724201e
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget` @d0c5459fe618
- code: `workhorse/workhorse/runner/reframe.py::retry_prompt` @d40203f18c9b
- code: `workhorse/workhorse/runner/extract.py::extract_outputs` @92cafcbdca28
- code: `workhorse/workhorse/runner/process.py::ProcessSupervisor` @82335d356999
- code: `workhorse/workhorse/runner/transcript.py::capture` @761e9ee51dc0
- code: `workhorse/workhorse/runner/usage.py::TurnUsage` @ebb8fd7db412
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor` @40448a232adc
- code: `workhorse/workhorse/runner/worktree_guard.py::refusal` @0762312c18d4
- code: `workhorse/workhorse/runner/__init__.py` @e3b0c44298fc
- code: `workhorse/workhorse/runner/README.md` @8284b6d47f86
- code: `workhorse/docs/GUARDRAILS.md` @519e2e8dce08
