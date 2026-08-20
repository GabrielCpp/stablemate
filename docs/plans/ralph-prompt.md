You are one iteration of an overnight ralph loop (the ralph-loop plugin's Stop hook feeds
you this same prompt again after every attempt to stop) implementing a four-plan program in
this worktree. Treat each iteration as if you remember nothing — the ledger and git history
ARE the memory, and they, not your conversation, decide what is done. Work here, on the
current branch, and never touch any other checkout.

## The iteration, exactly

1. Read `docs/plans/overnight-ledger.md`. Pick the FIRST unchecked `- [ ]` item. If there
   are no unchecked items left, write the file `RALPH_DONE` at the repo root containing a
   one-paragraph summary, then output the completion promise `<promise>LEDGER EMPTY</promise>`
   — and output it ONLY when the ledger truly has no unchecked items. Never output it to
   escape the loop.
2. Read the source plan the item references (the ledger's header maps prefixes to plan
   files) and the code it names. Check `git log --oneline -15` — a previous iteration may
   have half-landed this item; continue it, don't restart it.
3. Verify first: if the tree already satisfies the item, tick it as `(pre-existing: <hash>)`
   and commit only the ledger update.
4. Implement ONE ledger item, completely — including its tests. Do not start a second item.
5. Gate: `make lint` from the repo root, plus the affected package's tests
   (e.g. `uv run --package workhorse-workflows pytest workflows/tests -x -q`). A phase-gate
   item runs full `make test`. Do not commit red.
6. Commit per this repo's convention (Conventional Commits, scope = top-level package,
   stage by EXPLICIT path only — never `git add -A`). Split into multiple commits if the
   item genuinely spans concerns. End the message with:
   Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
7. Tick the item in the ledger: `- [x] ... (<short-hash>)`, plus one line of notes if
   anything surprised you. Commit the ledger update (`docs: tick <item-id> in overnight
   ledger`). Then push:
   GIT_TERMINAL_PROMPT=0 timeout 120 git -c credential.helper='!gh auth git-credential' \
     push "https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner).git" \
     "HEAD:refs/heads/$(git branch --show-current)"
8. Stop. The loop feeds this prompt again and the next iteration takes the next item.
   Do exactly ONE ledger item per iteration, even though your session persists.

## If the item cannot be finished

Move it (verbatim, unchecked) under `## Blocked` with a dated one-paragraph reason and what
you tried. Commit that ledger edit and exit — the next iteration takes the next item. Never
delete an item, never weaken its done-criteria to make it pass, never mark red work done.

## Hard rules (from AGENTS.md — they are load-bearing)

- `os.environ`/`os.getenv` are prohibited under `workflows/src/workhorse_workflows/`.
- A workflow never gives up: budget exhaustion escalates to `Await`, never `WorkflowFailed`.
- This repo is public: no private overlay project names anywhere, ever.
- ruff AND ty at zero findings; fix, don't suppress. `# type: ignore` is inert — ty's
  spelling is `# ty: ignore[rule]`.
- Never push over the `git@` remote; only the HTTPS+gh command above.
- Long-running measurement commands (replay/devlane baselines): run them bounded with
  `timeout`, and if one exceeds ~90 min, record partial results and what remains, then exit
  the iteration — do not sit silent for hours.
