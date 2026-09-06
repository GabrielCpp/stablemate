---
type: concept
slug: workflow-kit-paths
title: Workflow kit paths
---
# Workflow kit paths

This module resolves the consuming repository and the documentation repository from explicit
workflow inputs. An explicit `repo_dir` is authoritative; when it is empty, repository discovery
starts at the resolved current working directory and walks toward the filesystem root. No
environment variable is consulted, so the result is visible to and checkpointable by callers.

- code: `workflows/src/workhorse_workflows/kit/paths.py`

## Methods

### find_repo_root

The repository resolver accepts either the workflow's explicit repository input or the process
working directory as its discovery origin. A directory is recognized as a repository root when it
contains `agents.yml` or `.git`.

- sig: `find_repo_root(repo_dir: str | Path = "") -> Path`
- does: when `repo_dir` is non-empty, resolves that path and returns it without filesystem-marker discovery
- verify: count(subject="explicit repository root resolution result", equals=1)
- does: when `repo_dir` is empty, checks the resolved current working directory before each ancestor and selects the first directory containing `agents.yml` or `.git`
- verify: count(subject="ancestor repository root resolution result", equals=1)
- does: when no directory in the current directory's ancestry contains either marker, uses the resolved current working directory
- verify: count(subject="repository discovery fallback result", equals=1)
- returns: the selected repository root as an absolute `Path`
- verify: count(subject="absolute repository root result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/paths.py::find_repo_root`

### find_docs_root

The documentation-root resolver gives an absolute `docs_path` precedence. A relative
`docs_path` is interpreted beneath the repository resolved from `repo_dir`; an empty
`docs_path` resolves to that repository root directly.

- sig: `find_docs_root(docs_path: str = "", repo_dir: str | Path = "") -> Path`
- does: when `docs_path` is absolute and non-empty, resolves and returns that path without joining it to the repository root
- verify: count(subject="absolute documentation root resolution result", equals=1)
- does: when `docs_path` is relative and non-empty, joins it to `find_repo_root(repo_dir)` before resolving the result
- verify: count(subject="relative documentation root resolution result", equals=1)
- does: when `docs_path` is empty, returns the repository root resolved from `repo_dir` or the current working directory discovery rules
- verify: count(subject="default documentation root resolution result", equals=1)
- returns: the selected documentation root as an absolute `Path`
- verify: count(subject="absolute documentation root result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/paths.py::find_docs_root`
