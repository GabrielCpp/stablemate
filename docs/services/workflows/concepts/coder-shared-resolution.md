---
type: concept
slug: coder-shared-resolution
title: Coder resolver decision handling
---
# Coder resolver decision handling

- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py` @1a1dc35f49c9
- detail: [coder operator resolution result](../formats/coder-operator-resolution.md)
- detail: [coder path resolution](coder-path-resolution.md)

The coder resolver boundary prepares the single operator-resolution prompt, locates the
docs-home folder that holds its decisions, one `docs/decisions/<slug>/decision.md` per decision, and classifies the structured reply. Only the
literal `answered` decision selects the continuing branch; every other decision value selects the
operator escalation branch. A reply that claims to be answered is logged with its summary and any
grounding or decision record, but this helper does not independently judge whether the cited
grounding settles the block.

## Fields

### RESOLVER_POWER
- type: string
- default: `max`
- required: true
- semantics: model-power tier requested for the resolver turn
- verify: count(subject="resolver power setting", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::RESOLVER_POWER` @1a1dc35f49c9

## Methods

### resolver_args
- sig: `resolver_args(flow: Workflow, *, block_kind: str, notes: str, story: StoryPaths | None = None) -> dict[str, str]`
- does: supplies the story path and specification directory of the given `story`, or of the flow context when none is given, with the block kind and block notes to the shared resolver prompt
- verify: json_path(path="$.result", matches="story_path")
- does: supplies the absolute decisions directory derived from the repository directory alone. A coder run, an interactive session and a worktree of one member repository read and file decisions in the same folder. The prompt reads them as `<decisions directory>/*/decision.md` and files a new one with `ostler decisions add`
- verify: json_path(path="$.result", matches="decisions_dir")
- does: supplies the structured `OperatorResolution` result schema to the prompt
- verify: json_path(path="$.result", matches="result_schema")
- returns: a string-valued argument mapping for the shared resolver prompt
- verify: count(subject="resolver prompt argument mappings", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::resolver_args` @1a1dc35f49c9

### decisions_dir
- sig: `decisions_dir(repo_dir: str) -> Path`
- does: resolves the documentation root from the supplied repository directory alone: the artifacts dir when the repository is in any workspace of the home config, else the repository itself
- verify: json_path(path="$.result", equals="example result")
- does: returns the decisions directory resolved beneath that documentation root
- verify: json_path(path="$.result", matches="decisions")
- returns: an absolute `Path` passed to the resolver prompt
- verify: json_path(path="$.result", matches="/decisions")
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::decisions_dir` @1a1dc35f49c9
- tests: `workflows/tests/coder/shared/test_decision_home.py::test_a_run_and_a_session_resolve_the_same_decisions_folder`

### answered
- sig: `answered(flow: Workflow, result: OperatorResolution, block_kind: str) -> bool`
- does: returns false for every resolver result whose decision is not the literal `answered`
- verify: json_path(path="$.result", equals=false)
- does: logs an answered decision with its block kind, summary, grounding citations, and optional decision record
- verify: emitted(event="resolver decision log", count=1)
- does: logs an explicit warning when an answered result has no grounding citation
- verify: emitted(event="resolver ungrounded-answer warning", count=1)
- returns: true only when the resolver decision is the literal `answered`
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::answered` @1a1dc35f49c9
