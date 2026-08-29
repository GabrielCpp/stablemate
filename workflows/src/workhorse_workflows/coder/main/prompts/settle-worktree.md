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
3. **Commit what belongs to this story, one commit per package**, each commit carrying
   `Epic: {{ epic }}` and `Story: {{ story_id }}` as trailers, spelled exactly so — the run
   record ties a commit back to its story through them.
4. **Leave anything that is not yours exactly where it is.** Do not commit it, do not revert it, do
   not stash it. Name it in `notes` and return `blocked` — an operator decides what happens to work
   you did not write.
5. **Do not push, open a pull request, or switch branches** — the workflow owns those.
6. **Re-check before you answer.** `git status --porcelain` in each package should be empty except
   for the paths you are explicitly handing to the operator.

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
