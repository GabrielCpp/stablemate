---
type: concept
slug: qa-hygiene-gates
title: QA hygiene gates
---
# QA hygiene gates

The [Coder QA flow](../flows/coder-qa.md) runs these deterministic gates during finalization. The
first tidies screenshots without risking committed assets; the second rejects fabricated IDs and
unreconciled placeholders in newly added shipped source. Both resolve the code repository from
the supplied `repo_dir`, rather than from the process working directory.

- code: `workflows/src/workhorse_workflows/coder/qa/nodes/hygiene.py`
- tests: `workflows/tests/coder/qa/test_hygiene.py`
- detail: [coder QA subflow](coder-qa-subflow.md)

## Methods

### flush_root_screenshots
- sig: `flush_root_screenshots(logger: logging.Logger, spec_dir: str = "", repo_dir: str = "") -> ScreenshotFlush`
- does: identifies only regular files directly under the resolved repository root whose extension is `.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`, case-insensitively
- verify: count(subject="root image files considered by screenshot hygiene", equals=1)
- does: leaves root images already tracked by git in place and reports their count as `kept_tracked`
- verify: count(subject="tracked root images left in place", equals=1)
- does: creates `<spec_dir>/qa/` below the repository root and moves each untracked root image there
- verify: created(subject="the QA directory below the repository root")
- verify: count(subject="untracked root images moved into the QA directory", equals=1)
- does: chooses a `-1`, `-2`, and later suffix when a destination filename already exists, never overwriting it
- verify: unchanged(subject="pre-existing QA screenshots", except_fields=[])
- does: leaves untracked images in place and logs a warning when `spec_dir` is blank, resolves to the repository root or above it, the destination cannot be created, or an individual move fails
- verify: count(subject="unmovable root screenshots retained", equals=1)
- returns: `ScreenshotFlush` with `flushed`, `kept_tracked`, and a human-readable `notes` summary
- verify: json_path(path="$.notes", matches=".+")
- returns: all counts remain zero when no matching root image exists
- verify: json_path(path="$.flushed", equals=0)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/hygiene.py::flush_root_screenshots`

### check_sentinel_ids
- sig: `check_sentinel_ids(logger: logging.Logger, story_slug: str = "", repo_dir: str = "") -> QaResult`
- does: resolves the trunk base and reads only added lines from the `base_ref..HEAD` diff with zero context
- verify: count(subject="added source diff lines scanned by the sentinel gate", equals=1)
- does: scans only `.go`, `.ts`, `.tsx`, `.js`, and `.jsx` additions, excluding test files and pure comment lines
- verify: count(subject="eligible shipped-source additions scanned", equals=1)
- does: rejects an eligible added line containing an all-zero UUID
- verify: count(subject="all-zero UUID sentinel additions rejected", equals=1)
- does: rejects an eligible added line containing an all-zero hexadecimal or UUID string
- verify: count(subject="all-zero hexadecimal or UUID sentinel additions rejected", equals=1)
- does: rejects an eligible added line containing a `falls back until|when|if X exists` stub
- verify: count(subject="fallback stub sentinel additions rejected", equals=1)
- does: rejects an eligible added line containing a `TODO until` marker
- verify: count(subject="TODO-until sentinel additions rejected", equals=1)
- does: rejects an eligible added line containing a `placeholder until` marker
- verify: count(subject="placeholder-until sentinel additions rejected", equals=1)
- does: rejects an eligible added line containing a `stub until` marker
- verify: count(subject="stub-until sentinel additions rejected", equals=1)
- does: returns a failed result listing each matching filename, target line number, sentinel description, and up to 120 characters of trimmed content
- verify: json_path(path="$.status", equals="failed")
- does: returns a passed result with a skip note when the trunk base cannot be determined or diff execution fails
- verify: json_path(path="$.status", equals="passed")
- does: returns a passed result when the diff has no added lines or no eligible sentinel matches
- verify: json_path(path="$.status", equals="passed")
- returns: `QaResult` with status `passed` or `failed` and notes describing the scan, skip, or findings
- verify: json_path(path="$.status", matches="passed|failed")
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/hygiene.py::check_sentinel_ids`
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_through_every_gate`

### _added_lines
- sig: `_added_lines(root: Path, base_ref: str) -> list[tuple[str, int, str]]`
- does: returns one tuple per parsed added diff line containing the patched filename, post-image line number, and line content without its trailing newline
- verify: count(subject="parsed added diff lines with target locations", equals=1)
- does: returns an empty list for an empty diff, a malformed patch, renames, and binary-only changes
- verify: count(subject="unsupported diff forms safely ignored", equals=1)
- code: `workflows/src/workhorse_workflows/coder/qa/nodes/hygiene.py::_added_lines`
- tests: `workflows/tests/coder/qa/test_hygiene.py::test_added_lines_carry_their_target_line_numbers`
- tests: `workflows/tests/coder/qa/test_hygiene.py::test_a_diff_committed_as_a_fixture_does_not_forge_a_filename`
- tests: `workflows/tests/coder/qa/test_hygiene.py::test_renames_and_binaries_add_no_lines`
- tests: `workflows/tests/coder/qa/test_hygiene.py::test_no_diff_and_a_malformed_diff_both_yield_nothing`

The remaining helpers are internal policy seams: `_tracked_names` limits git tracking checks to
top-level names; `_dest_dir` rejects unsafe or unusable specification directories;
`_unique_target` prevents destination collisions; `_is_test_file` recognizes the configured test
filename markers; and `_is_comment_line` applies the comment exemption only to Go and JavaScript
dialects. `PatchSet` and `UnidiffParseError` are third-party parsing dependencies, while the kit
path and git helpers and the result models are documented in their own workflow nodes.
