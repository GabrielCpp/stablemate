# Plan: make groom's dashboard JSON-first and genuinely live

## Context (read first — this plan assumes no prior conversation)

Repo: `/mnt/data/workspace/stablemate` — a `uv` workspace monorepo. `groom` is a
local, single-process Litestar web dashboard + OTLP collector for `workhorse`
agent-workflow runs. It shows one row per running workflow, pages the operator when
a run blocks on a gate, and lets the gate be answered from the browser.

Read `groom/README.md` and the root `CLAUDE.md` before starting.

**Repo rules that bite (load-bearing):**
- `ruff check .` from the **repo root** must be clean. Fix findings, don't `# noqa`.
- stablemate ships publicly: no private overlay project name anywhere in the tree.
  `make check-public` enforces it and runs in `make test`.
- Tests are dependency-free and standalone where possible; run them with
  `uv run --project groom python groom/tests/test_<x>.py`.

**Recently landed (don't redo):** workhorse's OTLP metric export interval now
defaults to the heartbeat interval (10s) instead of the SDK's 60s
(`_metric_export_every_s()` in `workhorse/workhorse/otel.py`), and groom re-renders
+ broadcasts the run list every `GROOM_LIVE_TICK_S` (5s) via `_live_loop()` in
`groom/groom/app.py`. That ticker is load-bearing for this plan — the client uses it
as a heartbeat for the socket itself.

---

## Goal

Everything talks JSON. HTTP endpoints return JSON instead of HTML fragments; the
websocket pushes the same JSON shapes; the browser renders. The dashboard shows its
own connection state and falls back to HTTP resync when the socket is down or lying.

## Decisions already made (do not re-litigate)

1. **Drop htmx** (`htmx.min.js` 51KB + `htmx-ext-ws.min.js` 14.7KB). It is already
   vestigial — 4 attributes in a 644-line template whose 508 lines are hand-written
   `fetch`. Its only real jobs are socket transport, OOB swap application, and
   `ws-send` on the answer form.
2. **Render with Preact + htm**, vendored as the single-file `htm/preact/standalone`
   ESM build (~5KB). No build step, no `package.json`, no `node_modules` — this repo
   hand-drops `.min.js` into `groom/assets/` and serves it locally. Nothing may be
   loaded from a CDN at runtime.
   - Rejected: Lit (shadow DOM cuts the existing 19KB `dashboard.css` off from
     components); Alpine/petite-vue (only needed if markup had to stay in HTML —
     it doesn't, see #3).
3. **a11y moves from static to dynamic testing.** `groom/groom/a11y_lint.py` parses
   HTML on disk and cannot see JS-generated DOM. Rather than contort the design
   around it, replace it with Playwright (Python) + axe-core against a live groom.
   This is stronger coverage (computed contrast, focus order, ARIA validity).
4. **Do not push everything onto the socket.** Split by *who the data belongs to*:
   - **Socket** — fleet-wide facts every client shares (run list, status bar, alerts),
     plus per-client subscription for the open run's detail.
   - **HTTP** — anything scoped to one client's selection and cache/cancel friendly
     (files tree, file content, diff, traces query), plus the full-state resync.
   Building socket RPC for request/response data means hand-rolling ids, timeouts and
   cancellation — the sidecar protocol already had to do that once; don't do it twice.
5. **One state shape, one render path.** The socket delta and the HTTP resync must
   deliver the same JSON and feed the same `applyState()`. If they diverge, the
   resync path — the rarely-exercised one — is where drift hides silently.

## Architecture

```
  GET /api/state  ──┐
                    ├──→  applyState(json)  ──→  Preact re-renders
  ws JSON delta   ──┘        (one function, both paths)
```

Connection state is derived from **message recency, not `readyState`** — a half-open
TCP socket reads as OPEN forever. The server ticks every 5s, so:

| Client observes            | Shows          | Action                          |
|----------------------------|----------------|---------------------------------|
| message within ~15s        | `live`         | —                               |
| open but silent > 15s      | `stale`        | start HTTP resync polling       |
| closed, reconnecting       | `reconnecting` | backoff reconnect               |
| closed > 60s               | `offline`      | HTTP resync on an interval      |

---

## Phase 1 — The spine

Land this alongside the existing HTML routes so nothing breaks mid-flight.

1. **`GET /api/state`** in `groom/groom/app.py` — the whole fleet as JSON: run rows
   (id, name, workflow type, state, live flag, silence label, current node, node age,
   gate presence) + status bar counts. This is the resync payload.
2. **Extract the projection.** Add `groom/groom/projection.py` (or similar) with the
   dataclass→dict functions. Both `/api/state` and the websocket must call these —
   that is what keeps the two paths identical. Do **not** let the ws handler build its
   own dict inline.
3. **Socket pushes JSON.** Change `dashboard_ws` / `state.broadcast` to send
   `{"type": "state", ...}` (full) and `{"type": "run", ...}` (single-run delta)
   instead of HTML. Keep `_handle_command`'s `{"cmd": "answer"}` contract; the client
   will now send it directly over the raw socket rather than via `ws-send`.
4. **Vendor `htm/preact` standalone** into `groom/assets/`. Remove `htmx.min.js` and
   `htmx-ext-ws.min.js` and their `<script>` tags **only** once nothing references them.
5. **New client module** `groom/assets/dashboard.js` (ESM, `<script type="module">`):
   - `useConnection()` — owns the socket, the 4-state machine above, backoff reconnect,
     and the staleness timer. This replaces htmx-ext-ws's internal reconnect.
   - the store — a plain object fed by both transports.
   - `<Fleet>` / `<RunRow>` / `<StatusBar>` / `<ConnectionChip>` components, mounted
     into the existing `#runs-list` / `#statusbar` nodes as islands.
   - **Key every list item** (`key=${run.id}`). This is what preserves focus, scroll
     position and a half-typed answer across a 5s push — the whole point of the exercise.
6. **Delete `esc()` usage as it becomes dead.** Preact sets text as text, so the
   XSS-escaping discipline in `render.py` stops being load-bearing for converted
   surfaces. Gate questions are LLM-authored and still need marked → DOMPurify for
   the *markdown* path.

**Tests:** `/api/state` shape; projection functions used by both paths (assert the ws
frame and the HTTP body are equal for the same fleet); the connection state machine
(feed it synthetic timestamps, assert live→stale→offline transitions and that resync
polling starts).

## Phase 2 — Per-client subscription (the reactivity win)

Kills the client-side 5s poll of `GET /worker/{id}/live`.

1. Client sends `{"cmd": "watch", "run_id": "..."}` on selection.
2. Server keeps `queue → watched_run_id` alongside `state.CLIENTS`.
3. On the `_live_loop` tick and on any state change touching run X, push the detail
   slice to X's watchers only.
4. Delete the `LIVE_POLL_MS` interval from the template.

Result: the detail pane becomes as live as the list, and a block shows up instantly
instead of up to 5s late.

**Watch out:** `#detail` is deliberately never clobbered today so a half-typed answer
survives. Preserve that — push the activity/metrics/log slices, never the answer form.

## Phase 3 — Convert remaining endpoints to JSON

Independent of each other; land one at a time, each with its own test.

| Endpoint | Today | After |
|---|---|---|
| `GET /search` | HTML + OOB swap | JSON matches |
| `GET /traces` | HTML into `#traces-list` | JSON rows |
| `GET /repos` | HTML menu | JSON `[{container, repos[]}]` |
| `GET /files/{cid}` | HTML tree | JSON tree |
| `GET /file/{cid}` | HTML | JSON `{content, lang}` |
| `GET /diff/{cid}` | HTML | JSON (raw diff text; diff2html renders client-side) |
| `GET /worker/{cid}` | HTML detail | JSON detail |
| `GET /worker/{cid}/live` | HTML slice | **deleted** (Phase 2) |

`render.py` (662 lines, 13 `render_*` functions) shrinks to nothing as these land.
Delete it when the last caller goes, along with `render_notify_script` /
`render_answered_script` — script-injection-over-the-wire has no place once the
client owns rendering; make them JSON events the client reacts to.

## Phase 4 — Retire the static a11y linter, add dynamic a11y

1. Add a Playwright (Python) test that boots groom with a synthetic fleet, injects
   axe-core (**vendor it**, no CDN), and asserts zero violations on: the runs list,
   an open detail pane with a gate, the files pane, the diff pane, and the telemetry
   pane. Cover keyboard reachability of the activity rail and the answer form.
2. Delete `groom/groom/a11y_lint.py`, `groom/tests/test_a11y_lint.py`, and the
   `A11Y*` rule surface — **only after** the dynamic test is green and covers the same
   ground. Do not leave the static linter in place pointing at markup that no longer
   ships; a green lint that checks nothing is worse than no lint.
3. Add the new test to `make test`.

---

## Phase 5 — OKF documentation (do this per-phase, not at the end)

The doc graph under `docs/features/groom/` is large (**56 docs touch the surface this
refactor changes**) and it is **not** in `make test`, so nothing will tell you it
broke. It also still carries **unfixed debt from the earlier Inbox→Runs redesign**:
docs still describe inbox as the default mode and target `#inbox-list` /
`.act-btn[data-mode="inbox"]`, which no longer exist. Fix both in the same pass.

Validate continuously with:

```bash
uv run ostler doctor                       # referential integrity
uv run ostler reach groom-dashboard        # documented click-path to the screen
uv run ostler locators                     # Playwright locator per documented control
uv run ostler coverage                     # code: citations vs source inventory
```

### 5a. Screen doc — `docs/features/groom/gui/screens/groom-dashboard.md`

The most stale file. Rewrite:
- Modes are `runs | files | diff | telemetry | settings`; **runs** is the default.
  (Doc currently says inbox, and omits telemetry.)
- `#inbox-list` → `#runs-list` throughout; `.act-btn[data-mode="inbox"]` →
  `[data-mode="runs"]`.
- Replace all "out-of-band swap" language — updates are now JSON applied by the client.
- **New component: the connection chip** — document its four states, its role/name,
  and that it derives from message recency rather than socket `readyState`.
- Re-derive every `- selector:` / `- role:` / `- name:` / `- keyboard:` bullet from the
  new Preact-rendered DOM. `ostler locators` will flag ambiguity.
- Update `code:` citations: they point at `groom/groom/render.py::render_*` and
  `templates/dashboard.html::<fn>`; they must point at the new JS module members.
- `verify:` bullets currently cite `test_a11y_lint.py::test_shipped_dashboard_is_clean`
  and `test_render.py::test_dynamic_regions_have_stable_ids_and_oob_flag` — both die in
  Phase 4/3. Repoint at the new Playwright a11y test and the projection tests.

### 5b. HTTP contract — `docs/features/groom/http/groom.md`

- Every converted endpoint's `response:` block flips from `media: text/html` +
  "fragment" to `media: application/json` with the documented body shape.
- **Add `GET /api/state`** as a new endpoint entry, and say explicitly that it returns
  the same payload the websocket pushes — that equivalence is the contract Phase 1
  rests on, and it belongs in the book.
- The root `GET /` entry says the shell "bootstraps htmx, the websocket extension,
  vendored assets, and dashboard JavaScript" — drop htmx.
- The server intro says "live updates are pushed as HTML fragments over the browser
  websocket" — now JSON.
- Update the route-table sentence (counts of read/mutation endpoints change).

### 5c. Concept docs — retire or rewrite

Rewrite where the unit survives, delete where it doesn't:
- `concepts/groom-render-module.md`, `concepts/dashboard-shell-renderer.md`,
  `concepts/dashboard-shell-broadcaster.md`, `concepts/html-escape-helper.md`,
  `concepts/worker-detail-renderer.md`, `concepts/dashboard-file-view-renderer.md`,
  `concepts/workflow-state-dot-renderer.md`,
  `concepts/workflow-type-badge-renderer.md` — server-side HTML rendering, all gone.
- `concepts/dashboard-inbox-selection-applier.md` — renamed concept (runs, not inbox).
- `concepts/answered-notification-script-renderer.md`,
  `concepts/blocked-notification-script-renderer.md` — script fragments become JSON
  events.
- `concepts/dashboard-active-pane-loader.md`, `concepts/dashboard-toast-pusher.md` —
  now client-side units.
- `concepts/groom-a11y-lint.md`, `concepts/groom-a11y-html-file-selector.md`,
  `concepts/groom-a11y-html-tree-parser.md`,
  `concepts/control-accessible-name-detector.md`,
  `concepts/accessible-subtree-text-collector.md`,
  `concepts/ancestor-tag-collector.md`, `concepts/widget-focusability-detector.md`,
  `concepts/explicit-accessible-name-attribute-detector.md` — delete with Phase 4.
  Their data docs sit one level up, at the `groom/` root, not under `concepts/`:
  `groom-a11y-lint.md`, `groom-a11y-node.md`, `groom-a11y-finding.md`. Delete those
  too, and grep for inbound `parent:`/`code:` references before you do — `ostler
  doctor` is the check that catches what you miss.
- `concepts/dashboard-websocket-receive-loop.md` /
  `concepts/dashboard-websocket-send-loop.md` — frame payloads change to JSON.

**New concept docs** for the units this introduces: the JSON projection module, the
client state store, the connection state machine, the resync poller, and the
per-client watch registry from Phase 2.

### 5d. Data docs

These describe payload shapes that change representation:
- `dashboard-shell-fragment.md` — HTML fragment → JSON state payload (probably rename).
- `dashboard-websocket-answer-frame.md` — was an htmx `ws-send` form serialization; now
  a hand-built JSON command.
- `repository-menu-data.md`, `workspace-file-list-data.md`, `workspace-diff-data.md`,
  `workspace-file-content-data.md` — now the actual wire shapes, not inputs to a
  server-side renderer.
- `operator-inbox.md` — the concept is now the runs fleet; reconcile the name.
- `changes-view.md` — references htmx/inbox; update.
- `groom-answered-script-fragment.md`, `blocked-notification-script-fragment.md`,
  `groom-answered-browser-event-detail.md` — script fragments → events.

### 5e. Flows

Step sequences change once the client renders:
- `flows/operator-answers-blocked-gate.md` — the answer no longer goes via `ws-send`.
- `flows/operator-browses-workspace-file.md`,
  `flows/operator-inspects-working-tree-diff.md`,
  `flows/operator-refreshes-workflow-fleet.md` — JSON responses, client rendering.
- `flows/a11y-lint-run.md` — delete or replace with the Playwright+axe flow.
- `flows/serve-dashboard-and-startup-discovery.md` — startup hooks changed recently
  (`_spawn_live` was added); verify it lists all three.

### 5f. Visual registration — `docs/specs/groom-dashboard/vet/`

Six JSON manifests + per-component PNGs, captured against the old DOM:
`post-discovery-manifest.json`, `post-discovery-regions.json`,
`post-discovery-report.json`, `smoke-manifest.json`, `smoke-regions.json`,
`smoke-report.json`, plus screenshots like
`post-discovery-activity-inbox-mode.png`.

Selectors and ids change, so **re-capture** with `ostler vet` once Phase 3 lands and
the DOM is stable. Don't do this earlier — you'll just capture it twice. Update
`docs/specs/groom-dashboard/vet.md` and every `- screenshot:` bullet whose filename
still says `inbox`.

### 5g. Agent skills — the part that is easy to miss

Skills teach *future agents* the stack. Leave them alone and every later session
confidently rebuilds the thing you just removed. Four files name htmx:

| File | htmx refs | Action |
|---|---|---|
| `.claude/skills/stablemate-python-htmx-accessibility/SKILL.md` | 12 | Whole skill is about this stack — see below |
| `.claude/skills/stablemate-groom/SKILL.md` | 4 | Lines ~79, ~83, ~92: asset list, "server pushes `hx-swap-oob` HTML fragments", and the pointer to the htmx skill |
| `.claude/skills/stablemate-ui-accessibility/SKILL.md` | 2 | Frontmatter `description:` + line 17 route the HTML/vanilla-JS stack to the htmx skill |
| `base-library/library/skills/stablemate/stablemate-groom/SKILL.md` | 4 | **Shipped data** — the base-library copy of the groom skill |

Two traps:

1. **`.claude/skills/*` are farrier-generated, not hand-edited.** Their frontmatter
   says so (`do_not_edit`). Edit the source, then `make agent-install` to regenerate.
   Find the source for a given skill with:
   ```bash
   farrier source .claude/skills/<name>/SKILL.md
   ```
2. **`stablemate-python-htmx-accessibility`'s source is not in this repo** — it
   resolves to a shared stacks library outside stablemate, so changing it affects
   every consumer of that library, not just groom. Decide deliberately: either add a
   *new* stack skill for the JSON/Preact-islands stack and repoint
   `stablemate-ui-accessibility`'s router line at it, or negotiate the edit upstream.
   Do not silently rewrite a shared skill to match one app.

   The skill is also about to be misnamed — it teaches "focus management across
   `hx-swap`" and "aria-live for out-of-band pushes", neither of which will exist.
   Under keyed Preact reconciliation the a11y mechanics genuinely change, so this is
   a rewrite, not a find-and-replace.

`base-library/` is shipped data with no private-name exposure, so its groom skill can
be edited directly in-tree. Re-run `make check-public` after — it asserts base skills
still stand alone.

### 5h. Also check

- `docs/features/groom/groom-redesign/README.md` and
  `groom-redesign/design-system.md` — stale from the previous redesign.
- `docs/features/groom/concepts/inbox-question-preview.md`.
- `docs/okf-ui-profile.md` — if it encodes an htmx/OOB UI profile, it needs the
  JSON/client-render model instead.
- `docs/features/groom/groom.md` — the feature's entry doc (note: it is *inside* the
  `groom/` directory; there is no `docs/features/groom.md`).
- `docs/workhorse-otel.md`.
- **`groom/README.md` lines 26–27** — "pushes updates to open browser tabs over a
  websocket using htmx + htmx-ext-ws". This is the operator-facing contract and
  workhorse's house rule is to keep READMEs current when behavior changes; the
  surrounding paragraph on edge-triggered pushes vs the `GROOM_LIVE_TICK_S` clock
  stays true and should survive the edit.
- `docs/features/groom/sidecar-live-sessions.md:120` — parenthetical "(htmx-ext-ws)"
  describing which browser tabs reconnect. One-word fix; the sidecar protocol itself
  is unaffected.
- `base-library/workflows/author/docs/survey-intake-design.md:51` names
  `stablemate-htmx-accessibility` as an *example* of a per-stack skill. If 5g renames
  that skill the example goes stale — but it is illustrative prose about the skill
  channel, not about groom, so a different example may be the better fix.

---

## Verification (run before calling any phase done)

```bash
# groom + workhorse suites
for f in groom/tests/test_*.py;     do uv run --project groom python "$f"     || break; done
for f in workhorse/tests/test_*.py; do uv run --project workhorse python "$f" || break; done

ruff check .            # from the REPO ROOT — covers every subproject
make check-public       # private-name sweep + base-library standalone check
make test               # includes check-public

uv run ostler doctor    # OKF referential integrity
uv run ostler reach groom-dashboard
uv run ostler locators
uv run ostler coverage
```

## Out of scope / open

- `groom/.superdesign/` is a static design mockup — leave it alone.
- **Open question, mention don't change:** `GROOM_LIVE_AFTER_S` is 180s. It was tuned
  when metric exports arrived every 60s (3 cycles of margin). Exports now arrive every
  10s, so it's ~18 cycles and a dead run stays green about three minutes longer than
  needed. Somewhere around 45–60s would match the new cadence. It's an alerting
  threshold — get the operator's call before moving it.
- Sidecar protocol (`/sidecar` websocket, `getTree`/`getFile`/`getDiff` RPC) is
  **unchanged** by this work. Don't fold it into the browser socket.
