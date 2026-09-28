---
name: codebase-map
description: "Keep a map of where code lives and use it before writing any. Every directory that holds source carries a `## Map` section with one line per file and subdirectory saying what it owns. Before adding code, read the map and search for an existing owner of the concept. Place new code where a line says its concern lives, or add the line. Update the map in the same change as any add, rename, move or delete. Ships a pre-commit check that fails when a map and its directory disagree. Load when starting a project, creating a file or directory, moving or deleting code, deciding where new code goes, or when the codebase-map check fails a commit."
tags: [architecture, standards, docs]
hooks:
  - stage: pre-commit
    run: scripts/check_map.py
---

# Codebase map

An agent finds code by reading and searching. A helper that exists under a name it did
not think to search for is invisible to it, so it writes a second one. A file whose
purpose nobody wrote down gets whatever the next task needs, and it grows into three
concerns. The map prevents both. It is the first place to look for an owner, and it
forces a decision about where each new file belongs at the moment the file is created.

## Where the map lives

- Each directory that holds source has a `## Map` section in its own `AGENTS.md`. Agents
  load that file when they work in the directory, so the map is in front of the reader
  at the moment it matters.
- A `## Map` section in the directory's `README.md` also counts. The check reads
  `AGENTS.md` first. Use `README.md` for the root of a project whose readers start
  there.
- When farrier generates a directory's `AGENTS.md`, the map goes in that directory's
  `README.md`. Farrier folds the README into the generated file, so agents still see
  it.
- The rest of the file may carry what the directory is for and what does not belong in
  it. Keep that short. The map is the part the check enforces.

## What a line says

```markdown
## Map

- `invoice.py`: turns an order and a tax table into a priced invoice.
- `tax_table.py`: loads tax rates per region and answers a rate for a date.
- `render/`: formats an invoice as PDF or HTML. Knows nothing about pricing.
```

- One line per source file and per subdirectory that holds source. Test files,
  `__init__.py` and dot directories are left out.
- The line names what the file **owns**: the decision or the data it is the single place
  for. It does not describe how the code works or list its functions.
- Write it for a reader who is about to add code. They should be able to tell from the
  line whether their change belongs in this file.
- A line that needs "and" to join two concerns means the file holds two. Split the file,
  or write down why it stays one.

## Before writing code

1. Read the map of the directory the change lands in. Read the maps above it when the
   concept could live elsewhere.
2. Search for the concept under every name it might have. Search both the maps and the
   code. A grid walk, a retry loop, a date parser or a spacing rule usually already
   exists.
3. When an owner exists, use it or extend it. A near-copy with one parameter changed is
   a second owner, and the two drift apart.
4. When no owner exists, decide where the new code goes before writing it.

## Placing new code

- New code goes in the file whose map line names its concern.
- When no line fits, the code is a new concern. Create a file for it and add its line in
  the same change.
- When the right file would need its line rewritten to cover the new code, the file is
  about to hold two concerns. Put the code in a new file instead.
- A helper that two directories need goes in the lowest directory above both of them,
  with a map line there. It never goes in one of the two with the other importing
  across.

## In the same change

- Adding, renaming, moving or deleting a file updates the map line in the same commit.
- Changing what a file owns updates its line. The check cannot see this case, because
  the file name stays the same. Rewrite the line whenever the diff changes what the file
  decides.
- After a rename, search every `AGENTS.md`, `README.md` and doc for the old name and fix
  each hit.

## Starting a project

Write the root map before the first file of code. List the directories the design calls
for, each with one line. Then add each directory's own map when its first file lands. A
line written before the code is a decision about the design. A line written after is a
description of whatever happened.

## The check

`scripts/check_map.py` runs at pre-commit through farrier's hook runner. It checks every
directory where the commit adds or deletes a source file, and every directory whose map
file the commit changes. It fails when:

- a directory has no `## Map` section;
- a source file or source subdirectory has no line;
- a line names something that no longer exists;
- a line has no description.

A directory the commit does not touch is not checked, so an existing codebase adopts the
map one directory at a time. Run the whole tree with:

```bash
python3 .claude/skills/<installed-name>/scripts/check_map.py --all
```

`.agent-checks.toml` tunes the check for a repo:

```toml
[codebase-map]
extensions = [".py", ".ts"]
exclude = ["gen/*", "migrations/*"]
```

`extensions` replaces the default list of source extensions. `exclude` adds path
patterns to skip, such as generated code.

When the check fails, fix the map. Do not exclude the directory to get the commit
through. An exclusion is for code no person writes.
