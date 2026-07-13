---
name: stablemate-coder-workflow
description: "Architecture and conventions for the epic-coder workhorse workflow — vars contract, node topology, get_node_output pattern, ostler path integration, and script authoring rules."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/stablemate-coder-workflow/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-coder-workflow/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Coder Workflow — Architecture Reference

Load this skill when reading, modifying, or debugging `agents/workflows/coder/workflow.yaml` or any script under `agents/workflows/coder/scripts/`.

> **Repo modes (mono-repo vs multi-repo), the docs root, and standalone flow
> invocation are documented in `agents/workflows/coder/docs/repo-modes.md`
> (repo-root-relative path — read it before touching any `cwd:`/`add_dirs:` on an
> agent node or any path-resolution script (`resolve-impl-context.py`,
> `resolve-review-context.py`, `find_repo_root`/`find_docs_root`). It documents
> guarantees (and the lack thereof) around the docs root and the affected-repos
> list that are easy to get wrong.**

---

## Workflow Parameters (`vars:`)

Only **user-supplied params** live in `vars:`. Internal state (values produced by script nodes at runtime) is NOT declared here — it is accessed via `get_node_output()`.

| Var | Default | Notes |
|-----|---------|-------|
| `mode` | `"epic"` | `"epic"` = full queue; `"story"` = single story, own branch, no merge |
| `docs_path` | `""` | Docs repo root. Empty → `AGENT_REPO_DIR` (where workhorse launched) |
| `story` | `""` | Story slug (e.g. `"CASE-1234"`). Required in story mode; ignored in epic mode |
| `epic` | `""` | Optional: override which epic to run, skips queue pick |
| `max_qa_reworks` | `"3"` | Max QA-fix cycles per story |
| `max_setup_reworks` | `"2"` | Max setup-fix cycles when QA env is broken |
| `max_ci_reworks` | `"3"` | Max fix_ci cycles per epic PR |
| `max_merge_reworks` | `"2"` | Max fix_merge cycles per epic PR |
| `operator_mode` | `"auto"` | `"auto"` = resolve_* agent stands in; `"human"` = always halt |
| `target_env` | `"local"` | `"local"` = localhost QA; `"dev"` = shared DEV environment |

Override any var at launch:
```
workhorse run coder --params '{"mode":"story","story":"CASE-1234"}'
```

### Standalone flow invocation

Each per-story flow (`dev`, `review`, `qa`) is independently launchable. Its first node
is `prepare_story`, which resolves `story_path`/`spec_dir` from the `story` slug via
ostler — so only the minimal params are needed:

```bash
# QA only, against DEV
workhorse run coder qa --params '{"story":"CASE-1234","target_env":"dev"}'

# Dev (plan + implement) only
workhorse run coder dev --params '{"story":"CASE-1234"}'
```

`docs_path` and `epic` are optional (empty string = derive from CWD / ostler defaults).
Standalone QA runs `clear_qa_evidence` to wipe prior evidence and ensure `spec_dir`
exists before the QA agents start. `plan-context.json` is not required.

---

## Node Output References — `get_node_output()`

**All cross-node references at the parent level MUST use `get_node_output()`**, not bare `{{ var }}` template variables. Bare vars silently collapse to `""` if the upstream node hasn't run; `get_node_output` is explicit about source.

```yaml
# CORRECT — explicit source node
args:
  - "{{ get_node_output('open_pr', 'ci_epic') }}"
  - "{{ get_node_output('prepare_story', 'spec_dir') }}"

# WRONG — implicit flat merge, collapses silently when node hasn't run yet
args:
  - "{{ ci_epic }}"
  - "{{ spec_dir }}"
```

**Exception: inside `flows:`** — flow nodes have their own isolated `vars:` populated from the parent's `args:` block. Prompts and scripts inside a flow use `{{ story_path }}` etc. — that resolves to the flow's local var, which is correct.

### Canonical Source Map

| Key | Source Node | Used by |
|-----|-------------|---------|
| `story_path` | `prepare_story` | dev, review, qa flow args; replan_epic; commit; PR nodes |
| `spec_dir` | `prepare_story` | dev, review, qa flow args; replan_epic; commit; PR nodes |
| `story_slug` | `prepare_story` | dev, qa flow args; commit nodes; qa_give_up; open_story_pr |
| `base_branch` | `branch_story` (story) or `init_base` (epic) | branch_epic, open_pr, open_story_pr |
| `epic` | `select_epic` | branch_epic, open_pr, prune_epic, replan_epic, qa_give_up, commit_story |
| `ci_epic` | `open_pr` | await_ci, push_ci, fix_ci, merge, flag_ci_fail, await_ci_operator, fix_merge, push_merge, flag_merge_fail, await_merge_operator |
| `ci_base` | `open_pr` | await_ci, merge, fix_merge, flag_merge_fail, await_merge_operator |
| `ci_summary` | `await_ci` | fix_ci, flag_ci_fail, await_ci_operator |

**Dual-source pattern** — when a value can come from two nodes depending on mode:
```yaml
# base_branch: story mode → branch_story, epic mode → init_base
- "{{ get_node_output('branch_story', 'base_branch') or get_node_output('init_base', 'base_branch') }}"

# epic: from select_epic, but also overridable from vars
- "{{ get_node_output('select_epic', 'epic') or epic }}"
```

---

## Node Topology

### Story Mode
```
decide_mode → branch_story → prepare_story → dev → review → qa_phase
           → decide_post_sentinel → commit_story_pr → open_story_pr → done
```

### Epic Mode
```
decide_mode → init_base → select_epic → decide_epic → branch_epic
           → select_story → decide_story → prepare_story → dev → review → qa_phase
           → decide_post_sentinel → commit_story → select_story   (loop within epic)
                                 ↘ [story exhausted] prune_epic → open_pr
                                   → CI gate (reset_ci → await_ci → fix_ci loop)
                                   → merge → select_epic          (advance to next epic)
```

### `prepare_story` — the Convergence Node

Both modes pass through `prepare_story` before entering `dev`. It is the **single canonical source** for `story_path`, `spec_dir`, and `story_slug`. Never bypass it.

In story mode: `branch_story` → `prepare_story` (resolves from the `story` slug var)
In epic mode: `select_story` → `decide_story` → `prepare_story` (resolves from `select_story`'s output)

```yaml
- id: prepare_story
  type: script
  script: scripts/prepare-story.py
  args:
    - "{{ docs_path }}"
    - "{{ get_node_output('select_story', 'story_slug') or story }}"
    - "{{ get_node_output('select_story', 'epic') or epic }}"
  outputs:
    - key: story_path
    - key: spec_dir
    - key: story_slug
    - key: story_epic
  next: dev
```

---

## Ostler Path Integration

Ostler resolves slugs to canonical paths. Scripts call it instead of hardcoding path patterns.

### CLI Subcommands
```bash
ostler path spec <slug>              # → docs/specs/<slug>
ostler path story <epic> <slug>      # → docs/epics/<epic>/stories/<slug>/story.md
ostler path branch <slug>            # → story/<slug>
ostler path branch <slug> --epic     # → feat/<slug>
```

All commands respect `docRoots` from `ostler.yml` / `agents.yml`. Pass `-C <docs_root>` when not running from the docs repo CWD.

### In Scripts (Python)
```python
import subprocess, shutil
from pathlib import Path

def _ostler_path(docs_root: Path, subcmd: str, *args: str) -> str:
    cmd = ["ostler", "-C", str(docs_root), "path", subcmd, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""

# Always provide a fallback in case ostler is unavailable
spec_dir = _ostler_path(docs_root, "spec", slug) or f"docs/specs/{slug}"
story_path = _ostler_path(docs_root, "story", epic, slug)
```

---

## `docs_path` Threading

Scripts needing the docs root receive it as an **explicit positional arg**. Use `find_docs_root(docs_path_arg)` from `workhorse.scriptutil` — handles the empty → `AGENT_REPO_DIR` fallback.

```python
from workhorse.scriptutil import find_docs_root

def main():
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    docs_root = find_docs_root(docs_path_arg)
```

Scripts that accept `docs_path` as argv[1]: `prepare-story.py`, `select-next-epic.py`, `select-next-story.py`, `branch-story.sh`.

---

## Script Conventions

### Output Protocol
Every script prints one JSON object to stdout and exits 0. Non-zero exit means a hard failure (e.g. `await_operator.py` exits 2 for "blocked").

```python
def emit(**kwargs) -> None:
    payload = {"has_story": "no", "story_path": "", ...}  # defaults first
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)
```

### Declared Outputs
Every emitted key must be listed under `outputs:` in the workflow node. The engine extracts only declared keys.

```yaml
outputs:
  - key: story_path
  - key: spec_dir
  - key: story_slug
```

### Refuel Keys
`refuel:` on a script node tops up the gas tank when the named key **changes** (real forward progress). Use the key that uniquely identifies the unit of work:

| Node | `refuel:` | Why |
|------|-----------|-----|
| `branch_story` | `story` | Story mode entry: new story starts |
| `select_epic` | `epic` | New epic selected from queue |
| `select_story` | `story_slug` | New story selected within epic |

---

## Flow Contracts

Flows have their own isolated `vars:`. The parent populates them via `args:` using
`get_node_output`. Inside the flow, prompts use plain `{{ story_path }}` — that is the
flow's local var, not the parent context.

**`vars:` default convention:**

| Default value | Meaning |
|---------------|---------|
| `null` (absent/no default) | Required — caller must supply; missing key → error at launch |
| `""` (empty string) | Optional — caller may omit; flow uses `""` if absent |
| any other value | Default used when caller doesn't supply |

```yaml
flows:
  qa:
    name: qa
    start: prepare_story
    vars:
      story: ""          # optional — caller may omit (ostler falls back to CWD)
      docs_path: ""      # optional
      epic: ""           # optional
      operator_mode: "auto"
      target_env: "local"
    nodes:
      - id: prepare_story
        ...
```

The parent passes resolved values back into the flow's args after `prepare_story`:

```yaml
- id: qa_phase
  type: flow
  name: qa
  args:
    story: "{{ get_node_output('prepare_story', 'story_slug') }}"
    docs_path: "{{ docs_path }}"
    epic: "{{ get_node_output('prepare_story', 'story_epic') or get_node_output('select_story', 'epic') or epic }}"
    operator_mode: "{{ operator_mode }}"
    target_env: "{{ target_env }}"
```

---

## Checklist: Adding or Modifying a Node

- [ ] Script prints one JSON object, exits 0 on all normal paths
- [ ] All emitted keys are declared under `outputs:` in the node
- [ ] Args that come from other nodes use `{{ get_node_output('source_node', 'key') }}`
- [ ] Dual-source args use the `or` fallback pattern
- [ ] Script accepts `docs_path` as argv[1] if it needs the docs root; uses `find_docs_root()`
- [ ] Ostler called with `-C <docs_root>` for path resolution; hardcoded fallback provided
- [ ] `refuel:` set if the node marks forward progress (new story/epic)
- [ ] YAML validated after edits: `python3 -c "import yaml; yaml.safe_load(open('workflow.yaml'))"`
