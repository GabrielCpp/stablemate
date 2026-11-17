# Self-sufficient book workflows

## Problem

An operator who adopts the books at work cannot brief a writer by hand for every service, every
coworker commit and every story. Today three paths still need a person:

- A first book reaches every page, but the depth inside a form (each field tried with each class
  of bad input) came from a writer briefed by hand. That depth found the eight defects of the
  client's web app.
- A coworker's commit with no story leaves the books behind. The client's api book was last
  checked 128 commits ago. Catching up was done by briefing a worker from the stale list.
- A story updates the books of the services it declares. A story whose diff reaches a service it
  did not declare leaves that book behind, and the book's verified commit never moves, so a later
  catch-up redoes the story's work.

Done looks like: each path runs from one command with nothing done by hand, ends with every book
it touched checking clean, playing green and stamped verified at the commit it judged, and its
cost is read per run.

Out of scope: when the catch-up is launched (by hand, nightly or per merge); which agent profile
pays for it; the screen-lists and boundary tracks.

## Parts

1. **What changed.** From the code and a commit, name the book elements whose source changed and
   the new files no element names. Owns the mapping from a diff to books. Never knows who writes.
2. **Who writes.** A workflow turn that receives the elements and the diff of their files and
   updates the book. Never decides which books are in scope.
3. **The gates.** check and a run in every path. A first book also gates on `missing`. A catch-up
   does not, because a book verified before `missing` existed can hold hundreds of old unnamed
   files. There the stamp's own refusal on a changed unnamed file is the gate. Never knows which
   workflow called them.
4. **The stamp.** Records the commit a book was judged at, only after the gates pass. Never runs
   before the gates. A story stamps a book only when the story's commits are all that book
   awaits, because `verified` never refuses on a stale element and a stamp would hide another
   person's unjudged commits.

Flow: what changed → who writes, lap after lap → the gates → the stamp → commit.

No path ends a book failed. The lap cap, a blocked writer and an unreadable stale report each
park on an operator gate, a model resolves it, and the same book resumes. A half-finished book
feeds wrong context to every story and book downstream of it.

## The three paths

| Path | What changed comes from | Writer | Stamp |
| --- | --- | --- | --- |
| First book | `missing` (every file) and the unfilled fields of `check` | okf-book `python_book` | the HEAD it judged |
| Coworker catch-up | `stale` since the book's verified commit, per book | okf-book `catch_up`, one book after another | the HEAD it judged |
| Story | `stale --since <story base>` over every book of the root, joined with the services the story declares | coder's specify and book lanes | the story's commit, after book QA passes, on a book that was current at the story's base |

## Slices

1. **Depth on a first book.** Land the unfilled-field check, so the `check` gate of `python_book`
   refuses a book with a field nobody tried. Proof: `python_book` on the client's web book, with
   nothing by hand, takes the 34 unfilled fields to 0 with the run green.
2. **Coder reaches every touched book.** `ostler book stale --since <rev>`; coder's covered
   services become the declared ones plus every book whose elements the story's diff touched; the
   book lane stamps each covered book verified after book QA. Proof: tests on a fixture repo with a
   story that touches an undeclared service, then the next client story.
3. **Coworker catch-up.** An okf-book flow `catch_up` that walks every book with a non-empty stale
   list, writes from the list and the diff, gates on check and the targeted run, stamps and
   commits per book. Proof: the client's api book, 128 commits behind, caught up with nothing
   by hand.

Read 2026-11-16: all three slices landed. Slice 1 ran green on the client's web book, 34 unfilled
fields to 0, for $33.82 and 753 minutes, with one operator gate. Slice 3 caught the api book up in
one lap for $0.69 and 58 minutes. Slice 2 is proven by a test on a real repository, and its live
proof waits for the next client story.

Read 2026-11-16, wave 3, recorded run by run in `docs/proofs/book-workflows.md`. `python_book`
completed three existing client books and declared the app of a command-line book with nothing
by hand, for $0.64 to $3.35 each. `catch_up` moved a book onto the current format through two
gates whose causes were fixed in the workflow and in ostler. Every run played from a worktree.
The two runs whose owner handed the book to subagents cost about $58 by token count and $62; no other run passed
$5. The owner now writes the book itself, which no run has proven yet.

## Assumptions

1. A book's verified commit is the baseline a catch-up reads. A book with none is a first book.
   Basis: `stale` reads `VERIFIED`; the client's web book has none.
2. The story's base for `--since` is the commit the coder's worktree branched from. Basis: the
   coder records the proven state before the build.
3. A catch-up over many commits costs more than one story and is still cheaper than a first book.
   Basis: the api catch-up cost $0.69 against $33.82 for the web first book, but its 131 commits
   were stories whose book change had already landed. A catch-up over commits with no story is
   still unmeasured.
