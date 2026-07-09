---
type: format
slug: code-workspace-file
title: The .code-workspace file format
---
# The .code-workspace file format

A VSCode [multi-root workspace file](https://code.visualstudio.com/docs/editor/multi-root-workspaces)
that [scriptutil](concepts/scriptutil.md) reads (via its shared `_read_workspace_file` helper —
see [resolve_workspace](concepts/scriptutil.md#resolve_workspace-build-the-repo-map) — parsed as
[JSON-with-Comments](concepts/scriptutil.md#load_jsonc-json-with-comments-parser)) to learn which repos a workflow run
operates on, and optionally clones/updates via
[`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder). The **path** to the file is
never fixed — each caller passes its own env var name (`WORKSPACE_FILE` by default, or a
workflow-specific one such as `CODER_WORKSPACE`) to
[`resolve_workspace`](concepts/scriptutil.md#resolve_workspace-build-the-repo-map) /
[`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder), which read that env var to find
the file. `folders[].url` and `folders[].branch` are scriptutil's own optional schema
**extension** on top of VSCode's format — VSCode ignores unknown keys, so a `.code-workspace` file
authored with them still opens as a plain workspace in the editor. Every field beyond `folders` is
VSCode's own (`settings`, `extensions`, …) and is not read by scriptutil.

- file: `*.code-workspace`
- code: `workhorse/workhorse/scriptutil.py::_read_workspace_file`

## Fields

Only the key scriptutil reads; a `.code-workspace` file may carry others (`settings`, `extensions`,
…) which pass through unread.

### folders
- type: `list<Folder>` — required: no — default: `[]` (via `ws.get("folders", [])`)

Each entry is one repo/directory in the workspace, resolved relative to the file's own parent
directory (`ws_dir`).

### Folder.name
- type: `string` — required: no — default: the last path segment of `Folder.path`

The key this folder is addressed by in [`resolve_workspace`](concepts/scriptutil.md#resolve_workspace-build-the-repo-map)'s
returned map and, when the folder has a [url](#folderurl), the directory name it is cloned to under
`workspace_root` by [`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder).

### Folder.path
- type: `string` — required: **yes**

A path relative to `ws_dir` (the `.code-workspace` file's parent directory);
[`resolve_workspace`](concepts/scriptutil.md#resolve_workspace-build-the-repo-map) resolves it to an absolute path
(`(ws_dir / folder["path"]).resolve()`) and looks for that directory's own `agents.yml` to merge in
`template`/`workspace` config. Unused by
[`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder), which addresses folders by
[name](#foldername) under a fixed `workspace_root` instead.

### Folder.url
- type: `string` — required: no — default: unset (folder is not clonable)

Scriptutil's own extension, absent from VSCode's schema. When set,
[`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder) clones or fast-forwards this
folder from `url` into `workspace_root/<name>`. A folder without it is left untouched by
`checkout_workspace` — it may not be a git repo at all (e.g. a plain documentation directory whose
content only reaches the container via a bind mount).

### Folder.branch
- type: `string` — required: no — default: `"main"`

Scriptutil's own extension. The branch [`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder)
checks out and hard-resets a cloned/updated folder to (skipped instead if the folder has unsynced
local work — see `_has_unsynced_work` in [scriptutil](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder)).

## Consumers

- [`resolve_workspace`](concepts/scriptutil.md#resolve_workspace-build-the-repo-map) — reads `folders[].name`/`path`
  to build the `{repo_name: {path, ...}}` map every dispatch/config lookup keys off.
- [`checkout_workspace`](concepts/scriptutil.md#checkout_workspace-cloneupdate-every-url-bearing-folder) — reads
  `folders[].name`/`url`/`branch` to clone/update working trees before a workflow graph starts.
- Neither `main.py` nor any other part of the workhorse engine reads this file directly — only
  scriptutil, and only when a script node (or `entrypoint.sh`'s pre-graph checkout step) calls into
  it.

