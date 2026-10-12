---
type: concept
title: Operator inbox
---
# Operator inbox

The inbox is the channel a run uses to ask the operator something without stopping. The run
appends a message, keeps working, and reads the reply when it next looks. The file is
`inbox.jsonl` in the [run directory](run-directory.md), one JSON object per line.

Each message carries:

- `id`, the handle an operator replies to, such as `m1`.
- `body`, the question.
- `at`, the time the run asked.
- `reply` and `replied_at`, empty until the operator answers.

A message without a reply is outstanding. [`inbox read`](../workhorse.md#inbox) prints the
outstanding ones, and `inbox read --all` prints every one. `inbox reply ID TEXT` stores the reply
and the time, and a second reply to the same id replaces the first.

A gate is the blocking counterpart. When a state ends in `Await`, the run writes the question to
a gate file. The file opens with `STATUS: AWAITING_OPERATOR`, then a
`## Questions from the agent` heading, then the question. A second question on the same gate is
appended below the first, and the status is re-armed. The run parks until the status reads
anything else. An operator answers by editing the status, or with
[`control answer`](../workhorse.md#control), which sets `STATUS: ANSWERED` and appends the answer
text. While parked, the run still obeys control requests such as a reload.

The [answer the inbox](../flows/answer-inbox.md) journey walks the inbox end to end.

- code: `workhorse/workhorse/inbox.py::Message` @e2ad0fc21f23
- code: `workhorse/workhorse/inbox.py::append` @e2ad0fc21f23
- code: `workhorse/workhorse/gates.py::format_operator_gate` @5c0460a1fc89
- code: `workhorse/workhorse/gates.py::apply_answer` @5c0460a1fc89
- code: `workhorse/workhorse/pyflow/park.py::ask` @3bf2ebf15981
- code: `workhorse/workhorse/pyflow/park.py::wait_for_answer` @3bf2ebf15981
