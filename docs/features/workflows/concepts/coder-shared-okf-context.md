---
type: concept
slug: coder-shared-okf-context
title: Coder shared OKF context
---
# Coder shared OKF context

The coder's OKF context helpers turn one or more repository diffs and the current feature book
into the packet consumed by the documentation and QA gates. A successful packet is memoized only
when all packet files exist and the recorded fingerprint still matches the repository state and
the arguments that shaped the build. Validation independently checks the packet and cannot report
`passed` when the build that produced it was invalid.

- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::__all__`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`

## Fields

### PACKET_FILES
- type: `tuple[str, ...]`
- default: `qa-okf-context.json | qa-okf-context.md | qa-okf-verification-index.json`
- required: true
- semantics: names the three files that must all exist before a memo can be reused
- verify: count(subject="OKF packet files", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::PACKET_FILES`

### STAMP_FILE
- type: `str`
- default: `qa-okf-context.stamp.json`
- required: true
- semantics: names the JSON stamp recording the packet fingerprint, status, notes, and raw Ostler result
- verify: count(subject="OKF packet stamp filename", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::STAMP_FILE`

## Methods

### worktree_signature
- sig: `worktree_signature(root: Path, base: str, head: str, ignore: tuple[str, ...] = ()) -> str | None`
- does: includes the resolved base and HEAD revisions in the repository signature
- verify: count(subject="worktree revision inputs", equals=2)
- does: includes the tracked diff and the byte digests of untracked files when `head` is `WORKTREE`
- verify: count(subject="worktree change sources", equals=2)
- does: excludes every repository-relative path listed in `ignore` from the tracked and untracked inputs
- verify: count(subject="ignored worktree paths", equals=1)
- does: returns a SHA-256 signature for a readable Git worktree
- verify: json_path(path="$.signature", matches="^[0-9a-f]{64}$")
- returns: `None` when Git cannot answer the requested repository query
- verify: absent(subject="worktree signature after Git query failure")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::worktree_signature`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_editing_a_tracked_file_rebuilds`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_brand_new_untracked_file_rebuilds`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_committing_rebuilds`

### fingerprint
- sig: `fingerprint(signature: str | None, arguments: dict[str, object]) -> str | None`
- does: returns `None` when the worktree signature is `None`
- verify: absent(subject="memo fingerprint after missing worktree signature")
- does: combines the worktree signature and sorted packet-shaping arguments into a JSON payload
- verify: count(subject="memo fingerprint inputs", equals=2)
- returns: a SHA-256 key for a non-None signature and its arguments
- verify: json_path(path="$.fingerprint", matches="^[0-9a-f]{64}$")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::fingerprint`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_the_stamp_records_the_key_the_next_visit_recomputes`

### recall
- sig: `recall(spec_path: Path, key: str | None) -> OkfContextResult | None`
- does: returns `None` when the memo key is absent or any required packet file is missing
- verify: absent(subject="unusable OKF memo")
- does: returns `None` when the stamp cannot be parsed or its fingerprint differs from the requested key
- verify: absent(subject="mismatched or unreadable OKF memo")
- returns: the recorded status, notes, and Ostler payload when the complete stamp matches
- verify: json_path(path="$.status", matches="passed|invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::recall`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_an_unreadable_stamp_rebuilds_rather_than_guessing`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_missing_packet_file_rebuilds_even_with_a_matching_stamp`

### remember
- sig: `remember(spec_path: Path, key: str | None, result: OkfContextResult) -> None`
- does: writes the fingerprint, status, notes, and Ostler payload when a keyed result has status `passed`
- verify: persists(subject="passing OKF memo stamp")
- does: leaves no stamp when the key is absent or the result status is not `passed`
- verify: absent(subject="failed OKF memo stamp")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::remember`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_failed_build_is_not_memoized`

### build_okf_context
- sig: `build_okf_context(logger: logging.Logger, spec_dir: str = "", story_file: str = "", features_root: str = "", source_roots: tuple[str, ...] = (), base: str = "HEAD", head: str = "WORKTREE", docs_path: str = "", repo_dir: str = "", preexisting: tuple[str, ...] = (), story_sources: tuple[StorySource, ...] = ()) -> OkfContextResult`
- does: resolves the documentation repository from `docs_path` and `repo_dir` before computing the packet inputs
- verify: count(subject="resolved OKF documentation roots", equals=1)
- does: excludes pre-existing unchanged worktree paths from the mapped story diff
- verify: count(subject="pre-existing story paths excluded", equals=0)
- does: groups source scopes sharing repository checkout, base, and head into one source repository
- verify: count(subject="grouped OKF source repositories", equals=1)
- does: reuses the on-disk packet when its complete file set and fingerprint match the current inputs
- verify: count(subject="OKF packet rebuilds on unchanged inputs", equals=1)
- does: invokes Ostler context generation with repository provenance when external story sources are present
- verify: count(subject="external-source OKF context calls", equals=1)
- does: invokes Ostler context generation with parsed source roots when no external story sources are present
- verify: count(subject="local-source OKF context calls", equals=1)
- returns: `passed` when Ostler reports success, otherwise `invalid`, with diagnostic notes and raw payload
- verify: json_path(path="$.status", matches="passed|invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::build_okf_context`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_repeat_visit_reuses_the_packet_byte_for_byte`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_different_spec_dir_does_not_read_the_other_ones_memo`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_multi_repository_context_is_grouped_and_invalidated_by_source_edits`

### validate_okf_context
- sig: `validate_okf_context(logger: logging.Logger, spec_dir: str = "", build_status: str = "invalid", docs_path: str = "", repo_dir: str = "") -> OkfContextResult`
- does: resolves the documentation repository from `docs_path` and `repo_dir`
- verify: count(subject="resolved OKF validation roots", equals=1)
- does: validates the packet at `spec_dir` through Ostler
- verify: count(subject="validated OKF context packets", equals=1)
- returns: `passed` only when Ostler validation succeeds and `build_status` is `passed`
- verify: json_path(path="$.status", equals="passed")
- returns: `invalid` when Ostler validation fails or the build status is not `passed`
- verify: json_path(path="$.status", equals="invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::validate_okf_context`
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`
