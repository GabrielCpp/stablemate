---
type: concept
slug: diff-documentation-scopes
title: Diff documentation scopes
---
# Diff documentation scopes

`diff` is one HTTP handler, not two implementations to choose between. It requests `getDiff`
over the connected sidecar RPC helper, falls back to the workspace volume diff reader (or its
native equivalent) only when the sidecar returns no data and the workflow has a known workspace
volume, and returns the result as `{"diff": "<unified diff text>"}`.

Read [diff](groom-app-module.md#method-diff) for the handler's place in the [groom app
module](groom-app-module.md): its route wiring, its exception behavior, and its role among the
module's other endpoint handlers. Read [workspace diff data method-diff](../workspace-diff-data.md#method-diff)
when the question concerns the [workspace diff data](../workspace-diff-data.md) format it
produces: the sidecar-versus-fallback algorithm, the empty-state and error rules, and how it
relates to the sibling producer methods (`_rpc_get_diff`, `_git_diff`, the Docker and native
`git_diff` functions) that ultimately supply its diff text. Neither view supersedes the other;
each describes the same current handler from its own documented scope.

- code: groom/groom/app.py::diff
- rule: use the app-module node for the handler's endpoint contract and use the format node for the diff-producing algorithm and data shape; neither is preferred because both describe one current handler.
