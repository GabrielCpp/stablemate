---
type: concept
slug: coder-dev-package
title: Coder dev package
---
# Coder dev package

The `dev` machine builds one story with one owner and checks the result. It is a sub-flow
entered by the Coder main flow when a story is ready for implementation, and can also be run
directly with `workhorse-coder run dev`.

The owner works the story in three phase turns on one conversation, as
[coder dev phase turns](coder-dev-phase-turns.md) describes. `Dev.plan` writes the plan,
`Dev.build` builds it, and `Dev.review` reviews the diff and answers every finding in the story's
answer file. A story QA sent back starts at `Dev.review`, with QA's findings in their own section.
The flow around the turns is deterministic. It records the plan, runs the declared service gates,
settles the findings against the answers, and checks that the story left nothing uncommitted. A
failed check goes back to the review phase as a report for another repair lap. A spent lap budget
escalates to an operator gate.

The dev phases leave the book alone. The docs phase merges the story into the book after review,
and QA reads its obligations from that merge. The story's opening brief says so, so a repo
instruction that the book changes with the code does not send the plan, build and review turns
into the same merge the docs phase then does again.

- code: `workflows/src/workhorse_workflows/coder/dev/flow.py` @57566dc621c3
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev` @57566dc621c3
- code: `workflows/src/workhorse_workflows/coder/dev/prompts/_dev-scope.md` @72d37ceba409
- rule: the plan, build and review turns write, stamp and doctor nothing under the book's services root, because the docs phase owns the story's book merge
- rule: a copy the story adds of code the tree already has is the story's to extract to one owner, and a copy that predates the story is an `extract-module` follow-up
- rule: a copy across two builds is extracted to a library the workspace lists without asking when a standing decision covers it, or when the workspace exists and every build and deploy stays as it was, because nothing about how the code ships changes
- rule: a copy across two builds that needs a new workspace or a wider build blocks with one concrete library proposed, and the turn that receives the operator's answer writes it to the run's standing decisions before building, so the next story follows it without asking
- rule: a Reuse finding is declined only as a coincidence, with one reason per copy, because a copy left in place to save the slice work drifts from the code it repeats
- prefers: one book merge per story, in the docs phase, over a merge in the build that the docs phase repeats, because the duplicate cost a quarter to a third of each build turn
- tests: `workflows/tests/coder/dev/test_flow.py`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_opening_brief_leaves_the_book_merge_to_the_docs_phase`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_opening_brief_records_an_operator_answer_where_the_resolver_reads_decisions`
- detail: [coder dev flow](../flows/coder-dev.md)

The dev package operates against a docs repository carrying one epic with its `## Stories`
listing and one authored story, and against a workspace file naming the code repositories the
plan dispatches into. The `docs` and `workspace` test fixtures stand those inputs up. `docs`
builds the docs repo. `workspace` builds two real git repositories and a home config whose
`acme` workspace names them, as an operator ships one. The gates the
flow runs therefore see the same artifacts the production flow does.

## Methods

### plan_arg
- sig: `plan_arg(result: DevResult) -> dict[str, Any]`
- does: keeps only the structural half of the owner's reply that `record_plan` takes
- verify: count(subject="plan structure fields", equals=5)
- returns: the services, implementation order, shared packages, verification setup and fixtures
- verify: json_path(path="$.services", equals="example services")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::plan_arg` @e53511844b8a

### report_text
- sig: `report_text(report: FailureReport) -> str`
- does: renders a gate failure as the markdown the next owner turn reads
- verify: count(subject="rendered gate reports", equals=1)
- does: names the gate, then the command and directory when they are known, then each finding with its repair
- verify: count(subject="rendered report findings", equals=1)
- does: appends the gate output in a fence when it is not blank
- verify: count(subject="fenced report outputs", equals=1)
- returns: a markdown string starting with `Gate: <source>`
- verify: json_path(path="$.report", matches="^Gate: ")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::report_text` @e53511844b8a

### findings_text
- sig: `findings_text(items: Sequence[wl.WorkItem]) -> str`
- does: renders one `###` section per open finding item, with its source, target, issue and repair
- verify: count(subject="rendered finding sections", equals=1)
- does: shows `(no target)` for a finding with no target
- verify: count(subject="targetless finding sections", equals=1)
- returns: the sections joined by blank lines
- verify: json_path(path="$.findings", equals="example findings")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::findings_text` @e53511844b8a

### rejected_text
- sig: `rejected_text(rejected: dict[str, str], errors: Sequence[str]) -> str`
- does: lists each rejected answer id with the reason its evidence did not hold
- verify: count(subject="rejected answer lines", equals=1)
- does: appends each settlement error as its own bullet
- verify: count(subject="settlement error lines", equals=1)
- returns: one bullet per line
- verify: json_path(path="$.rejected", equals="example rejected")
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::rejected_text` @e53511844b8a

### unadvised_text
- sig: `unadvised_text(departures: Sequence[Departure]) -> str`
- does: renders the build departures that carry no advisor answer as the report the build's next turn reads
- verify: json_path(path="$.report", matches="^Departures: ")
- returns: a `Departures:` line asking for the advisor's answer, then one bullet per departure's change
- verify: count(subject="unadvised departure lines", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::unadvised_text` @e53511844b8a

### unconsulted_text
- sig: `unconsulted_text(ids: Sequence[str]) -> str`
- does: renders the declined findings with no consult on file as the report the review's next turn reads
- verify: json_path(path="$.report", matches="^Consults: ")
- returns: a `Consults:` sentence naming each finding id and asking for the advisor's answer before the decline stands
- verify: count(subject="unconsulted decline reports", equals=1)
- code: `workflows/src/workhorse_workflows/coder/dev/report.py::unconsulted_text` @e53511844b8a
