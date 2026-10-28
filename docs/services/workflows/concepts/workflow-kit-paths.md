---
type: concept
slug: workflow-kit-paths
title: Workflow kit paths
---
# Workflow kit paths

This module resolves the consuming repository and the documentation repository from explicit
workflow inputs. An explicit `repo_dir` is authoritative; when it is empty, repository discovery
starts at the resolved current working directory and walks toward the filesystem root. Repository
discovery itself consults no environment variable, so that result is visible to and checkpointable
by callers. The documentation root is the exception: it defers to the docs home of the repository, which is
the artifacts dir when that repository is a member of any workspace in the home config.

- code: `workflows/src/workhorse_workflows/kit/paths.py` @34f070621a86
- rule: epics, backlogs and specs live at the top level of the artifacts dir, so the documentation root holds `docs/` and never an `epics/` folder
- detail: [Artifacts layout and the docs home](../../ostler/concepts/artifacts-layout.md)

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
- code: `workflows/src/workhorse_workflows/kit/paths.py::find_repo_root` @34f070621a86

### find_docs_root

The documentation-root resolver returns the artifacts dir when the repository holding `repo_dir`
is a member of any workspace in the home config, matched by folder, worktree main folder or origin
URL. Otherwise it resolves the repository root from `repo_dir`.

- sig: `find_docs_root(repo_dir: str | Path = "") -> Path`
- does: when the repository holding `repo_dir` is a member of any workspace in the home config, returns the artifacts dir
- verify: count(subject="workspace documentation root resolution result", equals=1)
- does: otherwise returns the repository root resolved from `repo_dir` or the current working directory discovery rules
- verify: count(subject="default documentation root resolution result", equals=1)
- returns: the selected documentation root as an absolute `Path`
- verify: count(subject="absolute documentation root result", equals=1)
- code: `workflows/src/workhorse_workflows/kit/paths.py::find_docs_root` @34f070621a86
