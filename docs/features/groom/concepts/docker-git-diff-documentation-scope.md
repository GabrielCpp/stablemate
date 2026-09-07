---
type: concept
slug: docker-git-diff-documentation-scope
title: Docker git diff documentation scope
---
# Docker git diff documentation scope

The three method nodes cite the same Docker-volume diff helper, not alternative implementations.
`groom/groom/docker_io.py::git_diff` uses an explicit `repo_dir` when supplied, otherwise resolves
the first repository in the volume; it returns the git container's stdout or an empty string when
no repository resolves or the command fails.

Use [the Docker I/O module method](groom-docker-io-module.md#git-diff) for the adapter's public
API, [the workspace-volume diff reader method](workspace-volume-diff-reader.md#git-diff) for the
fallback reader's request context and read-only behavior, and [the workspace diff data method](../workspace-diff-data.md#method-git_diff)
for its role in the data handoff. These views are complementary; source code records no preference
or deprecation among them because they name the one callable at different documentation scopes.

- code: groom/groom/docker_io.py::git_diff
- rule: choose the node by the documentation question, not as an implementation selection; all three describe the same Docker-volume `git_diff` callable
