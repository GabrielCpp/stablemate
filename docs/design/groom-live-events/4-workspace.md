# Slice 4: Diff and Files follow the workspace

Read [the design note](../groom-live-events.md) and [slice 2](2-open-run.md) first.
This slice needs slice 2 merged, because the revision travels in the detail frame.

**When it lands:** an operator with the Diff or Files tab open sees an edit in the run's
workspace within about 2 s, without pressing Retry. A run whose sidecar predates this
slice behaves as today.

## Where things are today

- `groom/groom/sidecar.py`. `_watch_loop` runs `watchfiles.awatch` with
  `_WATCH_FILTER = DefaultFilter(ignore_dirs=...)` and sends `progress`, `blocked` and
  `turn` frames over the `/sidecar` socket.
- `groom/groom/app.py` handles the `/sidecar` socket frames. The `/reload` endpoint
  (near line 1670) is one way new sidecar code reaches running containers.
- `groom/groom/models.py`. `WorkflowContainer` holds a container run's state.
- `groom/groom/assets/dashboard.js`. `useRunDiff` (near line 4457) and `useRunFiles`
  (near line 4696) load on open and on Retry, and mark the result stale.

## Steps

1. **Emit a `workspace` frame from the sidecar.** In `_watch_loop`, any change under the
   workspace that is not already a `progress`, `blocked` or `turn` source schedules
   `{"type": "workspace"}`. Send at most one every 2 s, with a trailing send after the
   last change in a burst. Check `_WATCH_FILTER`. A commit or a stage changes
   `.git/index` and `.git/HEAD`, so those two paths must pass the filter while the rest
   of `.git` stays ignored. Report it as a design gap if the filter cannot express that.
2. **Count the revision in groom.** Add `workspace_rev: int = 0` to
   `WorkflowContainer`. The `/sidecar` handler raises it on a `workspace` frame and calls
   `live.mark_run(id)`. `run_detail` copies it into the detail.
3. **Refetch in the browser.** `useRunDiff` and `useRunFiles` refetch when the detail's
   `workspace_rev` moves and their tab is open, with a 1 s debounce. Keep the stale
   marker and Retry. A rev of 0 means an old sidecar, and the hooks behave as today.
4. **Ship the sidecar.** Find how sidecar code reaches a container: the image build, the
   mount and `/reload`. Write the path in the commit body. If an image rebuild is
   needed, rebuild it under the standing authorization and name the command in the
   report.
5. **Update the book.** Load the `ostler-book` skill. Add the `workspace` frame to the
   sidecar socket page, `workspace_rev` to the detail record, and the refresh rule to
   the Diff and Files screen pages. Find them with
   `ostler book search diff --service services.groom`.

Native runs have no sidecar. Their Diff and Files tabs stay as they are.

## Tests

- In the sidecar tests, three writes inside 2 s send one `workspace` frame now and one
  trailing frame. A write to `.git/index` sends one. A write under `.git/objects`
  sends none. Use `tmp_path`.
- In `groom/tests/test_app.py`, a `workspace` frame on `/sidecar` raises
  `workspace_rev` and sends one `detail` to a watching tab.
- In `groom/tests/test_diff_stale_dynamic.py` or a sibling, push a detail with a higher
  `workspace_rev` while Diff is open, and see one diff request leave within 1.5 s with no
  Retry click.

## Checks that close the slice

Run each from the repo root:

- `uv run pytest -n auto groom/tests` is green.
- `make lint` exits 0.
- `ostler book check services.groom --app .` passes.
- `ostler book run services.groom` is green.

The coordinator then has `e2e-web` open Diff on a container run in a running groom, edit
a file in that run's workspace, and see the diff update within 3 s.

Commit as `feat(groom): refresh diff and files when the workspace changes`.
