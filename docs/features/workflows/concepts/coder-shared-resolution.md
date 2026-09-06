---
type: concept
slug: coder-shared-resolution
title: Coder resolver decision handling
---
# Coder resolver decision handling

- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py`
- detail: [coder operator resolution result](../coder-operator-resolution.md)
- detail: [coder path resolution](coder-path-resolution.md)

The coder resolver boundary prepares the single operator-resolution prompt, locates the
docs-scoped decision records it may read or create, and classifies the structured reply. Only the
literal `answered` decision selects the continuing branch; every other decision value selects the
operator escalation branch. A reply that claims to be answered is logged with its summary and any
grounding or decision record, but this helper does not independently judge whether the cited
grounding settles the block.

## Fields

### RESOLVER_POWER
- type: string
- default: `smart`
- required: true
- semantics: model-power tier requested for the resolver turn
- verify: count(subject="resolver power setting", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::RESOLVER_POWER`

## Methods

### resolver_args
- sig: `resolver_args(flow: Workflow, *, block_kind: str, notes: str, docs_path: str) -> dict[str, str]`
- does: supplies the story path, specification directory, block kind, and block notes to the shared resolver prompt
- verify: json_path(path="$.result", matches="story_path")
- does: supplies the absolute decisions directory derived from the documentation path and repository directory
- verify: json_path(path="$.result", matches="decisions_dir")
- does: supplies the structured `OperatorResolution` result schema to the prompt
- verify: json_path(path="$.result", matches="result_schema")
- returns: a string-valued argument mapping for the shared resolver prompt
- verify: count(subject="resolver prompt argument mappings", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::resolver_args`

### decisions_dir
- sig: `decisions_dir(docs_path: str, repo_dir: str) -> Path`
- does: resolves the documentation root from the supplied documentation and repository paths
- verify: json_path(path="$.result", matches=".*")
- does: returns the decisions directory resolved beneath that documentation root
- verify: json_path(path="$.result", matches="decisions")
- returns: an absolute `Path` passed to the resolver prompt
- verify: json_path(path="$.result", matches="/decisions")
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::decisions_dir`

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
- code: `workflows/src/workhorse_workflows/coder/shared/resolution.py::answered`
