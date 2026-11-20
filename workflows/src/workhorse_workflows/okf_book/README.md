# okf_book

The `okf-book` workflow. It writes the Python book of one service under `services/<name>/`.

## Launch

Run it from the root of the repository whose book it writes:

```bash
workhorse-okf-book run python_book --run-id book-api-1 --profile claude --params '{...}'
```

`python_book` writes a first book, and a bare `run` starts it too. `catch_up` updates the books that exist, and its section is below. The parameters of `python_book` are `service`, `kind`, `source_folder` and `stack_copy`.

The owner writes lap after lap until three of the book's own commands exit 0, in this order: `check`, `run` and `missing`. `missing` lists the tracked files under `source_folder` that no element names through its `source` and no `App(ignore=...)` pattern covers, so a book cannot stop while the app holds a file it does not answer for.

When the three pass, the run stamps each of the book's modules with `ostler book verified`, which records the app's HEAD as the commit the book was judged at. A refused stamp sends the owner another lap with what the command printed, under the same lap cap. The stamp file sits inside the book's package, so the commit of `services/<name>/` carries it, and a later `catch_up` finds the book verified instead of naming it a first book.

Each time it stamps, `python_book` also writes `services/<name>/FORMAT`, the commit of the `ostler-book` skill's source the book was written against. The commit of the book carries it. A book that exists when the run starts and is behind that commit gets the commits and their diff in the owner's prompt on every lap. The `format_history` parameter names the checkout that holds the skill's history. Empty, it is the checkout the workflow package runs from. A history that cannot be read waits on an operator gate, except at the stamp of a first book, which is on the current format by construction: that run writes no `FORMAT`, commits, and says in its outcome that the mark was not written and why.

`--profile` names the agent profile of the home config. `--dry-run` walks the graph with the agent turns stubbed.

Attend a run through groom, never through its launch log: `groom wait --run <run-id> --until blocked,ended` returns at the next operator gate, and `workhorse-okf-book control --run <run-dir> questions|answer --text …|resume` answers it.

## Catch up

`catch_up` brings every book up to the app's HEAD after commits no story answered. Run it from the root of the repository that holds the books, like `python_book`:

```bash
workhorse-okf-book run catch_up --run-id catch-up-1 --profile claude --params '{"stack_copy": "evening", "services": ["api"]}'
```

`stack_copy` names the stack copy the targeted run plays on, as for `python_book`. `services` names the books to catch up. An empty list means every service book under the book root. A named service with no book is a first book.

The run reads `ostler book stale` for each module of each book and sorts the books:

- A book with nothing stale and a green `ostler book check` in each module is named current and skipped.
- A book with no verified commit is named a first book for `python_book` and not written.
- A book whose stale report cannot be read, or whose check exits 3 where nothing is stale, waits on an operator gate with the command, its exit code and what it printed. The answer reads it again.
- A book with nothing stale and a red check is filed for the format. The check's findings, each naming the element and what to state, are the owner's work list.
- Each other book is filed on the run's work list and worked one at a time. A resume skips the stale reads of the books already filed or settled, and takes first the book it stopped on.

What says a book is behind the book format is the tool's own check, which every user has: `ostler book check <module> --app <root>` exits non-zero and prints one finding per thing the format now asks for. The run reads it for each module of a book with nothing stale. A book whose stale report names something is filed as today, and a red check there is what its first lap meets.

The history of the `ostler-book` skill is optional context. When the workflow runs from a stablemate checkout, or `format_history` names one, and the history reads, the owner also gets the commits and their diff. The `FORMAT` file of the book's package holds the commit of the skill's source the book was last judged against, and a book with none gets a derived mark: the last commit to the skill's source before the book's own last commit. When there is no checkout or the history cannot be read, the run goes on without it, logs that the format history was not available, and writes no `FORMAT` file. It never waits on an operator gate for that.

A filed book gets an owner turn per lap. The turn receives the changed elements with their files, the changed files no element names, and the diff of those files between the book's verified commit and HEAD. It updates the book and names each endpoint or interaction it added. When a stack copy is given, it plays the journeys of the changed and added calls with `run --only` on that copy before it replies, and repairs the book until the run reads 0 fail. A run that exits 3 is reported in `blocked`. Then the run plays the book's own commands in order: `check` and `run --only` with the endpoints and interactions the report named and the turn added. Then it stamps the book with `ostler book verified`, which refuses while a file or function changed since the verified commit is named by no element and no ignore pattern, or a pointer names a file that is gone. The run never asks for the whole book's `missing` list, since completing a book is the job of `python_book`. A red command or a refused stamp starts the next lap with what it printed, up to three laps. A book still red after the third lap waits on an operator gate, as `python_book` does, with the red command's output as the question. The answer resumes the same book: the owner takes one more lap and its prompt receives the answer. The cap applies again after that lap, so each further red command asks again. An owner turn that replies `blocked` waits on an operator gate the same way, and the answer reaches the owner's next turn on the same book. A book is never failed, and the run never marks a work-list row blocked. A book waiting on the operator is left uncommitted and unstamped.

The owner of a book filed for the format gets the check's findings in its prompt as its work list: it states what each finding asks from what the app's code shows, and never invents a statement to silence one. A book with the history available also gets the commits and says in `format`, one line per commit, what it applied.

The run never plays a whole book. A book filed for the format plays what the owner's edits select: `ostler book affected <module> --app <code root> --since <the app's HEAD> --out <run_dir>/book-plan/<module>` reads the working tree against HEAD, so its diff is the owner's uncommitted edits. The run plays the plan's `only` with `run --only` and each journey of `by_journey` with `run --partial --journey`, as two plays when both exist, and `--fresh-data` on the first play of a module. A plan with nothing selected plays nothing. A whole plan plays only its `only` and `by_journey`, and its reason is recorded as owed to a whole play. A whole play belongs to a scheduled `ostler book run <module>`, not to catch-up. A book that is current in the app is not stamped with `verified`. A book that moved onto the format has `FORMAT` written at the head of the skill's history after its gates pass, when that history was available.

A book whose commands pass and whose stamp lands has the app's HEAD recorded, and the agent files are rendered. The run then commits `services/<name>/` with the subject `docs(<name>): catch the <name> book up with the app`. A book filed only for the format is committed with `docs(<name>): move the <name> book onto the current book format`, and the subject drops the second name, then the rest, where the service's name is long.

The run ends on one line per book: current, caught up with its laps, elements changed and endpoints added, a first book, or moved onto the format, such as `web: moved onto the format in 2 laps, check 2 findings to 0, notes 64 to 22, played 4 calls and 6 journeys green, owed to a whole play: <reason>`. That line gives the check's findings and notes before the first lap and after the last, the calls and journeys played with the play's exit, and the owed reason when there is one. The records of each book sit under `<run_dir>/outcomes/`.
