---
type: concept
slug: qa-evidence-ignore-rules
title: QA-evidence ignore rules
---
# QA-evidence ignore rules

The staged-files gate keeps its run evidence out of version control through a managed block in the
target repository's `.gitignore`. The block is installed only when the generated gate is among the
repository outputs; it names evidence artifacts rather than ignoring every directory named `qa`,
so a source package with that name remains visible. This module no longer installs or wires the
hook itself; [hook manager wiring](hook-manager-wiring.md) owns that contract.

- code: `farrier/farrier/hooks.py`
- tests: `farrier/tests/test_qa_evidence_ignore.py`

## Fields

### GATE_SCRIPT
- type: `str`
- default: `scripts/check_staged_files.py`
- required: true
- semantics: the gate path is `scripts/check_staged_files.py` relative to the rendered skill directory
- verify: json_path(path="$.gate_path", equals="scripts/check_staged_files.py")
- semantics: the gate's presence among install outputs enables the QA ignore block
- verify: count(subject="QA gate output path", equals=1)
- code: `farrier/farrier/hooks.py::GATE_SCRIPT`

### QA_GITIGNORE_BLOCK
- type: `tuple[str, ...]`
- default: a fenced block containing the QA evidence patterns
- required: true
- semantics: the managed block starts with `# >>> farrier: QA evidence (generated) >>>`
- verify: count(subject="QA evidence ignore block start marker", equals=1)
- semantics: the managed block contains patterns for `**/qa/**/steps/`, `**/qa/**/asserts/`, `**/qa/**/traces/`, `**/qa/**/videos/`, `**/qa/**/screenshots/`, `**/qa/qa-run.ndjson`, `**/qa/run-manifest.json`, and `**/qa/qa-session.json`
- verify: count(subject="QA evidence ignore patterns", equals=8)
- semantics: the managed block ends with `# <<< farrier: QA evidence <<<`
- verify: count(subject="QA evidence ignore block end marker", equals=1)
- code: `farrier/farrier/hooks.py::QA_GITIGNORE_BLOCK`

## Methods

### ensure_qa_gitignore
- sig: `ensure_qa_gitignore(repo: Path) -> bool`
- does: reads `<repo>/.gitignore` as UTF-8 when it exists, otherwise treats the existing content as empty
- does: removes the old marker-bounded QA block when both markers are present
- does: preserves repository ignore lines before and after an existing complete QA block
- does: replaces a complete existing QA block with the current `QA_GITIGNORE_BLOCK`, or appends the current block after the existing text when no complete pair of markers exists
- does: writes the resulting `.gitignore` as UTF-8 with exactly one trailing newline
- returns: `true` when the desired `.gitignore` differs from the existing text and is written
- returns: `false` when the existing text already equals the desired text and no write is needed
- verify: persists(subject="QA evidence ignore block in .gitignore")
- verify: unchanged(subject="repository ignore rules outside the QA block")
- code: `farrier/farrier/hooks.py::ensure_qa_gitignore`
- tests: `farrier/tests/test_qa_evidence_ignore.py::test_the_ignore_block_names_artifacts_not_the_qa_directory`
- tests: `farrier/tests/test_qa_evidence_ignore.py::test_the_ignore_block_is_idempotent_and_keeps_the_repo_rules`
- tests: `farrier/tests/test_qa_evidence_ignore.py::test_the_block_is_refreshed_in_place_when_it_changes`
