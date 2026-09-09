---
type: concept
slug: native-git-diff-documentation-scope
title: Native git diff documentation scope
---
# Native git diff documentation scope

The two method nodes cite the same native-run diff helper, not alternative implementations.
`groom/groom/localfs.py::git_diff` resolves `base/repo_dir` first and, when that fails and no
`repo_dir` was supplied, falls back to the base's first-discovered checkout; it runs
`git -c safe.directory=* -C <checkout> diff HEAD` locally and returns stdout, or `""` when no
checkout resolves, the process cannot launch, or the command fails or times out.

Use [the local-filesystem module method](groom-localfs-module.md#git-diff) for the adapter's
public API alongside its Docker-volume sibling (`list-files`, `read-file`, `write-file`, …), and
use [the workspace diff data method](../workspace-diff-data.md#method-git-diff-native) for its
role as the native-run producer in the sidecar/fallback diff handoff. These views are
complementary; source code records no preference or deprecation between them because they name
the one callable at different documentation scopes.

- rule: choose the node by the documentation question, not as an implementation selection; both describe the same native-run `git_diff` callable
