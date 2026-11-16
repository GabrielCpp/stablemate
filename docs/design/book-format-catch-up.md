# Format changes reach existing books

Disclosure: before this note I had read the okf-book `catch_up` and `python_book` flows and the
self-sufficient book workflows note. Each part below was checked against "would I have named it
without them"; the claims they carried are listed in 1b.

## 1. Problem

The book format gains a feature most days: a credential that renews itself, list claims, the
fields of a generated form, events, a backstage that runs a service command without starting the
command line. A book written before the feature keeps the old form. Its gates stay green, so
nothing names the gap, and the only way a book moves today is an operator briefing a writer by
hand. The client web book was moved onto self-renewing credentials that way on 2026-11-16, and the
old form had doubled its play time for two days before anyone saw why.

Done: after the format changes, the same command that catches books up with coworker commits
also moves each book onto the format, with nothing by hand. A moved book checks clean, plays
green as a whole, records which format it was judged against, and is committed by the run.

Out of scope: when the catch-up is launched; a coder story moving the books it touches onto the
format (the story's writer reads the current skill already); detecting the old form
mechanically.

## 1b. Claims

1. A book records the app commit it was judged at, and a catch-up reads what changed since
   (self-sufficient book workflows, assumption 1).
2. The writer of a catch-up gets the changed elements and the diff of their files, and the flow
   plays only the journeys of the changed calls (catch_up README).
3. A first book is stamped verified only after check, a whole play and `missing` pass
   (python_book README).

## 2. Parts and concepts

Level 1:

1. **What the format changed.** From the format's own history, names the changes a book has not
   been judged against. Owns the mark a book records and the list of changes after it. Never knows
   who writes or which app the book models. Hands the list to the writer.
2. **Who moves the book.** A writer turn that reads the changes and applies each one that fits
   this book, or says why it does not. Never decides which books are in scope.
3. **The gates.** Check and a whole play. Never knows why the book changed.
4. **The mark.** Records the format the book was judged against, only after the gates pass.

Flow: what the format changed → who moves the book, lap after lap → the gates → the mark, then the
app stamp when the app has nothing stale → commit. It runs inside the catch-up's walk over books,
beside what the app changed, so one writer turn per lap sees both.

The format's history is the history of the writer's own instructions. A change to the format is
a change to what the writer is taught, and every feature so far landed as a commit to that
teaching in the same wave as the tool change. So the list of changes is that history between the
book's mark and now, with each commit's subject and diff.

| Concept | Owns | Never knows |
|---|---|---|
| Format mark | the commit of the writer's instructions a book was last judged against | the app's commit |
| Format delta | the commits and the diff of the instructions after a mark | which apply to a book |
| Derived mark | for a book with no mark, the last instructions commit before the book's own last commit | why the book has none |
| Owner reply | for each change: applied, with the elements touched, or not applicable, with why | the gates |
| Whole play | the verdict of every journey, cell and input | which change caused a failure |

## 3. Invariants

- A mark is written only after check and a whole play pass on the lap that applied the changes.
  Owner: the mark.
- A book whose mark equals the instructions' last commit is never sent to the writer for the
  format. Owner: the format delta.
- The app stamp moves only when the app's stale report is empty after the lap, because a stamp
  hides unjudged app commits. Owner: the stamp of the catch-up, unchanged.

## 4. Forces and patterns

- What changed varies independently along two axes, the app and the format, and one book can be
  behind on both. Pattern: two sources of "what changed" feeding one owner turn and one gate
  sequence; a book is filed when either source names something.
- A format change can touch any journey (a credential reaches every login). Pattern: when the
  format delta is not empty, the run plays the whole book once instead of the targeted journeys.
- The history is long (26 commits, 51 kB of diff in two days). Pattern: the diff is inlined up to
  a cap; past it the subjects are listed and the writer reads each commit itself.

Claim 1 is re-derived for the format: the mark is the format's verified commit. Claim 2 holds for
app changes and is widened by the whole play when the format moved. Claim 3 is unchanged; a book
`python_book` writes or completes also records the mark it was written against (see A2).

## 5. Mapping onto the existing system

| Item | Verdict |
|---|---|
| What the format changed | New, in `okf_book/shared/`: two nodes read the mark and the git history of the ostler-book skill source in the stablemate checkout the workflow runs from |
| Format mark | New file `services/<name>/FORMAT` beside `VERIFIED`, one sha |
| Derived mark | New, same module: `git log -1 --format=%cI -- services/<name>` in the book root, then `git rev-list -1 --before=<date> HEAD -- <skill dir>` in stablemate |
| Who moves the book | Reshape: catch_up's owner prompt gains a format section; `CatchUpReply` gains `format` lines |
| The gates | Reshape: catch_up's `play` plays the whole book when the format delta is not empty |
| The mark | New step after the stamp: write `FORMAT`, inside the committed package |
| Filing | Reshape: catch_up files a book whose stale list is empty but whose format delta is not; `fill` no longer names it current |
| python_book | Reshape: writes `FORMAT` at the instructions' last commit when it stamps, and its owner's first lap gets the format section when the book exists and its mark is behind |

The skill source path is `base-library/library/skills/ostler/ostler-book/`. The workflow finds
the stablemate checkout from its own package location. Reading the delta is a role with one
variant today, the git history of that checkout. A workflow installed outside a git checkout
parks on an operator gate that names the missing history, and never skips the format silently
(A1). A changelog shipped inside the package is the second variant, built when an install
without history exists.

## 5c. Vetted

- `FORMAT` mark. Goal fit: pass, it is the variable "which version of the writer's instructions
  this book was last judged against", one sha per book package, which is the level the owner
  works at. It does not fold into `VERIFIED`, which holds the app's commit per module and is read
  by `stale`. Beneficiary: the operator, who stops briefing migrations; paid for by one whole
  play per migrated book. Reach: every surface kind, since every kind is written from the same
  skill. A story's book lane does not write it, because a story judges only what it touched and
  the mark claims the whole book. Verdict: keep.
- The delta from git history. Aim 7 (it belongs to whoever installs it) prefers a general
  mechanism. Verdict: reshape to a role with the git history as its first variant and a gate
  when it is absent, as written above.
- The derived mark for a book with none. Verdict: keep, with A5.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Operator running catch_up on a book behind only in the app | a targeted run, not a whole play | catch_up tests | api catch-up 58 min wall | a book with no format delta still plays only targeted journeys |
| A current book | skipped, no turn | catch_up tests | 0 turns | a book current on both axes still gets no turn |
| The app stamp | moves only when gates pass | stamp refusal | unchanged | unchanged |

## 6. Slices

1. **The format delta and the mark.** Nodes to read the delta and derive a mark; `FORMAT`
   written by the flow; catch_up files and sends a book behind on the format, plays it whole,
   marks and commits it. Done when: a test on a real git repository with a fake skill history
   files a book whose app is current and whose mark is behind, sends the delta to the owner, plays
   the whole book, writes the mark and commits; and a book current on both is skipped.
2. **python_book records the mark.** Done when a test's first book carries `FORMAT`.
3. **Proof on a real book.** `catch_up` on a client book whose backstage shells out to the
   command line (the change of 6604b0307), with nothing by hand. Done when the run ends with the
   book on `environment.exec`, the whole play green, `FORMAT` committed by the run.

## 7. Assumptions

1. The workflow runs from a stablemate git checkout. Decided: the history comes from that
   checkout. Basis: every run so far launched from a runner worktree. If wrong: section 5, the
   format delta needs the history shipped with the package.
2. A book written or completed by `python_book` is on the current format. Decided: python_book
   writes the mark. Basis: the writer reads the whole current skill. If wrong: the mark is written
   only by catch_up.
3. Every format feature lands as a commit to the skill source. Basis: the 26 skill commits since
   2026-11-14 each teach a tool change of the same wave. If wrong: a feature taught nowhere never
   reaches a book, the same as a writer today.
4. A whole play per format lap is affordable. Basis: 35 to 47 minutes for the largest books,
   once per catch-up. If wrong: a targeted run of the journeys the owner names.
5. A book's last commit is a fair stand-in for the format it was written against. Decided: the
   derived mark is the last skill commit before it. Basis: none measured; a commit that only
   rebuilt an index moves it later than the writing. If wrong: a book is named current on a
   feature it never got, and the next feature's lap does not show the older one either. The
   first `FORMAT` a run writes ends the guess for that book.
