# okf_book main

The machines that write and run one book per surface. The main flow hands each surface to the others.

## Map

- `exercise_book_flow.py`: the run of a book against the app.
- `reground_book_flow.py`: one turn per changed file a book cites, which names the nodes the change bears on before the owner's turn.
- `flow.py`: the main flow, which sends each surface's owner, runs the gates between its turns, and reports what blocked it.
- `nodes/`: the steps the flows call.
- `write_book_flow.py`: the owner's turn, which holds the whole book and opens on the gates it last failed.
