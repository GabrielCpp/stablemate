---
type: concept
slug: workflow-kit-credentials
title: Workflow kit credentials
---
# Workflow kit credentials

The credentials kit is the workflow package's narrow exception to the rule that workflow code
does not read environment variables: credentials stay out of checkpointed parameters, logs, and
telemetry. Its scoped environment helper supplies a freshly minted value only while a callee
needs it, then restores the caller's prior process state even when that callee fails.

- The module reads GitHub credentials in a fixed precedence order. `github_token` first consults
  the repository's `agents.yml` at `workflow.githubTokenEnv` (also accepting the snake-case
  spelling), then `GH_TOKEN`, then `GITHUB_TOKEN`; `api_token` instead consults `GH_TOKEN` and
  then `WORKHORSE_GIT_TOKEN`. An unset or empty source produces an empty string, which callers
  interpret as an unauthenticated or best-effort path.
- `scoped_env` and `scoped_envs` are the only in-process write path. They expose minted secrets to
  a callee through the process environment without returning the values from a workflow node.
  A single binding restores the prior value, or removes the variable if it did not exist; the
  multi-binding form applies every mapping entry and unwinds them in reverse order. The single
  binding is not safe to nest for the same variable name.
- `has_git_credential` checks only whether the configured Git credential variable is non-empty.
  It does not return the secret; Git expands the variable inside its credential helper.

- code: `workflows/src/workhorse_workflows/kit/credentials.py`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_sets_the_value_for_the_block_and_clears_it_after`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_restores_a_prior_value_rather_than_clearing_it`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_restores_even_when_the_block_raises`

## Fields

### GITHUB_FALLBACKS

- type: tuple of environment-variable names
- default: `("GH_TOKEN", "GITHUB_TOKEN")`
- required: true
- semantics: fallback order for `github_token` after any repository-specific variable
- verify: count(subject="GitHub fallback environment names", equals=2)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::GITHUB_FALLBACKS`

### GIT_CREDENTIAL_ENV

- type: string environment-variable name
- default: `"WORKHORSE_GIT_TOKEN"`
- required: true
- semantics: default variable whose presence enables the transient Git credential helper
- verify: count(subject="default Git credential environment name", equals=1)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::GIT_CREDENTIAL_ENV`

## Methods

### _configured_token_env

- sig: `_configured_token_env(root: Path) -> str | None`
- does: reads `agents.yml` below `root` and returns the trimmed configured GitHub token variable name
- does: returns `None` when the file is absent, unreadable, invalid YAML, or has no configured workflow token variable
- returns: the string from `workflow.githubTokenEnv` or `workflow.github_token_env`, when present
- verify: count(subject="configured token environment lookup result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::_configured_token_env`

### github_token

- sig: `github_token(root: str | Path) -> str`
- does: resolves the first non-empty token from the repository-configured variable, `GH_TOKEN`, and `GITHUB_TOKEN`, in that order
- returns: the selected token value, or an empty string when all candidate variables are unset or empty
- verify: count(subject="GitHub token resolution result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::github_token`

### api_token

- sig: `api_token() -> str`
- does: selects `GH_TOKEN` before `WORKHORSE_GIT_TOKEN` for an unconfigured API client
- returns: the selected token value, or an empty string when both variables are unset or empty
- verify: count(subject="API token resolution result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::api_token`

### scoped_env

- sig: `scoped_env(name: str, value: str) -> Iterator[None]`
- does: sets `name` to `value` for the duration of the context block
- does: removes `name` when the block exits if it had no prior value
- does: restores the prior value of `name` when the block exits if one existed
- does: restores or removes `name` when the block exits through an exception
- verify: count(subject="scoped environment restoration cases", equals=4)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::scoped_env`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_sets_the_value_for_the_block_and_clears_it_after`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_restores_a_prior_value_rather_than_clearing_it`
- tests: `workflows/tests/test_kit_credentials.py::test_scoped_env_restores_even_when_the_block_raises`

### scoped_envs

- sig: `scoped_envs(values: Mapping[str, str]) -> Iterator[None]`
- does: applies each name/value pair as a scoped environment binding
- does: restores all bindings in reverse insertion order when the block exits
- returns: a no-op context for an empty mapping
- verify: count(subject="multi-variable scoped environment bindings", equals=1)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::scoped_envs`

### has_git_credential

- sig: `has_git_credential(name: str = GIT_CREDENTIAL_ENV) -> bool`
- does: checks whether `name` contains a non-empty value without returning that value
- returns: `true` when the variable is non-empty and `false` otherwise
- verify: count(subject="Git credential presence result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/credentials.py::has_git_credential`
