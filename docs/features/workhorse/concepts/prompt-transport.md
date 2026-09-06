---
type: concept
slug: prompt-transport
title: Prompt transport for argv-based backends
---
# Prompt transport for argv-based backends

Argv-based adapters use one bounded transport for prompts. Content at or below 96 KiB stays in
the command argument; larger content is written to the supplied prompt artifact and replaced by
an instruction that names that file. Claude and Codex use stdin instead, so they do not call these
helpers.

- code: `workhorse/workhorse/runner/backends/__init__.py::prepare_argv_prompt`
- tests: `workhorse/tests/test_backends.py::test_copilot_attaches_a_large_prompt_instead_of_putting_it_in_argv`,
  `workhorse/tests/test_backends.py::test_cline_points_a_large_prompt_at_its_artifact_instead_of_putting_it_in_argv`

## Methods

### prepare_argv_prompt
- sig: `prepare_argv_prompt(prompt: str, prompt_path: Path | None) -> tuple[str, Path | None]`
- does: returns the original prompt and no attachment when its UTF-8 encoding is at most 96 KiB
- does: writes an oversized prompt to `prompt_path` and returns a bounded file-reading instruction plus that path
- raises: `BackendInvocationError` when an oversized prompt has no artifact path
- returns: a prompt safe for one argv argument and the artifact path when file-backed delivery is used
- verify: json_path(path="$.prompt", matches=".{1,}")
- code: `workhorse/workhorse/runner/backends/__init__.py::prepare_argv_prompt`

### ensure_prompt_is_not_in_argv
- sig: `ensure_prompt_is_not_in_argv(prompt: str, command: list[str]) -> None`
- does: accepts an argv that does not contain an oversized prompt
- raises: `RuntimeError` when an oversized prompt remains in any command argument
- returns: `None` after the transport invariant is satisfied
- verify: absent(subject="oversized prompt text in an argv-based command")
- code: `workhorse/workhorse/runner/backends/__init__.py::ensure_prompt_is_not_in_argv`
