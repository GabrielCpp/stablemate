---
type: concept
slug: author-finalize-subflow
title: Author finalize subflow
---
# Author finalize subflow

`Finalize` validates and delivers an already-authored roadmap. It never performs another authoring
agent turn: it resolves the epic-mode configuration, checks for silently dropped planning scope,
checks whole-graph integrity, validates the roadmap's single milestone, validates the produced
artifacts again, marks the roadmap authored, and commits the authored documents on the current
branch. The gate implementations are described in the [author artifact gates](author-artifact-gates.md)
module concept. Reconciliation and integrity each allow at most two automatic resolver passes; milestone
validation uses the integrity cap. Human mode bypasses automatic resolution. Validation failures
are either routed through bounded automatic resolution or parked at an operator context file; a
terminal artifact or milestone failure commits an incomplete marker and raises instead of reporting
success. A passing or explicitly skipped gate is the only path to the next gate. The module exports
the two resolution limits and an unbounded timeout used only for resolver turns.

- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize`
- tests: `workflows/tests/author/finalize/test_flow.py::test_finalizes_with_one_commit_on_the_current_branch`
- tests: `workflows/tests/author/finalize/test_flow.py::test_terminal_validation_commits_incomplete_then_fails`
- detail: [author roadmap intake](../flows/author-roadmap-intake.md)

## Fields

### operator_mode
- type: `str`
- default: `"auto"`
- required: false
- semantics: selects automatic resolution or direct human operator gates
- verify: json_path(path="$.operator_mode", matches="^(auto|human)$")
- semantics: accepts only `auto` and `human`
- verify: json_path(path="$.operator_mode", matches="^(auto|human)$")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.operator_mode`

### MAX_RECONCILE_RESOLVES
- type: `int`
- default: `2`
- required: true
- semantics: maximum automatic reconciliation resolver passes before awaiting an operator
- verify: json_path(path="$.max_reconcile_resolves", equals=2)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::MAX_RECONCILE_RESOLVES`

### MAX_INTEGRITY_RESOLVES
- type: `int`
- default: `2`
- required: true
- semantics: maximum automatic integrity and milestone resolver passes before awaiting an operator
- verify: json_path(path="$.max_integrity_resolves", equals=2)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::MAX_INTEGRITY_RESOLVES`

### UNBOUNDED
- type: `float`
- default: `float("inf")`
- required: true
- semantics: timeout passed to resolver agent turns so the flow cap does not truncate diagnosis
- verify: json_path(path="$.resolver_timeout", equals="inf")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::UNBOUNDED`

## Methods

### setup
- sig: `setup() -> RunContext`
- does: loads author configuration in epic mode
- verify: count(subject="finalize configuration loads", equals=1)
- does: stores the resolved configuration as the flow context
- verify: count(subject="finalize run contexts", equals=1)
- returns: returns the resolved [run context](../author-config.md)
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the roadmap filename stem as `work_id`
- verify: json_path(path="$.work_id", matches=".+")
- does: reports progress as validating and delivering the authored roadmap
- verify: json_path(path="$.progress", equals="validating and delivering authored roadmap")
- returns: returns the work identifier and progress labels
- verify: count(subject="finalize label mappings", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.labels`

