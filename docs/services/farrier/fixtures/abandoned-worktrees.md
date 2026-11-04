---
type: fixture
slug: abandoned-worktrees
title: Abandoned worktrees
---
# Abandoned worktrees

A directory named by `dir` holding a repository `acme` and its linked worktrees: `landed` has
nothing unmerged, `dirty` has an uncommitted file, `ahead` has an unmerged commit, `standing` is
locked, `busy` has a process in it, `fresh` was cut just now and `gone` has lost its folder. Every
worktree but `fresh` was last touched in 2020.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### repository

- kind: seed
- run: git init -q -b main "$dir/acme" && git -C "$dir/acme" config user.email test@example.com && git -C "$dir/acme" config user.name Test && git -C "$dir/acme" commit -q --allow-empty -m one
- working-directory: scenario:

### worktrees

- kind: seed
- run: for name in landed dirty ahead standing busy gone fresh; do git -C "$dir/acme" worktree add -q -b "$name" "../$name"; done
- working-directory: scenario:

### work

- kind: seed
- run: touch "$dir/dirty/scratch.md" && git -C "$dir/ahead" -c user.email=test@example.com -c user.name=Test commit -q --allow-empty -m feature && git -C "$dir/acme" worktree lock ../standing && rm -rf "$dir/gone"
- working-directory: scenario:

### age

- kind: seed
- run: for name in landed dirty ahead standing busy; do git_dir="$(git -C "$dir/$name" rev-parse --absolute-git-dir)"; touch -d 2020-01-01 "$git_dir/HEAD" "$git_dir/index" "$git_dir/logs/HEAD"; done
- working-directory: scenario:

### occupant

- kind: seed
- run: (cd "$dir/busy" && nohup sleep 120 &) >/dev/null 2>&1
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir/landed" && test ! -d "$dir/gone"
- working-directory: scenario:
