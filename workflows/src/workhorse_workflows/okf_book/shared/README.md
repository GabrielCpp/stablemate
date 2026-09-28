# okf_book shared

The code more than one okf-book machine calls.

## Map

- `blockers.py`: what a run could not finish, collected across its books and handed to the operator once, after the last.
- `book_commits.py`: the subjects a book is committed under, which tell a rerun whether this workflow finished it.
- `book_compilation.py`: compiling the named services' books into a QA plan, and reading the page and node an obligation id names.
- `book_flow.py`: what every okf-book machine reads, which is the repo it writes and the folder its records go in.
- `book_run.py`: compiling a service's book, bringing its app's stack up, running every scenario, and what that run did.
- `citations.py`: the source files a book's pages cite on their `code:` bullets, with the symbol and the digest each cites.
- `confine.py`: what a writer's turn changed in the tree, read from git before and after it.
- `entries.py`: a service's `entries.md`, the root of its book, one link per entry point, written only by code.
- `imports.py`: which files a file pulls in, resolved to paths inside the repo, and the walk that unions them.
- `metrics.py`: what each turn cost, appended as it finishes, so a run's minutes, tokens and dollars are read per book.
- `page_check.py`: the check the writer runs on its whole book, and the run repeats after it.
- `production.py`: a service's production file set, which is what its entry points reach and what brings its stack up.
- `scenarios.py`: compiling the whole book into a plan, and reading back what running it did.
- `stack.py`: the files that build and start the stack, which no import reaches and the book still has to describe.
