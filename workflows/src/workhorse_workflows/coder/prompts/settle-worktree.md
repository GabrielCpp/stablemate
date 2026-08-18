# Coder Workflow — Settle Worktree Stage

You are running the **settle worktree** stage for story `{{ story_slug }}`. The story's work is
finished, but the working tree still holds changes that are **not in a commit**. The workflow does
not commit on your behalf — you commit as you go — so this is the one lap you get to record what
you left behind before the run parks for a human.

Story file: `{{ story_path }}`
Spec directory: `{{ spec_dir }}`
Epic: `{{ epic }}`

## What is still uncommitted

Each line is `<package>:<path within that package's checkout>`. Paths that were already dirty when
the story started, and that this story never touched, have been removed — everything below is
either yours or a stranger's.

```
{{ dirty_paths }}
```

## Steps

1. **Read the diff before you stage anything.** `git status` and `git diff` in each package that
   appears above, plus `git diff --staged` for what is already in the index.
2. **Decide, per path, whether this story wrote it.** Compare against `{{ story_path }}` and the
   plan in `{{ spec_dir }}`. Work that implements, tests or documents this story is yours. A file
   you cannot account for — a stray build artifact, an editor scratch file, someone else's
   half-finished edit — is **not** yours to commit under this story's name.
3. **Commit what belongs to this story, one commit per package.** Stage by explicit path — never
   `git add -A`, `git add .` or `git commit -a`, which sweep in whatever else is in the tree.
   Use a Conventional Commit subject scoped to the package it lands in:

   ```
   <type>(<scope>): <lowercase imperative description>

   Epic: {{ epic }}
   Story: {{ story_slug }}
   ```

   `<type>` is `feat` for new behaviour, `fix` for a repaired defect, `refactor` for a rename, move
   or extraction, `test` / `docs` / `chore` for the rest — pick by what the change *is*, not how
   large it is. `<scope>` is the package being released, not the module inside it. Subject ≤ 72
   characters, no capital first word, no trailing period. Keep the `Epic:` and `Story:` trailers
   exactly as spelled above; they are how the run record ties a commit back to its story.
4. **Leave anything that is not yours exactly where it is.** Do not commit it, do not revert it, do
   not stash it. Name it in `notes` and return `blocked` — an operator decides what happens to work
   you did not write.
5. **Do not push, open a pull request, or switch branches** — the workflow owns those.
6. **Re-check before you answer.** `git status --porcelain` in each package should be empty except
   for the paths you are explicitly handing to the operator.

## Output

Respond with JSON only:

```json
{"status": "settled|blocked", "notes": "<what you committed, per package — or which paths you left and why they are not yours>"}
```

`settled` means every path above is either committed or was deliberately left, and the tree holds
nothing of this story's that is not recorded. `blocked` means something on that list needs a human:
you cannot tell whose it is, committing it would be wrong, or the commit itself failed. Return
`blocked` rather than guessing — the run parks for an operator, which costs ten minutes; a commit
of someone else's work under this story's name costs considerably more.
