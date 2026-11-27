# groom architecture

How groom is built, for anyone changing its code. The `groom` skill in the base library carries the contract a workflow or script integrates with. This file carries the internals behind it.

## Answer flow internals

`gates.py::answer_gate()`: acquire a per-`(container_id, file_path)` lock → re-check the gate file
still reads `AWAITING_OPERATOR` (reject a second tab's stale submission) → write `STATUS: ANSWERED`
+ the text via a throwaway read-write container (stdin-piped, never shell-interpolated) → if the
container is still running, done — the in-container wait script wakes up in place, no restart. A
plain `docker start <container_id>` is only a fallback for a container that isn't running (crashed,
manually stopped, or predates this design). **There is no compose/label-based recreate fallback.**

## Stack constraints (don't violate these when touching `groom`)

- Python only — no Node/npm/bundler, including at packaging time.
- No runtime CDN — every asset (the `htm/preact` standalone ESM build, diff2html, marked,
  DOMPurify, highlight.js, Pico classless CSS, `dashboard.js`) is vendored under `groom/assets/`
  and served via `create_static_files_router`.
- Single-process, shared in-memory state — `state.py`'s `WORKFLOWS`/`LOG`/`CLIENTS`/`_gate_locks`
  are plain module-level objects, not Litestar `app.state`, not Redis/a broker.
- **Everything on the wire is JSON.** The server never emits markup: `projection.py` builds the
  payloads, and the *same* shapes go out over `/ws` and over HTTP (`/api/state` and friends), so a
  tab whose socket went quiet resyncs rather than going stale. One state shape, one render path.
  `_handle_command` recognizes `cmd == "answer"` and `cmd == "watch"`.
- The browser renders with Preact + htm, mounted as islands into ids the static shell already
  ships. **No build step, no `package.json`, no `node_modules`** — the vendored standalone build is
  an ESM module loaded directly. Keep it that way; the Python-only constraint above is why.
- Connection state is derived from **message recency, not `readyState`** (a half-open socket reads
  open forever): live / stale / reconnecting / offline, with HTTP resync polling once stale.
- Agent-authored content (gate questions, diffs) is rendered client-side from JSON string members
  (`marked`+`DOMPurify`, `diff2html`) — the server emits no markup at all, which is what keeps the
  XSS boundary in one place (`tests/test_dashboard_client.py` is the contract to preserve).
- `groom serve` refuses a non-loopback `--host` without `--allow-non-loopback`.

## Accessibility (the dashboard is a real UI — it owes the contract)

The universal `ui-accessibility` skill
contract applies and is the skill to load. There is **no per-stack skill for groom's stack** — it is
a hand-authored HTML shell plus Preact islands with no router and no bundler, so the framework
mechanics the stack skills exist to supply (HTMX swap/focus rules, React Router announcements)
don't apply.

> **Ignore `stablemate-python-htmx-accessibility` when you are in `groom/`.** It is still installed
> — the universal contract skill routes to it, and farrier follows that link — and its `applyTo`
> glob matches `groom/templates/**` and `groom/assets/**/*.js`. It describes a stack groom left:
> there is no `hx-swap` here, no out-of-band push, no server-rendered fragment. Following it means
> rebuilding machinery that was deliberately removed.

The mechanics that do apply are small enough to state here:

- **The live regions are in the shell, not in the islands.** `#runs-list` (`role="log"`),
  `#statusbar` and the detail head (`role="status"`), and `#toasts` (`role="alert"`,
  `aria-live="assertive"`) are static elements the islands render *into*. Keep it that way: a live
  region that is itself re-created by a render is never announced. Adding a fourth `role="status"`
  to this page needs a distinguishing `aria-label` — the ambiguity is real.
- **Every island's roots and names are the accessibility contract.** Rows are keyed so Preact
  reconciles rather than replaces; a key change that swaps a row's DOM node moves focus off it.
- **State is never colour alone.** The connection chip and `.ws-dot` pair the dot
  (`aria-hidden="true"`) with the phase word; run status pairs its colour with text.
- **The command palette is a modal:** `role="dialog"` + `aria-modal`, focus moved to
  `#palette-input` on open and restored to the trigger on Escape, with the input as a `combobox`
  driving `aria-activedescendant` over a `role="listbox"`. The repo search box follows the same
  pattern. Both are built; don't regress them.

**Accessibility here is tested dynamically, not statically.** `tests/test_a11y_dynamic.py` drives
a live groom with Playwright and runs vendored axe-core over each pane. Adding a pane means adding
its axe pass — a static template linter cannot see markup the browser builds.

The `marked`+`DOMPurify` markdown path preserves the XSS boundary
(`tests/test_dashboard_client.py`); keep it also preserving headings/lists so gate questions stay
perceivable.

## Package layout (orientation, not exhaustive)

`models.py` (dataclasses) · `state.py` (in-memory store + broadcast) · `gates.py` (STATUS
parsing + `answer_gate`) · `docker_io.py` (purpose-built throwaway-container helpers:
`read_file`/`write_file`/`grep_awaiting_files`/`docker_start`/`is_running`/`git_diff`/...) ·
`discovery.py` (one-shot reconciliation) · `projection.py` (registry → the JSON payloads both
transports send) · `app.py` (Litestar routes + `/ws`) · `assets/dashboard.js` (the Preact
islands) · `sidecar.py` (in-container `groom-sidecar`) · `cli.py` (`groom`/`groom-sidecar` entry
points).

