# Farrier: resolving a generated skill back to its source

> **Status:** phase 1 implemented; follow-on phases proposed. This document records
> the design for making a farrier-generated adapter (a skill/command under
> `.claude/`, `.agents/`, `.github/`) point unambiguously at its editable **source**
> in the central prompt library — so an agent that wants to fix a skill edits the
> source, not the generated copy that the next `make agent-install` overwrites.

## 1. Problem

Every generated skill/command carries a provenance block stamped by
`skill_metadata_block` (`farrier/farrier/install.py`):

```yaml
metadata:
  generated_by: farrier
  source: library/skills/stablemate/ostler/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run …"
```

`source:` is deliberately **machine-independent** — `library_source_path`
(`install.py:275`) anchors it at the last `library/` segment so it is identical on
every machine and stable under `--check`. But that portability is exactly why it is
not directly openable: it says *what* the source is, never *where the library root
lives on this machine*. The `do_not_edit` prose ("edit the source in the central
prompt library") gives an agent no resolvable path.

Farrier already knows how to find the library root — `resolve_library_dir`
(`install.py:111`) resolves it with precedence `--library` > `$FARRIER_LIBRARY_DIR` >
`library_dir` in the home config. The gap is that this resolution was internal to
`install`; nothing let an agent (or a human) run it against a generated file.

## 2. Design principle: portable header + resolver command

"Find the source from the header alone" cannot fully work, because the library root
is inherently **per-machine** (config/env/flag). Baking an absolute path into the
committed frontmatter would be wrong on every other machine, would leak a home-dir
path into version control, and would go stale when the library moves.

So the header stays **portable** (logical, `library/`-anchored coordinates) and the
machine-specific resolution happens through a **command that reuses the same library
resolution as install**. The header *points*; farrier *resolves*.

## 3. Phase 1 — implemented

### 3.1 A `resolve:` field in the provenance block

`skill_metadata_block(source, dest_rel)` now also emits a copy-pasteable command
keyed to the generated file's own repo-relative path:

```yaml
metadata:
  generated_by: farrier
  source: library/skills/stablemate/ostler/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-ostler/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
```

No absolute path is baked in, so the header stays portable and `--check`-stable. An
agent keys on the structured `source` / `resolve` fields, not the human prose.

### 3.2 `farrier source <file>`

```bash
farrier source .claude/skills/stablemate-ostler/SKILL.md
# → /abs/path/to/vigilant-octo/agents/library/skills/stablemate/ostler/SKILL.md
```

Behavior (`_run_source`, `install.py`):

1. Read the file's `metadata.source` via `frontmatter_metadata` — a real YAML parse
   of the front matter (the provenance is a *nested* block, so the flat
   line-splitter in `split_front_matter` is not used).
2. Resolve the library root with `resolve_library_dir(args.library)` — the **same**
   precedence as `install`, so there is zero drift between "where install rendered
   from" and "where source points."
3. Join and verify: `root / metadata.source`. Print the absolute path.

Errors are explicit and actionable:

- the file has no `metadata.source` → "not a farrier-generated skill or command";
- the joined path does not exist → names the expected path and points at
  `farrier config show library_dir` (the generated file may predate a library
  move/rename).

`--library` overrides the resolved root, mirroring `install`.

### 3.3 Tests

- `tests/test_source_command.py` — `frontmatter_metadata` nested-block parsing, a
  successful resolve, and both error paths, driven through `main([...])`.
- `tests/test_provenance_banner.py` — updated for the new signature; asserts the
  `resolve:` field names the generated file's own repo-relative path and that the
  `source:` stays library-anchored (portable).

## 4. Follow-on phases (proposed)

**Phase 2 — richer, still-portable coordinates.** Add optional fields the resolver
and agents can use without a local checkout:

```yaml
  library: vigilant-octo@<git-sha>     # which library, pinned
  source_url: https://github.com/<org>/vigilant-octo/blob/<sha>/library/skills/stablemate/ostler/SKILL.md
  sha256: <hash of the rendered body>
```

`source_url` lets an agent **read** the source with no checkout (WebFetch / `gh`);
`library@<sha>` pins the version so the URL and any diff are reproducible. Still no
absolute path in the committed file.

**Phase 3 — install-time manifest + drift.** `install` already knows the resolved
root, so have it write `.agents/farrier-manifest.json` mapping each generated file →
`{ source, library_root, library@sha, sha256 }`. Payoffs:

- offline resolution without re-running the resolver;
- **drift detection** — fold the `sha256` check into `farrier install --check` so a
  hand-edited generated file (or a source that moved) is reported;
- a record of the exact library version rendered.

The recorded `library_root` is machine-specific, but the manifest lives under
`.agents/` and is regenerated every install — a cache, not a committed contract, so
`farrier source` prefers live resolution and falls back to the manifest.

## 5. Why this shape

- **Portability is the constraint, not an afterthought.** The committed header must
  be identical across machines (it already is, for `--check`); resolution is the
  per-machine part, so it belongs in a command, not the file.
- **One resolution path.** `farrier source` and `install` share
  `resolve_library_dir`, so "where it rendered from" and "where source points" can
  never disagree.
- **Agent-first.** Structured `source` / `resolve` fields (not prose) are what an
  agent reads; `farrier source` turns them into an editable path in one call.
