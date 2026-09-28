# okf_book

The `okf-book` workflow. It writes, repairs and runs one OKF book per surface of an app.

## Map

- `workflow.py`: the composition root of the `okf-book` command. It is the one place a flow is registered.
- `main/`: the flows that write, repair, root and run a book, and the main flow that hands each surface between them.
- `shared/`: the code more than one okf-book flow calls.
