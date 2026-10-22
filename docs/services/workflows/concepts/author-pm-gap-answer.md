---
type: concept
slug: author-pm-gap-answer
title: Author PM gap answer
---
# Author PM gap answer

The `GapAnswer` flow answers a writer's product question. A writer that cannot go on without a product decision returns `blocked` with its question. The stage hands that question to this flow, and the writer retries with the answer as its note.

The product manager reads the milestone, its [ledger](../formats/pm-ledger.md) and the epics, and answers from them. An answer is appended to the ledger, so every later turn reads it. When only a change to the milestone could settle the question, the reply is an amendment. The flow then waits on the run's operator file, records the operator's text in the ledger as a human answer, and returns it as the note.

Each question runs in a fresh session. A stage asks at most twice (`MAX_ANSWERS`). A third question ends the stage as blocked, and the Author flow asks the operator.

- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer` @e0c54f0a14b1
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer.start` @e0c54f0a14b1
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer.record_human` @e0c54f0a14b1
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::MAX_ANSWERS` @e0c54f0a14b1
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::accepts` @e0c54f0a14b1
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::note_for` @e0c54f0a14b1
- code: `workflows/src/workhorse_workflows/author/pm/nodes/ledger.py::append_ledger` @b6b6f49ef343
- tests: `workflows/tests/author/pm/test_pm.py::test_a_pm_answer_is_kept_in_the_ledger`
- tests: `workflows/tests/author/pm/test_pm.py::test_an_amendment_waits_on_the_operator_and_records_the_human_answer`
- detail: [Author PM review](author-pm-review.md)
- detail: [PM ledger](../formats/pm-ledger.md)

## Fields

### question
- type: string
- default: empty
- required: true
- semantics: the writer's blocking question
- verify: json_path(path="$.question", equals="Which sign-in method comes first?")
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer` @e0c54f0a14b1

### asker
- type: string
- default: empty
- required: false
- semantics: the stage that asked, recorded as the ledger entry's heading
- verify: json_path(path="$.asker", equals="story-split")
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer` @e0c54f0a14b1

## Methods

### start
- sig: `start() -> Done | Await`
- does: refuses an empty question before any agent turn runs
- verify: json_path(path="$.failure_class", equals="gap-answer-missing-question")
- does: asks a high-power agent for an answer or an amendment
- verify: count(subject="PM answer turns", equals=1)
- does: appends an answer to the ledger and returns it with the retry note
- verify: created(subject="grills/pm.md")
- does: for an amendment, waits on the operator file with the question and the reason
- verify: json_path(path="$.await", matches="needs a product decision")
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer.start` @e0c54f0a14b1

### record_human
- sig: `record_human(asked: str) -> Done`
- does: reads the operator's text below the question and appends it to the ledger as a human answer
- verify: json_path(path="$.by", equals="human")
- returns: returns the operator's answer with the retry note
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::GapAnswer.record_human` @e0c54f0a14b1

### accepts
- sig: `accepts(answer: Answer) -> None`
- does: refuses an answered reply with no text and an amendment with no reason
- verify: json_path(path="$.error", matches="non-empty")
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::accepts` @e0c54f0a14b1

### note_for
- sig: `note_for(question: str, answer: str, by: str) -> str`
- does: renders the note a writer is retried with, as `You asked: ...` and `The <by> answers: ...`
- verify: json_path(path="$.note", matches="^You asked: ")
- code: `workflows/src/workhorse_workflows/author/pm/answer.py::note_for` @e0c54f0a14b1
