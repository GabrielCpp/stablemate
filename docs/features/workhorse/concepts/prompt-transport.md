---
type: concept
slug: prompt-transport
title: Prompt transport for argv-based backends
---
# Prompt transport for argv-based backends

The shared transport keeps a prompt within the safe size of one subprocess argument for the
argv-based [Copilot](copilot-backend.md), [Cline](cline-backend.md), and
[OpenCode](opencode-backend.md) backends. It measures UTF-8 bytes, rather than Python characters,
against a 96 KiB limit. A prompt at or below that limit stays in argv unchanged. A larger prompt
is written to the supplied `prompt.md` artifact and the argv message instead tells the agent to
read that complete file. Copilot supplies the artifact through `--attachment`, OpenCode through
`--file`, and Cline has no attachment flag, so its positional message names the artifact. Claude
and Codex use stdin delivery and do not call these helpers.

The transport fails before spawning when oversized content has no artifact destination. Each
argv-based adapter also checks the finished command so an oversized original prompt cannot
accidentally remain in any argument after command construction.

- code: `workhorse/workhorse/runner/backends/__init__.py::prepare_argv_prompt`
- code: `workhorse/workhorse/runner/backends/__init__.py::ensure_prompt_is_not_in_argv`
- tests: `workhorse/tests/test_backends.py::test_copilot_attaches_a_large_prompt_instead_of_putting_it_in_argv`,
  `workhorse/tests/test_backends.py::test_cline_points_a_large_prompt_at_its_artifact_instead_of_putting_it_in_argv`,
  `workhorse/tests/test_backends.py::test_opencode_attaches_a_large_prompt_instead_of_putting_it_in_argv`

## Methods

### prepare_argv_prompt
- sig: `prepare_argv_prompt(prompt: str, prompt_path: Path | None) -> tuple[str, Path | None]`
- does: measures the prompt's UTF-8 encoding against the 96 KiB inline argv limit
- verify: count(subject="UTF-8 bytes permitted in an inline argv prompt", equals=98304)
- does: returns the original prompt and no attachment when its UTF-8 encoding is at most 96 KiB
- verify: json_path(path="$.attachment", absent=true)
- does: writes an oversized prompt to the supplied artifact path using UTF-8 encoding
- verify: persists(subject="the complete oversized prompt artifact")
- does: replaces an oversized prompt with an instruction naming the artifact and requiring the complete file to be read
- verify: json_path(path="$.prompt", matches="Read it in full and follow it as the user request")
- raises: `BackendInvocationError` when an oversized prompt has no artifact path
- verify: json_path(path="exception.type", equals="BackendInvocationError")
- returns: the bounded argv message and the artifact path when file-backed delivery is used
- verify: json_path(path="$.attachment", matches="prompt.md")
- code: `workhorse/workhorse/runner/backends/__init__.py::prepare_argv_prompt`
- tests: `workhorse/tests/test_backends.py::test_copilot_attaches_a_large_prompt_instead_of_putting_it_in_argv`,
  `workhorse/tests/test_backends.py::test_cline_points_a_large_prompt_at_its_artifact_instead_of_putting_it_in_argv`,
  `workhorse/tests/test_backends.py::test_opencode_attaches_a_large_prompt_instead_of_putting_it_in_argv`

### ensure_prompt_is_not_in_argv
- sig: `ensure_prompt_is_not_in_argv(prompt: str, command: list[str]) -> None`
- does: bypasses the argv-content scan when the prompt's UTF-8 encoding is at most 96 KiB
- verify: json_path(path="$.result", equals="null")
- does: accepts an argv-based command when an oversized prompt is absent from every argument
- verify: absent(subject="oversized prompt text in an argv-based command")
- raises: `RuntimeError` when an oversized prompt remains as part of any command argument
- verify: json_path(path="exception.type", equals="RuntimeError")
- returns: `None` after the argv transport invariant is satisfied
- verify: json_path(path="$.result", equals="null")
- code: `workhorse/workhorse/runner/backends/__init__.py::ensure_prompt_is_not_in_argv`
