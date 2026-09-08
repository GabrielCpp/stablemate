---
type: concept
slug: file-content-documentation-scopes
title: File content documentation scopes
---
# File content documentation scopes

`file_content` is one HTTP handler, not two implementations to choose between. It projects the
requested path's language before doing any I/O, calls `getFile` over the connected sidecar RPC
helper, falls back to the workspace volume file-content reader (or its native equivalent) only
when the sidecar returns no result and the selected workflow has a known workspace volume, and
returns the result as `{"path", "content", "lang"}`.

Read [file-content](groom-app-module.md#method-file-content) for the handler's place in the
[groom app module](groom-app-module.md): its route wiring, its exception behavior, and its role
among the module's other endpoint handlers. Read [workspace file content data
method-file_content](../workspace-file-content-data.md#method-file_content) when the question
concerns the [workspace file content data](../workspace-file-content-data.md) format it produces:
the language-projection and sidecar-versus-fallback algorithm, the empty-state and error rules,
and how it relates to the sibling producer method (`_rpc_get_file`) that ultimately supplies the
sidecar-side text. Neither view supersedes the other; each describes the same current handler
from its own documented scope.

- code: groom/groom/app.py::file_content
- rule: use the app-module node for the handler's endpoint contract and use the format node for the file-content-producing algorithm and data shape; neither is preferred because both describe one current handler.
