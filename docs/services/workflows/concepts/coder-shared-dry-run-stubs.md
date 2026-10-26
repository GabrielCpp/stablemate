---
type: concept
slug: coder-shared-dry-run-stubs
title: Coder shared dry-run stubs
---
# Coder shared dry-run stubs

- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py` @884c9598465e

Coder genesis uses these callbacks as deterministic stand-ins when the workflow runs with
`--dry-run`. Every callback accepts arbitrary node arguments because the dry-run registry replaces
the real node body. The successful values keep the run on its forward path; `classified` selects
the absent-target genesis branch, while `story_paths` supplies a synthetic story so later
per-story lanes are reached. `launch_set` supplies the one-story launch the main flow works.

## Methods

### classified

Classifies the dry-run genesis target as worth processing and chooses the full bootstrap branch.

- sig: `classified(*_args: object, **_kwargs: object) -> TargetClassification`
- does: ignores all positional and keyword arguments
- verify: count(subject="genesis target classification stub invocations", equals=1)
- returns: a target classification with `ok=true`
- verify: json_path(path="$.ok", equals=true)
- returns: `target_state="absent"` so the subsequent genesis states are visited
- verify: json_path(path="$.target_state", equals="absent")
- returns: the note `dry run`
- verify: json_path(path="$.note", equals="dry run")
- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py::classified` @884c9598465e

### built

Reports that the synthetic genesis skeleton was created successfully.

- sig: `built(*_args: object, **_kwargs: object) -> Skeleton`
- does: ignores all positional and keyword arguments
- verify: count(subject="genesis skeleton stub invocations", equals=1)
- returns: a skeleton result with `ok=true`
- verify: json_path(path="$.ok", equals=true)
- returns: the note `dry run`
- verify: json_path(path="$.note", equals="dry run")
- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py::built` @884c9598465e

### installed

Reports that the synthetic Farrier installation completed successfully.

- sig: `installed(*_args: object, **_kwargs: object) -> FarrierInstall`
- does: ignores all positional and keyword arguments
- verify: count(subject="genesis Farrier installation stub invocations", equals=1)
- returns: an installation result with `ok=true`
- verify: json_path(path="$.ok", equals=true)
- returns: the note `dry run`
- verify: json_path(path="$.note", equals="dry run")
- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py::installed` @884c9598465e

### valid

Reports that the synthetic genesis result satisfies the main flow’s preconditions.

- sig: `valid(*_args: object, **_kwargs: object) -> GenesisReport`
- does: ignores all positional and keyword arguments
- verify: count(subject="genesis validation stub invocations", equals=1)
- returns: a genesis report with `valid=true`
- verify: json_path(path="$.valid", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py::valid` @884c9598465e

### story_paths

Provides the synthetic story identity and paths needed to traverse the per-story lanes.

- sig: `story_paths(*_args: object, **_kwargs: object) -> StoryPaths`
- does: ignores all positional and keyword arguments
- verify: count(subject="story path stub invocations", equals=1)
- returns: a `StoryPaths` result for story `dry-run-story`
- verify: json_path(path="$.story_slug", equals="dry-run-story")
- returns: the epic identity `dry-run-epic`
- verify: json_path(path="$.story_epic", equals="dry-run-epic")
- returns: the story id `dry-run-story`, the same value as the story slug
- verify: json_path(path="$.story_id", equals="dry-run-story")
- returns: a story document path under `/dry-run/docs/epics/dry-run-epic/stories/dry-run-story`
- verify: json_path(path="$.story_path", matches="/dry-run/docs/epics/dry-run-epic/stories/dry-run-story/story\\.md")
- returns: a `spec_dir` beneath the synthetic story directory
- verify: json_path(path="$.spec_dir", matches="/dry-run/docs/epics/dry-run-epic/stories/dry-run-story/spec")
- returns: a `qa_dir` beneath the synthetic story directory
- verify: json_path(path="$.qa_dir", matches="/dry-run/docs/epics/dry-run-epic/stories/dry-run-story/qa")
- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py::story_paths` @884c9598465e

### launch_set

Provides the synthetic launch set that lets the dry-run main flow reach one story.

- sig: `launch_set(*_args: object, **_kwargs: object) -> LaunchSet`
- does: ignores all positional and keyword arguments
- verify: count(subject="launch set stub invocations", equals=1)
- returns: a launch set in `epic` mode
- verify: json_path(path="$.mode", equals="epic")
- returns: one entry for story `dry-run-story` under epic `dry-run-epic`
- verify: json_path(path="$.entries[0].slug", equals="dry-run-story")
- code: `workflows/src/workhorse_workflows/coder/shared/stubs.py::launch_set` @884c9598465e
