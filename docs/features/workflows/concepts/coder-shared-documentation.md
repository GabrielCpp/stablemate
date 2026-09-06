---
type: concept
slug: coder-shared-documentation
title: Coder shared documentation helpers
---
# Coder shared documentation helpers

The shared documentation helpers decide whether a repository has a usable OKF book, classify
whether changed source is available for deterministic local mapping, and enforce direct grounding
of changed production units. They also expose the same grounding worklist to the author before the
author turn and scope doctor findings to the documentation nodes affected by the story.

- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::__all__`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`
- detail: [coder documentation flow](../flows/coder-docs.md)
- detail: [coder docs subflow package](coder-docs-subflow.md)
- detail: [coder shared OKF context](coder-shared-okf-context.md)

## Fields

### CONTEXT_FILE
- type: `str`
- default: `qa-okf-context.json`
- required: true
- semantics: names the diff-to-OKF packet stored below a story specification directory
- verify: count(subject="OKF context packet filename", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::CONTEXT_FILE`

### CONFIG_FILES
- type: `tuple[str, ...]`
- default: `ostler.yml | ostler.yaml | agents.yml | .agents.yml`
- required: true
- semantics: lists the repository-root configuration filenames inspected for OKF management
- verify: count(subject="OKF configuration filename set", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::CONFIG_FILES`

### MANAGED_KINDS
- type: `tuple[str, ...]`
- default: `epics | features`
- required: true
- semantics: names Ostler-managed document trees whose presence can establish an OKF repository
- verify: count(subject="managed OKF document kinds", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::MANAGED_KINDS`

### DIRECT_KINDS
- type: `set[str]`
- default: `changed-code | file-owner | surface-owner`
- required: true
- semantics: identifies packet reasons that directly implicate a documentation node
- verify: count(subject="direct documentation reason kinds", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::DIRECT_KINDS`

### SEMANTIC_SUPPRESSED
- type: `set[str]`
- default: `dangling-code-ref | missing-code-symbol`
- required: true
- semantics: suppresses local-code grounding doctor errors when semantic review has no local worktree
- verify: count(subject="semantic doctor suppression set", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::SEMANTIC_SUPPRESSED`

### MAX_PROMPT_NOTE_CHARS
- type: `int`
- default: `12000`
- required: true
- semantics: keeps an inline doctor-error note below the prompt spill threshold
- verify: count(subject="documentation prompt note limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::MAX_PROMPT_NOTE_CHARS`

### DOCTOR_ERRORS_FILE
- type: `str`
- default: `doctor-errors.txt`
- required: true
- semantics: names the spill file containing an overlong complete doctor-error list
- verify: count(subject="doctor error spill filename", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::DOCTOR_ERRORS_FILE`

### MAX_DOCTOR_ERROR_MESSAGE_CHARS
- type: `int`
- default: `400`
- required: true
- semantics: truncates an individual doctor message without dropping any finding from the list
- verify: count(subject="doctor error message limit", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::MAX_DOCTOR_ERROR_MESSAGE_CHARS`

## Methods

### ungrounded_refs
- sig: `ungrounded_refs(packet: dict[str, Any], inherited: set[str]) -> list[str]`
- does: returns exact changed production references absent from direct OKF code ownership
- verify: count(subject="ungrounded production references", equals=0)
- does: ignores deleted units because their absence needs no code bullet
- verify: count(subject="deleted units requiring code grounding", equals=0)
- does: ignores units whose path variants are unchanged pre-existing work
- verify: count(subject="pre-existing units charged for grounding", equals=0)
- returns: references using the packet's repository-qualified spelling and normalized nested-symbol ownership
- verify: count(subject="normalized grounding references", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::ungrounded_refs`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_grounding_failure_names_the_symbols_not_the_files`

### story_touched_lines
- sig: `story_touched_lines(root: Path, paths: set[str], logger: logging.Logger) -> dict[str, set[int] | None]`
- does: computes post-image lines changed from the branch merge base for each requested document
- verify: count(subject="story documentation diff line maps", equals=1)
- does: marks untracked files and unreadable diffs undecidable so the gate charges the whole file
- verify: count(subject="fail-closed documentation diff maps", equals=1)
- returns: a path-to-line-set map, with `None` representing an undecidable complete-file scope
- verify: count(subject="documentation diff scope maps", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::story_touched_lines`
- tests: `workflows/tests/coder/docs/test_scoping.py::test_an_untracked_document_is_the_story_s_in_its_entirety`

### detect_okf_docs
- sig: `detect_okf_docs(logger: logging.Logger, docs_path: str = "", features_subdir: str = "", repo_dir: str = "") -> OkfDetection`
- does: resolves the requested features root using the documentation root and Ostler configuration
- verify: count(subject="resolved OKF features roots", equals=1)
- does: recognizes OKF management from Ostler configuration, managed trees, or agent templates
- verify: count(subject="OKF management detections", equals=1)
- does: returns `no` without loading a graph when no configuration or managed tree exists
- verify: json_path(path="$.has_okf", equals="no")
- does: returns `invalid` when configuration exists but the graph cannot load
- verify: json_path(path="$.has_okf", equals="invalid")
- returns: `yes` with the graph's effective features root when the graph loads
- verify: json_path(path="$.has_okf", equals="yes")
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::detect_okf_docs`
- tests: `workflows/tests/coder/docs/test_flow.py::test_a_repo_with_no_okf_book_ends_successfully_without_an_agent_turn`

### classify_documentation_context
- sig: `classify_documentation_context(logger: logging.Logger, docs_path: str = "", source_roots: tuple[str, ...] = (), repo_dir: str = "") -> ContextClassification`
- does: treats a readable docs worktree with every source root inside it as `local`
- verify: json_path(path="$.mode", equals="local")
- does: treats external source roots or a non-worktree docs root as `semantic`
- verify: json_path(path="$.mode", equals="semantic")
- does: returns `error` when an existing docs repository cannot be read
- verify: json_path(path="$.mode", equals="error")
- returns: source roots normalized relative to the docs worktree for local OKF context mapping
- verify: json_path(path="$.source_roots", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::classify_documentation_context`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_outside_the_docs_worktree_take_the_semantic_route`

### verify_story_documentation
- sig: `verify_story_documentation(logger: logging.Logger, docs_path: str = "", spec_dir: str = "", author_status: Literal["documented", "not_required", "blocked"] = "blocked", build_status: Literal["", "passed", "invalid"] = "invalid", validation_status: Literal["", "passed", "invalid"] = "invalid", context_mode: Literal["local", "semantic"] = "local", author_nodes: tuple[str, ...] = (), repo_dir: str = "", preexisting: tuple[str, ...] = ()) -> DocumentationGate`
- does: rejects an author status other than `documented` or `not_required`
- verify: json_path(path="$.status", equals="invalid")
- does: requires a passed context build, validation, and readable packet in local mode
- verify: json_path(path="$.status", equals="invalid")
- does: rejects changed production references without direct symbol or file grounding
- verify: json_path(path="$.status", equals="invalid")
- does: runs doctor and attributes affected errors to named nodes or the story's changed anchors
- verify: count(subject="affected documentation doctor findings", equals=0)
- does: spills a complete oversized doctor-error list beside the story specification
- verify: persists(subject="doctor error spill list")
- returns: `passed` only when all required status, grounding, packet, and affected-doctor checks pass
- verify: json_path(path="$.status", equals="passed")
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::verify_story_documentation`
- tests: `workflows/tests/coder/docs/test_flow.py::test_grounding_the_enclosing_unit_grounds_what_is_nested_inside_it`

### documentation_obligations
- sig: `documentation_obligations(logger: logging.Logger, docs_path: str = "", spec_dir: str = "", context_mode: str = "local", build_status: str = "", repo_dir: str = "", preexisting: tuple[str, ...] = ()) -> DocumentationObligations`
- does: returns an empty worklist with an explanatory note in semantic mode
- verify: json_path(path="$.refs", matches=".*")
- does: returns an empty worklist with an unreadable-packet note when local context cannot load
- verify: json_path(path="$.notes", matches=".*")
- does: computes the same ungrounded reference list used by the documentation gate
- verify: count(subject="documentation grounding obligation worklists", equals=1)
- returns: changed production references plus the build-status context for the author prompt
- verify: json_path(path="$.refs", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::documentation_obligations`
- tests: `workflows/tests/coder/docs/test_flow.py::test_the_author_is_handed_the_grounding_worklist_before_it_writes`

### features_root
- sig: `features_root(flow: Workflow) -> str`
- does: reads the detected features root from the recorded `detect_okf_docs` node output
- verify: count(subject="features roots read from detection output", equals=1)
- returns: the features root recorded during setup rather than a separately resolved path
- verify: json_path(path="$.features_root", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/docs.py::features_root`
