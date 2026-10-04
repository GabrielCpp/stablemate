# okf_book main

The machines that write, repair and run one book per surface. The main flow hands each surface to the others.

## Map

- `exercise_book_flow.py`: the run of a book against the app.
- `lead_lap_flow.py`: the lead turn that reads a failed run whole and names the side of each group of failed checks.
- `reground_book_flow.py`: one turn per changed file a book cites, which names the nodes the change bears on before any page is repaired.
- `flow.py`: the main flow, which takes each surface from its book to the run and reports what blocked it.
- `nodes/`: the steps the flows call.
- `repair_book_flow.py`: the repair of a book too large for one writer, a batch of pages per turn.
- `root_book_flow.py`: the entries page code writes and commits for a book HEAD holds none for.
- `settle_repair_turn_flow.py`: the put-back and commit of one repair turn's changes, under a message a small model writes from the diff.
- `write_book_flow.py`: the one writer turn that writes a whole book.
