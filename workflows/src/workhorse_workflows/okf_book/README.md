# okf_book

The `okf-book` workflow. It writes, repairs and runs one OKF book per surface of an app.

## Map

- `workflow.py`: the composition root of the `okf-book` command. It is the one place a flow is registered.
- `main/`: the flows that write, repair, root and run a book, and the main flow that hands each surface between them.
- `shared/`: the code more than one okf-book flow calls.

## Launch

Run it from the root of the repository whose book it writes. Each surface is a service
slug, its kind and its entry folder:

```bash
workhorse-okf-book run --run-id book-api-1 --profile claude \
  --params '{"surfaces":[{"service":"api","kind":"http","entry":"api"}]}'
```

- `service`: the book's folder under `docs/features/`.
- `kind`: `cli`, `http`, `web` or `mobile`. It picks the writer's branch of the skill and the driver the scenarios run on.
- `entry`: the service's source folder, relative to the repository root. The writer copies it and reads nothing outside it. A path that is not a folder stops the run before the first turn.

One `--params` line may carry several surfaces. The run writes them one after the other and lands in `.agents/runs/okf-book-<run-id>`. `--profile` names the agent profile of the home config. `--dry-run` walks the graph with the agent turns and the stack stubbed.

Attend a run through groom, never through its launch log: `groom wait --run <run-id> --until blocked,ended` returns at the next operator gate, and `workhorse-okf-book control --run <run-dir> questions|answer --text …|resume` answers it.
