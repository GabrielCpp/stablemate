---
type: concept
slug: coder-shared-okf-context
title: Coder shared OKF context
---
# Coder shared OKF context

The coder's OKF context helpers turn one or more repository diffs and the current feature book
into the packet consumed by the documentation and QA gates. A successful packet is memoized only
when all packet files exist, their bytes match the digests the stamp recorded, and the recorded
fingerprint still matches the repository state and the arguments that shaped the build. Validation independently checks the packet and cannot report
`passed` when the build that produced it was invalid.

- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::__all__` @a8cbd64f2928
- rule: the QA lane owns the packet's scope. The QA turn reads the packet through
  `ostler qa context-show` and never runs `ostler qa context --base`, because a packet built
  from a new base drops the story scope and charges the story with every other story's
  obligations. A `stale-plan` finding is repaired in the plan. A `stale-context` finding is
  repaired with `ostler qa context --refresh`, which rebuilds the packet from the base and
  excluded paths the lane recorded in it. The lane rebuilds the packet again after every QA
  turn before it validates the plan.
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`

## Fields

### PACKET_FILES
- type: `tuple[str, ...]`
- default: `qa-okf-context.json | qa-okf-context.md | qa-okf-verification-index.json`
- required: true
- semantics: names the three files that must all exist before a memo can be reused
- verify: count(subject="OKF packet files", equals=3)
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::PACKET_FILES` @a8cbd64f2928

### STAMP_FILE
- type: `str`
- default: `qa-okf-context.stamp.json`
- required: true
- semantics: names the JSON stamp recording the packet fingerprint, each packet file's SHA-256, status, notes, and raw Ostler result
- verify: count(subject="OKF packet stamp filename", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::STAMP_FILE` @a8cbd64f2928

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
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::worktree_signature` @a8cbd64f2928
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
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::fingerprint` @a8cbd64f2928
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_the_stamp_records_the_key_the_next_visit_recomputes`

### recall
- sig: `recall(spec_path: Path, key: str | None) -> OkfContextResult | None`
- does: returns `None` when the memo key is absent or any required packet file is missing
- verify: absent(subject="unusable OKF memo")
- does: returns `None` when the stamp cannot be parsed or its fingerprint differs from the requested key
- verify: absent(subject="mismatched or unreadable OKF memo")
- does: returns `None` when any packet file's bytes differ from the SHA-256 the stamp recorded
- verify: absent(subject="OKF memo over a rewritten packet")
- returns: the recorded status, notes, and Ostler payload when the complete stamp matches
- verify: json_path(path="$.status", matches="passed|invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::recall` @a8cbd64f2928
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_an_unreadable_stamp_rebuilds_rather_than_guessing`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_missing_packet_file_rebuilds_even_with_a_matching_stamp`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_packet_rewritten_after_the_build_rebuilds_even_with_a_matching_stamp`

### remember
- sig: `remember(spec_path: Path, key: str | None, result: OkfContextResult) -> None`
- does: writes the fingerprint, each packet file's SHA-256, status, notes, and Ostler payload when a keyed result has status `passed`
- verify: persists(subject="passing OKF memo stamp")
- does: leaves no stamp when the key is absent or the result status is not `passed`
- verify: absent(subject="failed OKF memo stamp")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::remember` @a8cbd64f2928
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_failed_build_is_not_memoized`

### build_okf_context
- sig: `build_okf_context(logger: logging.Logger, spec_dir: str = "", story_file: str = "", services_root: str = "", source_roots: tuple[str, ...] = (), base: str = "HEAD", head: str = "WORKTREE", repo_dir: str = "", preexisting: tuple[str, ...] = (), story_sources: tuple[StorySource, ...] = (), story_refs: tuple[str, ...] = ()) -> OkfContextResult`
- does: resolves the documentation repository from `repo_dir`, or the artifacts dir while a workspace is active before computing the packet inputs
- verify: count(subject="resolved OKF documentation roots", equals=1)
- does: replaces the `TRUNK` base with the branch's nearest merge base with trunk before computing the packet inputs
- verify: count(subject="TRUNK bases resolved to a merge base", equals=1)
- does: excludes pre-existing unchanged worktree paths from the mapped story diff, unioning `untouched_since` across the docs root and every `story_sources` checkout rather than the docs root alone
- verify: count(subject="pre-existing story paths excluded", equals=0)
- does: when the base is `TRUNK` and no `story_sources` are given, narrows the merge-base diff to the paths this story's own commits touched, excluding paths only other stories on the same branch changed
- verify: count(subject="story-scoped TRUNK bases narrowed by story_refs", equals=1)
- does: when the merge base with trunk is HEAD itself, as under commit delivery on trunk, diffs from the parent of the earliest commit reachable from HEAD that carries one of `story_refs` as its `Story:` trailer, so a story whose commits already landed still owes obligations for them
- verify: count(subject="on-trunk story bases moved to the story's first commit", equals=1)
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
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::build_okf_context` @a8cbd64f2928
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_repeat_visit_reuses_the_packet_byte_for_byte`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_different_spec_dir_does_not_read_the_other_ones_memo`
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_multi_repository_context_is_grouped_and_invalidated_by_source_edits`
- tests: `workflows/tests/coder/shared/test_okf_story_scope.py::test_on_trunk_a_story_owes_obligations_for_its_own_landed_commits`
- tests: `workflows/tests/coder/shared/test_okf_story_scope.py::test_on_trunk_a_story_with_no_commit_yet_maps_only_the_worktree`

### validate_okf_context
- sig: `validate_okf_context(logger: logging.Logger, spec_dir: str = "", build_status: str = "invalid", repo_dir: str = "") -> OkfContextResult`
- does: resolves the documentation repository from `repo_dir`, or the artifacts dir while a workspace is active
- verify: count(subject="resolved OKF validation roots", equals=1)
- does: validates the packet at `spec_dir` through Ostler
- verify: count(subject="validated OKF context packets", equals=1)
- returns: `passed` only when Ostler validation succeeds and `build_status` is `passed`
- verify: json_path(path="$.status", equals="passed")
- returns: `invalid` when Ostler validation fails or the build status is not `passed`
- verify: json_path(path="$.status", equals="invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::validate_okf_context` @a8cbd64f2928
- tests: `workflows/tests/coder/docs/test_flow.py::test_sources_inside_the_docs_worktree_take_the_local_route`
