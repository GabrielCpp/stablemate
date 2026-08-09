---
type: format
slug: code-workspace-file
title: The .code-workspace file format
---
# The .code-workspace file format

A VSCode [multi-root workspace file](https://code.visualstudio.com/docs/editor/multi-root-workspaces)
that [the workflow kit](concepts/workflow-kit.md) reads (via its shared `_read_workspace_file`
helper — see [resolve_workspace](concepts/workflow-kit.md#resolve_workspace) — parsed as
[JSON-with-Comments](concepts/workflow-kit.md#load_jsonc)) to learn which repos a workflow run
operates on, and optionally clones/updates via
[`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace). The **path** to the file is
never fixed — it is a run's input: a workflow declares a `workspace_file` field and passes it down
to [`resolve_workspace`](concepts/workflow-kit.md#resolve_workspace) /
[`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace) as an argument, so the manifest
a run used is recorded in its checkpoint and settable with `--param`. (A workflow reads no
environment — see [workflows/README.md](../../../workflows/README.md).) Empty falls back to the
single checkout at `repo_dir`, which is what makes a one-repo run need no manifest at all. `folders[].url` and `folders[].branch` are the kit's own optional schema **extension** on
top of VSCode's format — VSCode ignores unknown keys, so a `.code-workspace` file authored with them
still opens as a plain workspace in the editor. Every field beyond `folders` is VSCode's own
(`settings`, `extensions`, …) and is not read.

- file: `*.code-workspace`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_read_workspace_file`

## Fields

Only the key the kit reads; a `.code-workspace` file may carry others (`settings`, `extensions`,
…) which pass through unread.

### folders
- type: `list<Folder>` — required: no — default: `[]` (via `ws.get("folders", [])`)

Each entry is one repo/directory in the workspace, resolved relative to the file's own parent
directory (`ws_dir`).

### Folder.name
- type: `string` — required: no — default: the last path segment of `Folder.path`

The key this folder is addressed by in
[`resolve_workspace`](concepts/workflow-kit.md#resolve_workspace)'s returned map and, when the
folder has a [url](#folderurl), the directory name it is cloned to under `workspace_root` by
[`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace).

### Folder.path
- type: `string` — required: **yes**

A path relative to `ws_dir` (the `.code-workspace` file's parent directory);
[`resolve_workspace`](concepts/workflow-kit.md#resolve_workspace) resolves it to an absolute path
(`(ws_dir / folder["path"]).resolve()`) and looks for that directory's own `agents.yml` to merge in
`template`/`workspace` config. Unused by
[`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace), which addresses folders by
[name](#foldername) under a fixed `workspace_root` instead.

### Folder.url
- type: `string` — required: no — default: unset (folder is not clonable)

The kit's own extension, absent from VSCode's schema. When set,
[`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace) clones or fast-forwards this
folder from `url` into `workspace_root/<name>`. A folder without it is left untouched — it may not
be a git repo at all (e.g. a plain documentation directory whose content only reaches the container
via a bind mount).

### Folder.branch
- type: `string` — required: no — default: `"main"`

The kit's own extension. The branch
[`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace) checks out and hard-resets a
cloned/updated folder to (skipped instead if the folder has unsynced local work — see
`_has_unsynced_work` in [the kit](concepts/workflow-kit.md#checkout_workspace)).

## Consumers

- [`resolve_workspace`](concepts/workflow-kit.md#resolve_workspace) — reads `folders[].name`/`path`
  to build the `{repo_name: {path, ...}}` map every dispatch/config lookup keys off.
- [`checkout_workspace`](concepts/workflow-kit.md#checkout_workspace) — reads
  `folders[].name`/`url`/`branch` to clone/update working trees before a workflow run starts.
- No part of the workhorse engine reads this file. It is read only by
  [`workhorse_workflows.kit`](concepts/workflow-kit.md) — from a node, or from the container
  supervisor's pre-run checkout step.
