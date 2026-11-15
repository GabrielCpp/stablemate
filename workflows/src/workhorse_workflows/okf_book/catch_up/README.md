# okf_book catch_up

The catch-up flow, which brings each service book up to the app's HEAD from its stale report.

`flow.py` holds the machine, `nodes.py` the fill, the diff and the records of each book, `report.py` the reading of `ostler book stale`, and `prompts/update-book.md` the owner's turn. The gates are the nodes of `shared/book_gates.py`, which `python_book` calls too. The operator gates, their questions and the lap cap are in `shared/book_flow.py`, and both flows hand the operator's answer to the owner's next turn through the same method.
