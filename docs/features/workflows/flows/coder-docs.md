---
type: flow
slug: coder-docs
title: Coder documentation flow
---
# Coder documentation flow

- The `Docs` machine folds one completed story into the current OKF book. It resolves the story
  and documentation context, distinguishes an unmanaged book from an unusable one, optionally
  grounds the code diff locally, asks an author turn to write the graph, gates the result against
  direct grounding, and then obtains an independent documentation review. It is entered by the
  Coder main flow or directly with `workhorse-coder run docs`.
- start: the configured story slug resolves to a readable story before any documentation turn
- verify: count(subject="resolved documentation story", equals=1)
- start: the repository has a usable OKF book and a classified documentation context
- verify: count(subject="classified documentation contexts", equals=1)
- steps:
  - [setup](#setup)
  - [context-classification](#context-classification)
  - [document](#document)
  - [grounding-gate](#grounding-gate)
  - [repair](#repair)
  - [review](#review)
  - [author-resolution](#author-resolution)
- end: an approved documentation review returns a passed result containing every node authored during the flow
- verify: count(subject="passed documentation results", equals=1)
- end: an absent OKF book returns not-applicable without an agent turn
- verify: count(subject="not-applicable documentation results", equals=1)
- end: an unusable OKF book fails before documentation
- verify: count(subject="unusable OKF documentation failures", equals=1)
- end: a malformed agent result fails before a repair or review pass
- verify: count(subject="malformed documentation result failures", equals=1)
- end: an unresolved documentation block returns a blocked result
- verify: count(subject="blocked documentation results", equals=1)
- detail: [coder main flow](coder-main.md)
- detail: [coder docs subflow package](../concepts/coder-docs-subflow.md)
- detail: [coder shared documentation helpers](../concepts/coder-shared-documentation.md)
- code: `workflows/src/workhorse_workflows/coder/docs/flow.py::Docs`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_outside_the_docs_worktree_take_the_semantic_route`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_failed_gate_reworks_before_the_reviewer_ever_runs`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_block_is_put_to_the_author_before_it_ends_the_flow`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_run_killed_mid_review_resumes_without_re_documenting`

`story`, `docs_path`, `workspace_file`, `epic`, `target_env`, `preexisting`, and `operator_mode`
are checkpointed inputs. Empty docs and workspace paths use the repository's configured
resolution; `target_env` defaults to `local`, and `operator_mode` defaults to `auto`.

## Steps

### setup

- kind: prepare

The flow resolves workspace directories and prepares the requested story. An empty or
unresolvable story path raises a workflow failure before OKF detection or an agent turn. Every
entry resets the story's documentation-repair conversation and the shared story backbone so a
resume or post-fix pass cannot reuse a conversation describing an older book. The shared backbone
is intentionally left open on terminal return for the caller's next lane; the private repair
conversation is always reset.

`Docs.labels` exposes the resolved story slug as the `work_id` activity label when one exists.
`Docs.state_labels` adds grounding and review counters, progress verdicts, and carried story
labels only after a `DocsLoop` exists; setup and the first `start` entry report only the story
label.

### context-classification

- kind: prepare

The flow first detects the OKF book. No configured OKF graph is a successful `not_applicable`
result and spends no agent turn; an unusable graph is a workflow failure. It then classifies the
documentation context. A readable local source root uses the local route, where an OKF context
packet maps changed production units to graph references and is validated before review. Sources
outside the documentation worktree use the semantic route, where no diff packet is built and the
agent result plus Ostler review provide the authority. An unreadable context is a workflow
failure, not a semantic pass.

When a workspace manifest and story id are supplied, the flow also resolves story-source
provenance and fails if that mapping is invalid. It builds the initial documentation obligations
before the author turn: local mode records the current OKF packet status and lists ungrounded
changed production references; semantic mode records that no worktree grounding list is
available. The same packet arguments are rebuilt after authoring rather than reusing the
pre-author snapshot.

### document

- kind: drive

The first author turn uses the `document-story` prompt with medium power and the story, epic,
features-root, implementation context, workspace directories, and the initial grounding worklist.
It may return `documented`, `not_required`, or a blocked result. `not_required` still proceeds to
the grounding gate; it means the story changes nothing represented by the book, not that the gate
is skipped. A blocked author result enters author resolution and never reaches review.

The returned node identities are appended to the loop's accumulated identities with duplicates
removed. A repair pass can therefore return an empty node list when its cited finding is already
resolved without discarding nodes authored on earlier passes.

### grounding-gate

- kind: verify

For local context the flow rebuilds the OKF packet against the post-author worktree, validates the
packet, and asks `verify_story_documentation` to check every changed production unit directly
against the accumulated authored nodes. The gate is skipped only for semantic context, with both
context status values passed as empty strings. Only an explicit passed gate reaches review. A
failed gate supplies the remaining `G:` references to repair and does not spend reviewer budget.
The grounding budget is three rework passes; exhaustion blocks instead of approving or failing the
whole caller run.

### repair

- kind: drive

Grounding failures and reviewer findings both enter `repair`, which edits only the cited nodes and
does not re-author the whole story. Repair turns use low power, the story's repair conversation,
the current gate and review notes, and the outstanding obligations. A repair turn has a 45-minute
timeout and no in-place retry. A timeout is redispatched on a fresh conversation with an overrun
notice; three overruns enter author resolution. The repair chain is recycled after four laps or
when grounding progress is stalled. Authored node identities accumulate across passes rather than
being replaced by the latest response.

If the repair agent times out, no documentation result is fabricated. The flow records an
`overran` transition, resets the repair conversation, and redispatches with a notice that the
previous turn was cut and that the doctor worklist remains authoritative. After three such
overruns it enters author resolution. The repair brief is bounded to 12,000 characters only as a
last-resort prompt safeguard; the complete doctor list is expected to be spilled to the story
specification first.

### review

- kind: verify

After a passed gate, the flow dispatches one independent high-power `review-story-documentation`
turn. The reviewer receives the original, unnarrowed story obligations even after the grounding
gate has closed some of them. An approved review returns `DocsResult(status="passed")` and the
accumulated authored nodes. A revision must contain findings with an id, target, issue, and repair;
missing structured findings are a workflow failure. The finding id is opaque. A blocked review
enters author resolution with its actionable findings, while a revision gets up to three review
rework passes; exhaustion blocks rather than raising.

The reviewer result is checked before its findings are used: a `revise` result must contain at
least one finding, and every finding must provide an id, target, issue, and repair. The id is an
opaque stable handle and is preserved only in the repair notes. An approved result resets the
private repair chain and returns the accumulated authored node identities; a blocked result
passes its actionable findings to author resolution.

### author-resolution

- kind: drive

Documentation blocks are bounded by three resolver consultations, not by a global block cap. In
`auto` mode the shared resolver may answer only from an existing decision, repository rule,
installed skill, or acceptance criterion. An answered story-scoped decision is read from the story
context, prepended to the repair notes, and gets one repair lap with a fresh reviewer budget. An
epic-scoped answer cannot be applied to one story and ends the flow blocked with the answer as its
notes. An unanswered or escalated resolver result also ends blocked. `human` and `operator` modes
await the operator on the story context instead of dispatching the resolver; a missing answer
remains blocked.

The resolver is unbounded in wall-clock time because it stands in for the accountable author, but
its consultations are bounded by `MAX_DOCS_BLOCKS`. An answered story-scoped context is consumed
by `read_author`, which resets the reviewer counter and sends one repair lap containing both the
ratified answer and the original block notes. An epic-scoped answer cannot be applied to this
story. If the expected answer file is absent, still awaiting, or cannot be acted on, the flow
returns blocked rather than spending a repair lap on an empty decision.

The flow leaves the shared story backbone open for the caller's next lane, but resets its private
repair chain on every terminal result. A checkpoint taken after the grounding gate resumes at
review with the author result; a checkpoint during repair resumes with the outstanding worklist
and progress counters, without repeating the initial author pass.

## State bookkeeping

The module's private helpers keep state transitions deterministic without becoming workflow
states. `_author_args` renders the story, epic, context, feature-root, plan summary, gate/review
notes, and current obligations shared by the author and repair prompts. `_rework` routes either a
grounding result or a review result to repair without changing the result's finding payload.
`_context_mode` treats a manifest-resolved external source repository as locally verifiable when
the resolved story sources are present; otherwise it preserves the classifier's local or
semantic mode. `_epic_path` derives the parent epic path through configured docs-root
resolution.

Review findings are rendered one per line as `id [kind] target: issue. Repair: repair` by
`_format_finding`; `_review_notes` places those lines before an optional summary. A malformed
revision is a workflow failure, while a malformed author response is rejected by the typed
result contract before the flow can enter repair. The module exports only `Docs`.
