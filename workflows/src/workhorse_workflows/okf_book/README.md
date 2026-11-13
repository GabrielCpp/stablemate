# okf_book

The `okf-book` workflow. It writes the Python book of one service under `services/<name>/`.

## Launch

Run it from the root of the repository whose book it writes:

```bash
workhorse-okf-book run python_book --run-id book-api-1 --profile claude --params '{...}'
```

`python_book` is the only flow, and a bare `run` starts it too. Its parameters are `service`, `kind`, `source_folder` and `stack_copy`.

`--profile` names the agent profile of the home config. `--dry-run` walks the graph with the agent turns stubbed.

Attend a run through groom, never through its launch log: `groom wait --run <run-id> --until blocked,ended` returns at the next operator gate, and `workhorse-okf-book control --run <run-dir> questions|answer --text …|resume` answers it.
