---
type: concept
slug: coverage-validator
title: Author coverage validator
---
# Author coverage validator

The Author main coverage validator checks one named epic through Ostler's epic-scoped doctor
operation. It reports only the doctor error codes that describe broken seed coverage or story
topology, while leaving unrelated epic findings to other gates. The caller may permit unwritten
stories during an intermediate split pass; the default authored requirement includes that finding.

- code: `workflows/src/workhorse_workflows/author/main/nodes/coverage.py::validate_coverage`
- detail: [story split subflow](story-split-subflow.md)
- detail: [coverage defects](../coverage-defects.md)
- detail: [author shared paths](author-shared-paths.md)

## Methods

### validate_coverage
- sig: `validate_coverage(logger: logging.Logger, epic_dir: str = "", repo_dir: str = "", require_authored: bool = True) -> Defects`
- does: trims surrounding whitespace from `epic_dir` before resolving the epic name
- verify: count(subject="coverage validator epic-directory normalization", equals=1)
- does: returns `Defects(ok=false, errors="no epic_dir supplied")` without running Ostler when the trimmed epic directory is empty
- verify: json_path(path="$.ok", equals=False)
- does: resolves the consuming repository with the survey repository-root policy and constructs an Ostler facade for that root
- verify: count(subject="coverage validator Ostler evaluations", equals=1)
- does: runs Ostler doctor for the basename of the supplied epic directory, scoping findings to that epic
- verify: count(subject="epic-scoped coverage doctor evaluations", equals=1)
- does: returns `Defects(ok=false, errors="ostler doctor for epic <name> could not run")` when the scoped doctor outcome is invalid
- verify: json_path(path="$.errors", matches="ostler doctor for epic .+ could not run")
- does: retains error findings only for orphan-seed, dangling-seed, cross-epic-seed, dangling-dependency, cross-epic-dependency, missing-story-file, and unwritten-story
- verify: count(subject="retained coverage doctor findings", equals=1)
- does: excludes an unwritten-story finding when `require_authored` is false
- verify: absent(subject="unwritten-story finding when authored stories are not required")
- returns: returns `Defects(ok=true, errors="")` when no retained coverage findings remain
- verify: json_path(path="$.ok", equals=True)
- returns: returns `Defects(ok=false, errors=...)` with one formatted `[code] message` line per retained finding when coverage findings remain
- verify: json_path(path="$.errors", matches=".+\\].+")
- code: `workflows/src/workhorse_workflows/author/main/nodes/coverage.py::validate_coverage`
