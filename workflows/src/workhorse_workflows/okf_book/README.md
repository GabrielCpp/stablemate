# okf_book

The `okf-book` workflow. It writes the Python book of one service under `services/<name>/`.

## Launch

Run it from the root of the repository whose book it writes:

```bash
workhorse-okf-book run python_book --run-id book-api-1 --profile claude --params '{...}'
```

`python_book` writes a first book, and a bare `run` starts it too. `catch_up` updates the books that exist, and its section is below. The parameters of `python_book` are `service`, `kind`, `source_folder` and `stack_copy`.

The owner writes lap after lap until three of the book's own commands exit 0, in this order: `check`, `run` and `missing`. `missing` lists the tracked files under `source_folder` that no element names through its `source` and no `App(ignore=...)` pattern covers, so a book cannot stop while the app holds a file it does not answer for.

`--profile` names the agent profile of the home config. `--dry-run` walks the graph with the agent turns stubbed.

Attend a run through groom, never through its launch log: `groom wait --run <run-id> --until blocked,ended` returns at the next operator gate, and `workhorse-okf-book control --run <run-dir> questions|answer --text …|resume` answers it.

## Catch up

`catch_up` brings every book up to the app's HEAD after commits no story answered. Run it from the root of the repository that holds the books, like `python_book`:

```bash
workhorse-okf-book run catch_up --run-id catch-up-1 --profile claude --params '{"stack_copy": "evening", "services": ["api"]}'
```

`stack_copy` names the stack copy the targeted run plays on, as for `python_book`. `services` names the books to catch up. An empty list means every service book under the book root. A named service with no book is a first book.

The run reads `ostler book stale` for each module of each book and sorts the books:

- A book with nothing stale is named current and skipped.
- A book with no verified commit is named a first book for `python_book` and not written.
- Each other book is filed on the run's work list and worked one at a time. A resume skips the stale reads of the books already filed or settled, and takes first the book it stopped on.

A filed book gets an owner turn per lap. The turn receives the changed elements with their files, the changed files no element names, and the diff of those files between the book's verified commit and HEAD. It updates the book and names each endpoint or interaction it added. Then the run plays the book's own commands in order: `check` and `run --only` with the endpoints and interactions the report named and the turn added. Then it stamps the book with `ostler book verified`, which refuses while a file or function changed since the verified commit is named by no element and no ignore pattern, or a pointer names a file that is gone. The run never asks for the whole book's `missing` list, since completing a book is the job of `python_book`. A red command or a refused stamp starts the next lap with what it printed, up to three laps. A book still red after the third lap is failed and the run goes on to the next book. It is left uncommitted and unstamped.

A book whose commands pass and whose stamp lands has the app's HEAD recorded, and the agent files are rendered. The run then commits `services/<name>/` with the subject `docs(<name>): catch the <name> book up with the app`.

The run ends on one line per book: current, caught up with its laps, elements changed and endpoints added, a first book, or failed with the gate that stayed red. The records of each book sit under `<run_dir>/outcomes/`.
