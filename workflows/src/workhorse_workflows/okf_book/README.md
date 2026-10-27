# okf_book

The `okf-book` workflow. It writes, repairs and runs one OKF book per surface of an app.

## Launch

Run it from the root of the repository whose book it writes. Each surface is a service
slug, its kind and its entry folder:

```bash
workhorse-okf-book run --run-id book-api-1 --profile claude \
  --params '{"surfaces":[{"service":"api","kind":"http","entry":"api"}]}'
```

- `service`: the book's folder under `docs/services/`.
- `kind`: `cli`, `http`, `web` or `mobile`. It picks the writer's branch of the skill and the driver the scenarios run on.
- `entry`: the service's source folder, relative to the repository root. The writer copies it and reads nothing outside it. A path that is not a folder stops the run before the first turn.
- `repo`: the workspace member that holds the service's source. Under a workspace it is required and must name a member, and the book is written to the docs home while `entry` is read from that member. Outside a workspace it must be empty. A surface that gets either wrong stops the run before the first turn, naming the members.

One `--params` line may carry several surfaces. The run writes them one after the other and lands in `.agents/runs/okf-book-<run-id>`. `--profile` names the agent profile of the home config. `--dry-run` walks the graph with the agent turns and the stack stubbed.

Attend a run through groom, never through its launch log: `groom wait --run <run-id> --until blocked,ended` returns at the next operator gate, and `workhorse-okf-book control --run <run-dir> questions|answer --text …|resume` answers it.