### _context
- sig: `_context() -> str`
- does: resolves the configured author operator context path relative to the repository root
- verify: json_path(path="$.context_path", matches=".+")
- returns: returns the path used by finalization's operator gates
- verify: count(subject="finalize operator context paths", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._context`

### _context_path
- sig: `_context_path() -> Path`
- does: joins the repository root to the configured author operator context path
- verify: json_path(path="$.context_path", matches=".+")
- returns: returns the absolute operator context file path
- verify: count(subject="absolute finalize context paths", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._context_path`

### _resolve_integrity
- sig: `_resolve_integrity(notes: str) -> OperatorResolution`
- does: asks the high-power integrity resolver to diagnose the supplied validation notes
- verify: count(subject="finalize integrity resolver turns", equals=1)
- does: passes the author context path, configured epics directory, and validation notes to the resolver
- verify: count(subject="finalize resolver input envelopes", equals=1)
- does: leaves the resolver turn unbounded so a diagnostic response is not cut off by the flow's gate caps
- verify: count(subject="unbounded finalize resolver turns", equals=1)
- returns: returns the resolver's operator resolution
- verify: json_path(path="$.decision", equals="answered")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity`

### _fail_validation
- sig: `_fail_validation(heading: str, errors: str) -> None`
- does: commits an incomplete roadmap marker before terminating failed final validation
- verify: count(subject="incomplete finalize commits", equals=1)
- does: raises workflow failure with the validation heading and errors
- verify: count(subject="terminal finalize validation failures", equals=1)
- raises: `WorkflowFailed` after the incomplete commit is attempted
- verify: count(subject="workflow failures after incomplete finalize commits", equals=1)
- returns: returns no value when validation does not fail before the commit call
- verify: count(subject="successful _fail_validation returns", equals=0)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._fail_validation`

### start
- sig: `start() -> Continue`
- does: rejects an operator mode other than `auto` or `human`
- verify: count(subject="invalid finalize operator mode failures", equals=1)
- does: starts reconciliation with a zero resolution count
- verify: count(subject="finalize reconciliation starts", equals=1)
- raises: `WorkflowFailed` for an invalid operator mode
- verify: count(subject="invalid finalize mode workflow failures", equals=1)
- returns: returns a continuation targeting reconciliation
- verify: json_path(path="$.next", equals="reconcile")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.start`

### reconcile
- sig: `reconcile(resolves: int = 0) -> Continue | Await`
- does: runs the reconciliation gate against the committed epic baseline
- verify: count(subject="finalize reconciliation checks", equals=1)
- does: proceeds to integrity when reconciliation holds or is skipped
- verify: count(subject="reconciliation-to-integrity transitions", equals=1)
- does: treats a missing git baseline, epics directory, or committed epic baseline as a skipped gate rather than a failure
- verify: count(subject="fail-open reconciliation skips", equals=1)
- does: awaits the operator when human mode is selected or the reconciliation resolution limit is reached
- verify: visible(locator="operator-awaiting context", text="reconciliation")
- does: routes reconciliation errors to the shared operator resolver while fewer than two automatic resolutions have been attempted
- verify: count(subject="automatic reconciliation resolutions", equals=1)
- returns: returns a continuation or operator await state for the next reconciliation decision
- verify: count(subject="reconciliation gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.reconcile`

### resolve_reconcile
- sig: `resolve_reconcile(notes: str, resolves: int = 0) -> Await`
- does: asks the shared operator resolver to resolve reconciliation findings
- verify: count(subject="shared reconciliation resolver turns", equals=1)
- does: persists the reconciliation notes in the author operator context
- verify: persists(subject="reconciliation operator context")
- does: does not use the resolver result to bypass the operator await
- verify: count(subject="reconciliation resolver awaits", equals=1)
- returns: returns an operator await state that resumes at integrity
- verify: json_path(path="$.next", equals="integrity")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.resolve_reconcile`

### integrity
- sig: `integrity(resolves: int = 0) -> Continue | Await`
- does: runs whole-graph integrity verification
- verify: count(subject="finalize integrity checks", equals=1)
- does: proceeds to roadmap milestone validation when integrity holds or is skipped
- verify: count(subject="integrity-to-milestone transitions", equals=1)
- does: treats an unloadable graph as a skipped integrity gate and proceeds
- verify: count(subject="fail-open integrity skips", equals=1)
- does: awaits the operator when human mode is selected or the integrity resolution limit is reached
- verify: visible(locator="operator-awaiting context", text="integrity")
- does: routes integrity errors to graph resolution while fewer than two automatic resolutions have been attempted
- verify: count(subject="automatic integrity resolutions", equals=1)
- returns: returns a continuation or operator await state for the next integrity decision
- verify: count(subject="integrity gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.integrity`

### resolve_graph
- sig: `resolve_graph(notes: str, resolves: int = 0) -> Continue | Await`
- does: asks the integrity resolver to diagnose graph validation notes
- verify: count(subject="graph integrity resolver turns", equals=1)
- does: awaits the operator when the resolver escalates the graph findings
- verify: visible(locator="operator-awaiting context", text="graph")
- does: repeats integrity with an incremented resolution count when the resolver answers
- verify: count(subject="graph resolution retry transitions", equals=1)
- raises: no workflow failure solely because the resolver escalates
- verify: count(subject="graph resolver workflow failures", equals=0)
- raises: an escalated resolver result becomes an operator await
- verify: visible(locator="operator-awaiting context", text="graph")
- returns: returns an integrity continuation or an operator await state
- verify: count(subject="graph resolution outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.resolve_graph`

### roadmap_milestone
- sig: `roadmap_milestone(resolves: int = 0) -> Continue | Await`
- does: validates that the approved roadmap owns one non-empty milestone
- verify: count(subject="finalize roadmap milestone checks", equals=1)
- does: proceeds to close when the roadmap milestone is valid
- verify: count(subject="milestone-to-close transitions", equals=1)
- does: awaits the operator when human mode is selected or the milestone resolution limit is reached
- verify: visible(locator="operator-awaiting context", text="milestone")
- does: routes milestone errors to the integrity resolver while fewer than two automatic resolutions have been attempted
- verify: count(subject="automatic milestone resolutions", equals=1)
- returns: returns a continuation or operator await state for the next milestone decision
- verify: count(subject="milestone gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.roadmap_milestone`

### resolve_milestone
- sig: `resolve_milestone(notes: str, resolves: int = 0) -> Continue | Await`
- does: asks the integrity resolver to diagnose roadmap milestone validation notes
- verify: count(subject="milestone resolver turns", equals=1)
- does: awaits the operator when the resolver escalates the milestone findings
- verify: visible(locator="operator-awaiting context", text="milestone")
- does: repeats milestone validation with an incremented resolution count when the resolver answers
- verify: count(subject="milestone resolution retry transitions", equals=1)
- raises: no workflow failure solely because the resolver escalates
- verify: count(subject="milestone resolver workflow failures", equals=0)
- raises: an escalated resolver result becomes an operator await
- verify: visible(locator="operator-awaiting context", text="milestone")
- returns: returns a milestone continuation or an operator await state
- verify: count(subject="milestone resolution outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.resolve_milestone`

### close
- sig: `close() -> Done`
- does: validates that authored artifacts contain loadable, authored, selectable planning work
- verify: count(subject="final authored artifact checks", equals=1)
- does: commits an incomplete marker and fails when authored artifacts are invalid
- verify: count(subject="invalid authored artifact failures", equals=1)
- does: revalidates the roadmap-owned milestone before delivery
- verify: count(subject="final roadmap milestone rechecks", equals=1)
- does: commits an incomplete marker and fails when the roadmap milestone is invalid
- verify: count(subject="invalid final milestone failures", equals=1)
- does: leaves the roadmap approved when either terminal validation fails
- verify: json_path(path="$.status", equals="approved")
- does: advances the roadmap status from `approved` to `authored`
- verify: json_path(path="$.status", equals="authored")
- does: commits the authored planning documents on the current branch
- verify: persists(subject="authored planning documents")
- does: does not create a branch or open a pull request during delivery
- verify: count(subject="finalize pull requests", equals=0)
- returns: returns Done with the commit result
- verify: json_path(path="$.committed", equals=True)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.close`
