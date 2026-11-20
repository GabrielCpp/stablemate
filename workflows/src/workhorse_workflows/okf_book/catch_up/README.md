# okf_book catch_up

The catch-up flow, which brings each service book up to the app's HEAD from its stale report.

`flow.py` holds the machine, `nodes.py` the fill, the diff and the records of each book, `report.py` the reading of `ostler book stale`, and `prompts/update-book.md` the owner's turn. The gates are the nodes of `shared/book_gates.py`, which `python_book` calls too. The operator gates, their questions and the lap cap are in `shared/book_flow.py`, and both flows hand the operator's answer to the owner's next turn through the same method.

A book is filed when its stale report names anything, or when it names nothing and `ostler book check` is red in one of its modules. The check is the tool's own, so a user who installed the tool has it. A book filed for the red check alone is filed for the format: its findings, each naming the element and what to state, are the owner's work list, and the commit says so in its subject. `fill` runs the check of each module of a book with nothing stale, and records the findings and notes it counted as the before of the outcome line.

`shared/book_format.py` reads the history of the `ostler-book` skill from a stablemate checkout. That history is optional context: with it the owner also gets the commits and their diff, and `FORMAT` is written at the head of the history after the gates pass. Without a checkout, or when the history cannot be read, the run goes on, logs that the format history was not available, and writes no `FORMAT`. No operator gate waits on it.

`play` never plays a whole module. For a book filed for the format, `python_book_affected` runs `ostler book affected` with `--since` at the app's HEAD, so the diff is the owner's uncommitted edits, and `play` runs `--only` on the plan's calls and `--partial --journey` on its journeys, `--fresh-data` on the first play of a module. A whole plan plays what it names and records its reason as owed. A scheduled `ostler book run <module>` is where a whole play belongs. `catch_up_move` keeps the numbers of that play and the check after the last lap, and the outcome line of the book carries them with the check's before.

A book whose service declares no app has no verified commit by construction: `ostler book stale` prints `<name> declares no app` and exits 2, and `report.py` reads that exact line as a first book, with no operator gate.
