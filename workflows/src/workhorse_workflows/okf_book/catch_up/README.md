# okf_book catch_up

The catch-up flow, which brings each service book up to the app's HEAD from its stale report.

`flow.py` holds the machine, `nodes.py` the fill, the diff and the records of each book, `report.py` the reading of `ostler book stale`, and `prompts/update-book.md` the owner's turn. The gates are the nodes of `shared/book_gates.py`, which `python_book` calls too. The operator gates, their questions and the lap cap are in `shared/book_flow.py`, and both flows hand the operator's answer to the owner's next turn through the same method.

A book is filed when its stale report names anything or when its format delta is not empty. `shared/book_format.py` reads the delta from the `FORMAT` mark of the book, or derives the mark when the book has none, and `play` plays the whole book when the delta is not empty. The commit of a book filed only for the format says so in its subject.

A book whose service declares no app has no verified commit by construction: `ostler book stale` prints `<name> declares no app` and exits 2, and `report.py` reads that exact line as a first book, with no operator gate.
