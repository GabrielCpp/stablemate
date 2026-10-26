---
type: concept
slug: author-finalize-subflow
title: Author finalize subflow
---
# Author finalize subflow

`Finalize` validates and delivers an already-authored milestone. It never performs another authoring
agent turn: it resolves the epic-mode configuration, checks for silently dropped planning scope,
checks whole-graph integrity, checks that the milestone lists epics, validates the produced
artifacts again, marks the milestone authored, and commits the authored documents on the current
branch. The gate implementations are described in the [author artifact gates](author-artifact-gates.md)
module concept. A reconciliation failure awaits the operator directly. Integrity and milestone validation each allow at most two automatic resolver passes. Human mode bypasses automatic resolution. Validation failures
are either routed through bounded automatic resolution or parked at an operator context file; a
terminal artifact or milestone failure commits an incomplete marker and raises instead of reporting
success. A passing or explicitly skipped gate is the only path to the next gate. The module exports
the integrity resolution limit and an unbounded timeout used only for resolver turns.

- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize` @dc589cfbd2c4
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/_blueprint.py::blueprint` @840c4e312d81
- tests: `workflows/tests/author/finalize/test_flow.py::test_finalizes_with_one_commit_on_the_current_branch`
- tests: `workflows/tests/author/finalize/test_flow.py::test_terminal_validation_commits_incomplete_then_fails`
- detail: [author milestone intake](../flows/author-milestone-intake.md)

## Fields

### operator_mode
- type: `str`
- default: `"auto"`
- required: false
- semantics: selects automatic resolution or direct human operator gates
- verify: json_path(path="$.operator_mode", matches="^(auto|human)$")
- semantics: accepts only `auto` and `human`
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.operator_mode` @dc589cfbd2c4

### MAX_INTEGRITY_RESOLVES
- type: `int`
- default: `2`
- required: true
- semantics: maximum automatic integrity and milestone resolver passes before awaiting an operator
- verify: json_path(path="$.max_integrity_resolves", equals=2)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::MAX_INTEGRITY_RESOLVES` @dc589cfbd2c4

