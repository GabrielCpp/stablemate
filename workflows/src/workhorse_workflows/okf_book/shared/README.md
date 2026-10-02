# okf_book shared

The code more than one okf-book machine calls.

## Map

- `agent_files.py`: rendering the repo's agent files from its prompt library before a book commit, so a skill the library changed does not refuse it.
- `blockers.py`: what a run could not finish, collected across its books and handed to the operator after the last.
- `book_commits.py`: the messages a book is committed under, which tell a rerun whether this workflow finished it.
- `book_compilation.py`: compiling the named services' books into a QA plan, and reading the page and node an obligation id names.
- `book_flow.py`: the base every okf-book machine sits on: the repo it writes, the folder its records go in, and how it commits a book.
- `book_run.py`: compiling a service's book, bringing its app's stack up, running every scenario or those some target pages name, and what that run did.
- `book_shape.py`: the shape code gives a book after each turn: each endpoint a server page holds inline moved onto a page of its own, then each page past the size limit carved onto fragment pages.
- `citations.py`: the source files a book's pages cite on their `code:` bullets, with the symbol and the digest each cites.
- `confine.py`: what a writer's turn changed in the tree, read from git before and after it.
- `entries.py`: a service's `entries.md`, the root of its book, one link per entry point, written only by code.
- `imports.py`: which files a file pulls in, resolved to paths inside the repo, and the walk that unions them.
- `metrics.py`: what each turn cost, appended as it finishes, so a run's minutes, tokens and dollars are read per book.
- `page_check.py`: the check the writer runs on its whole book, and the run repeats after it.
- `production.py`: a service's production file set, which is what its entry points reach and what brings its stack up.
- `scenarios.py`: compiling the whole book into a plan, picking the scenarios some target pages name, and reading back what running it did.
- `stack.py`: the files that build and start the stack, which no import reaches and the book still has to describe.