### UNBOUNDED
- type: `float`
- default: `float("inf")`
- required: true
- semantics: timeout passed to resolver agent turns so the flow cap does not truncate diagnosis
- verify: json_path(path="$.resolver_timeout", equals="inf")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::UNBOUNDED` @dc589cfbd2c4

## Methods

### setup
- sig: `setup() -> RunContext`
- does: loads author configuration in epic mode
- verify: count(subject="finalize configuration loads", equals=1)
- does: stores the resolved configuration as the flow context
- verify: count(subject="finalize run contexts", equals=1)
- returns: returns the resolved [run context](../formats/author-config.md)
- verify: json_path(path="$.repo_root", equals="docs/stories")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.setup` @dc589cfbd2c4

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the milestone's folder name as `work_id`
- verify: json_path(path="$.work_id", equals="CASE-1234")
- does: reports progress as validating and delivering the authored milestone
- verify: json_path(path="$.progress", equals="validating and delivering authored milestone")
- returns: returns the work identifier and progress labels
- verify: count(subject="finalize label mappings", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.labels` @dc589cfbd2c4

### _context
- sig: `_context() -> str`
- does: resolves the configured author operator context path relative to the repository root
- verify: json_path(path="$.context_path", equals="docs/stories/acme-story/story.md")
- returns: returns the path used by finalization's operator gates
- verify: count(subject="finalize operator context paths", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._context` @dc589cfbd2c4

### _context_path
- sig: `_context_path() -> Path`
- does: joins the repository root to the configured author operator context path
- verify: json_path(path="$.context_path", equals="docs/stories/acme-story/story.md")
- returns: returns the absolute operator context file path
- verify: count(subject="absolute finalize context paths", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._context_path` @dc589cfbd2c4

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
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._resolve_integrity` @dc589cfbd2c4
- detail: [author resolve-integrity prompt](../formats/author-resolve-integrity-prompt.md)

### _fail_validation
- sig: `_fail_validation(heading: str, errors: str) -> None`
- does: commits an incomplete milestone marker before terminating failed final validation
- verify: count(subject="incomplete finalize commits", equals=1)
- does: raises workflow failure with the validation heading and errors
- verify: count(subject="terminal finalize validation failures", equals=1)
- raises: `WorkflowFailed` after the incomplete commit is attempted
- verify: count(subject="workflow failures after incomplete finalize commits", equals=1)
- returns: returns no value when validation does not fail before the commit call
- verify: count(subject="successful _fail_validation returns", equals=0)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize._fail_validation` @dc589cfbd2c4

### start
- sig: `start() -> Continue`
- does: rejects an operator mode other than `auto` or `human`
- verify: count(subject="invalid finalize operator mode failures", equals=1)
- does: starts reconciliation
- verify: count(subject="finalize reconciliation starts", equals=1)
- raises: `WorkflowFailed` for an invalid operator mode
- verify: count(subject="invalid finalize mode workflow failures", equals=1)
- returns: returns a continuation targeting reconciliation
- verify: json_path(path="$.next", equals="reconcile")
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.start` @dc589cfbd2c4

### reconcile
- sig: `reconcile() -> Continue | Await`
- does: runs the reconciliation gate against the committed epic baseline
- verify: count(subject="finalize reconciliation checks", equals=1)
- does: proceeds to integrity when reconciliation holds or is skipped
- verify: count(subject="reconciliation-to-integrity transitions", equals=1)
- does: treats a missing git baseline, epics directory, or committed epic baseline as a skipped gate rather than a failure
- verify: count(subject="fail-open reconciliation skips", equals=1)
- does: awaits the operator with the reconciliation errors when the gate fails, and resumes at integrity
- verify: json_path(path="$.await", matches="reconciliation")
- returns: returns a continuation or operator await state for the next reconciliation decision
- verify: count(subject="reconciliation gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.reconcile` @dc589cfbd2c4

### integrity
- sig: `integrity(resolves: int = 0) -> Continue | Await`
- does: runs whole-graph integrity verification
- verify: count(subject="finalize integrity checks", equals=1)
- does: proceeds to milestone epic validation when integrity holds or is skipped
- verify: count(subject="integrity-to-milestone transitions", equals=1)
- does: treats an unloadable graph as a skipped integrity gate and proceeds
- verify: count(subject="fail-open integrity skips", equals=1)
- does: awaits the operator when human mode is selected or the integrity resolution limit is reached
- verify: json_path(path="$.await", matches="integrity")
- does: routes integrity errors to graph resolution while fewer than two automatic resolutions have been attempted
- verify: count(subject="automatic integrity resolutions", equals=1)
- returns: returns a continuation or operator await state for the next integrity decision
- verify: count(subject="integrity gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.integrity` @dc589cfbd2c4

### resolve_graph
- sig: `resolve_graph(notes: str, resolves: int = 0) -> Continue | Await`
- does: asks the integrity resolver to diagnose graph validation notes
- verify: count(subject="graph integrity resolver turns", equals=1)
- does: awaits the operator when the resolver escalates the graph findings
- verify: json_path(path="$.await", matches="graph")
- does: repeats integrity with an incremented resolution count when the resolver answers
- verify: count(subject="graph resolution retry transitions", equals=1)
- raises: no workflow failure solely because the resolver escalates
- verify: count(subject="graph resolver workflow failures", equals=0)
- raises: an escalated resolver result becomes an operator await
- returns: returns an integrity continuation or an operator await state
- verify: count(subject="graph resolution outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.resolve_graph` @dc589cfbd2c4
- detail: [author resolve-integrity prompt](../formats/author-resolve-integrity-prompt.md)

### milestone_epics
- sig: `milestone_epics(resolves: int = 0) -> Continue | Await`
- does: validates that the approved milestone lists at least one epic
- verify: count(subject="finalize milestone epic checks", equals=1)
- does: proceeds to close when the milestone lists epics
- verify: count(subject="milestone-to-close transitions", equals=1)
- does: awaits the operator when human mode is selected or the milestone resolution limit is reached
- verify: json_path(path="$.await", matches="milestone")
- does: routes milestone errors to the integrity resolver while fewer than two automatic resolutions have been attempted
- verify: count(subject="automatic milestone resolutions", equals=1)
- returns: returns a continuation or operator await state for the next milestone decision
- verify: count(subject="milestone gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.milestone_epics` @dc589cfbd2c4

### resolve_milestone
- sig: `resolve_milestone(notes: str, resolves: int = 0) -> Continue | Await`
- does: asks the integrity resolver to diagnose milestone validation notes
- verify: count(subject="milestone resolver turns", equals=1)
- does: awaits the operator when the resolver escalates the milestone findings
- verify: json_path(path="$.await", matches="milestone")
- does: repeats milestone validation with an incremented resolution count when the resolver answers
- verify: count(subject="milestone resolution retry transitions", equals=1)
- raises: no workflow failure solely because the resolver escalates
- verify: count(subject="milestone resolver workflow failures", equals=0)
- raises: an escalated resolver result becomes an operator await
- returns: returns a milestone continuation or an operator await state
- verify: count(subject="milestone resolution outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.resolve_milestone` @dc589cfbd2c4
- detail: [author resolve-integrity prompt](../formats/author-resolve-integrity-prompt.md)

### close
- sig: `close() -> Done`
- does: validates that authored artifacts contain loadable, authored, selectable planning work
- verify: count(subject="final authored artifact checks", equals=1)
- does: commits an incomplete marker and fails when authored artifacts are invalid
- verify: count(subject="invalid authored artifact failures", equals=1)
- does: revalidates that the milestone lists epics before delivery
- verify: count(subject="final milestone epic rechecks", equals=1)
- does: commits an incomplete marker and fails when the milestone is invalid
- verify: count(subject="invalid final milestone failures", equals=1)
- does: leaves the milestone approved when either terminal validation fails
- verify: json_path(path="$.status", equals="approved")
- does: advances the milestone status from `approved` to `authored`
- verify: json_path(path="$.status", equals="authored")
- does: commits the authored planning documents on the current branch
- verify: persists(subject="authored planning documents")
- does: does not create a branch or open a pull request during delivery
- verify: count(subject="finalize pull requests", equals=0)
- returns: returns Done with the commit result
- verify: json_path(path="$.committed", equals=True)
- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.close` @dc589cfbd2c4

## Nodes

### load_config
The returned `Config` carries the resolved repository root, the repo-relative milestone path, the epics and services directories, and the layers configured in `agents.yml`'s `localInstructions:`.

- sig: `load_config(logger: logging.Logger, repo_dir: str = "", mode: str = "epic") -> Config`
- does: resolve the author's paths and prove the selected intake exists
- verify: count(subject="finalize configuration loads", equals=1)
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::load_config` @1e565a154642
- detail: [author load_config documentation roles](author-load-config-documentation-roles.md)

### verify_reconcile
- sig: `verify_reconcile(logger: logging.Logger, ref: str = "HEAD", repo_dir: str = "") -> VerifyReport`
- does: measure scope this run silently dropped against the last committed epics
- verify: count(subject="finalize reconciliation checks", equals=1)
- does: detect dropped seed items and dropped stories that were in the baseline
- verify: count(subject="dropped scope detections", equals=1)
- consistency: reconcile-report-status — the returned VerifyReport sets holds=True when no scope was dropped, skipped=True when there is no git repository, no epics directory, or no epic with a committed baseline, and errors carrying one dropped-seed or dropped-story line per silent removal otherwise
- verify: count(subject="reconciliation reports", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/artifacts.py::verify_reconcile` @f3adad9536ae

### verify_integrity
- sig: `verify_integrity(logger: logging.Logger, epic: str = "", repo_dir: str = "") -> VerifyReport`
- does: run ostler doctor over the whole graph as a blocking gate
- verify: count(subject="finalize integrity checks", equals=1)
- does: treat an unloadable graph as a skipped integrity gate
- verify: count(subject="fail-open integrity skips", equals=1)
- consistency: integrity-error-report — when ostler doctor reports error-level findings, the returned VerifyReport.errors carries each finding's code, optional scope, and message
- verify: json_path(path="$.errors", matches=".+\\].+")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/integrity.py::verify_integrity` @ca330f6a9a15

### validate_milestone_epics
- sig: `validate_milestone_epics(logger: logging.Logger, milestone: str, repo_dir: str = "") -> Defects`
- does: prove the milestone lists at least one epic
- verify: count(subject="milestone epic validations", equals=1)
- consistency: milestone-epic-presence — rejects a milestone that is missing or lists no epics
- verify: count(subject="milestone epic presence checks", equals=1)
- returns: returns whether validation holds with zero or more validation errors
- verify: count(subject="milestone epic validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::validate_milestone_epics` @cbdf7f3f88f8

### validate_artifacts
- sig: `validate_artifacts(logger: logging.Logger, repo_dir: str = "") -> Defects`
- does: prove that coder engine can walk what this run produced
- verify: count(subject="artifact validations", equals=1)
- does: validate every queued epic is loadable with at least one authored story
- verify: count(subject="epic-story-coverage checks", equals=1)
- does: require at least one story remain selectable for coder to run
- verify: count(subject="selectable story checks", equals=1)
- consistency: validate-artifacts-return — the returned Defects carries one error when any queued epic is unloadable, has no stories, or has an unauthored story.md
- verify: count(subject="artifact validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/artifacts.py::validate_artifacts` @f3adad9536ae

### mark_milestone_authored

The node advances one validated milestone from `approved` to `authored` (idempotently, a milestone already in `authored` returns without rewriting) and returns a `MilestoneStatus` carrying the milestone path and the new status.

- sig: `mark_milestone_authored(logger: logging.Logger, milestone: str, repo_dir: str = "") -> MilestoneStatus`
- does: advance one validated milestone from approved to authored idempotently
- verify: count(subject="milestone status advances", equals=1)
- does: update the milestone's frontmatter status field from `approved` to `authored`
- verify: json_path(path="$.status", equals="authored")
- verify: count(subject="authored milestone results", equals=1)
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::mark_milestone_authored` @cbdf7f3f88f8

### commit_author
- sig: `commit_author(logger: logging.Logger, mode: str = "epic", epic: str = "", bullet: str = "", milestone: str = "", repo_dir: str = "", docs_dir: str = "docs", id_registry: str = ".agents/ids.json") -> Committed`
- does: commit the epic/story docs this run wrote to the current branch
- verify: count(subject="finalize commits", equals=1)
- does: scope commits to the docs directory and id registry, skipping paths that do not exist
- verify: count(subject="scoped commit paths", equals=1)
- does: format the commit message with the mode, epic, and bullet for human readability
- verify: count(subject="authored commit messages", equals=1)
- returns: a `Committed` carrying the success flag — `committed=True` when `commit_paths` produced a commit, `committed=False` when the repository has no git root, the configured scope is empty, or `commit_paths` did not produce a commit
- verify: persists(subject="authored planning documents")
- code: `workflows/src/workhorse_workflows/author/shared/nodes/commit.py::commit_author` @d5269aa9b09f

### blueprint
- sig: `Blueprint("author-finalize") -> Blueprint`
- does: provides the one node-registration target owned by the finalize package
- returns: returns a blueprint named `author-finalize`
- verify: json_path(path="$.name", equals="author-finalize")
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/_blueprint.py::blueprint` @840c4e312d81
