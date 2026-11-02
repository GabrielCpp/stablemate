// groom's dashboard client.
//
// The server projects JSON (groom/projection.py) and this module renders it.
// Two things follow from that, and they are the reason this file exists at all:
//
//   1. **One state shape, one render path.** A `state` frame pushed on the
//      websocket and the body of `GET /api/state` are the same JSON, and both go
//      through `applyState()`. Recovering from a dead socket is therefore not a
//      second rendering path that can rot unobserved — it is the only path,
//      reached a different way.
//
//   2. **Connection state is derived from message recency, not `readyState`.**
//      A half-open TCP socket reads OPEN forever and will never deliver another
//      frame; a dashboard that trusts `readyState` shows a green dot over a
//      frozen fleet. The server ticks every GROOM_LIVE_TICK_S (5s) whether or not
//      anything changed, so silence is information: see `deriveConnection()`.
//
// Every panel is a Preact island mounted into an id the static shell already
// ships (`#runs-list`, `#statusbar`, `#detail`, `#palette-results`), so the live-region and
// landmark attributes stay on elements that outlive every update. Nothing on
// either side of the wire is HTML any more: the server sends data, this module
// decides what it looks like, and the only strings that ever reach `innerHTML`
// are the outputs of DOMPurify, diff2html and highlight.js.
//
// Keys carry real weight here. A row is keyed by run id and a gate block by its
// file path, which is what preserves focus, scroll position and — because Preact
// then reuses the same `<textarea>` DOM node — a half-typed answer across a
// 5-second push.
//
// What one tab has *open* is not a fleet-wide fact, so it is not broadcast: the
// tab sends `{cmd: "watch", run_id}` and the server pushes that run's detail back
// to it alone (`onDetail`). That subscription is what replaced polling
// `GET /worker/{id}/live` every five seconds from every open tab.

import { html, render, useState, useEffect, useLayoutEffect, useRef } from "/assets/htm-preact.js";

const UNCOMMITTED_VIEW = "uncommitted";
const BRANCH_VIEW = "branch";

// --------------------------------------------------------------------------- //
// Store — one snapshot, subscribed to by every island
// --------------------------------------------------------------------------- //
// Deliberately not a per-component `useState`: the socket is a singleton and the
// islands read overlapping slices of the same truth, so the state lives outside
// the component tree and the components are pure functions of it.
const store = {
  snapshot: {
    // fleet (socket-pushed)
    runs: [],
    status: { counts: {}, repos: 0, workers: 0 },
    scanning: true,
    conn: { phase: "connecting", resyncing: false },
    query: "",
    // the open run (subscription snapshot, then ingestion pushes)
    selected: null,
    detail: null,
    tab: "overview",
    gatesCollapsed: false,
    overview: { runId: "", status: "idle", data: null, rev: 0 },
    breakdown: { view: "flow", sort: "time" },
    // per-tab, per-selection panels (HTTP; cancel- and cache-friendly)
    mode: "runs",
    checkouts: {},
    diffViews: {},
    diffKept: {},
    sidecarLost: {},
    stillDown: {},
    runDiff: idleRunDiff(),
    runFiles: idleRunFiles(),
    // the attendant: a per-run summary rides every `state` frame, the log does not
    attend: { mode: "off", by_run: {}, rev: 0, status: "idle", sessions: [], selected: null, record: null },
    // dispatch queues have no socket push — occupancy changes on a launch/exit
    // that only the server's own threads see — so this pane polls while open.
    dispatch: { status: "idle", queues: [], selectedQueue: null, items: [], selectedItem: null },
    settings: { status: "idle", attend: null, saving: false },
    palette: { open: false, query: "", active: 0 },
  },
  listeners: new Set(),
  get() {
    return this.snapshot;
  },
  set(patch) {
    this.snapshot = Object.assign({}, this.snapshot, patch);
    this.listeners.forEach((fn) => fn(this.snapshot));
  },
  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  },
};

/** Merge into one nested slice of the snapshot. The snapshot itself stays flat
 *  and shallow-merged, so a panel updating its own key can never clobber another. */
function setIn(key, patch) {
  store.set({ [key]: Object.assign({}, store.get()[key], patch) });
}

function useStore() {
  const [snap, setSnap] = useState(store.get());
  useEffect(() => store.subscribe(setSnap), []);
  return snap;
}

/** The single entry point for fleet-wide state, from either delivery path. */
function applyState(msg) {
  store.set({ runs: msg.runs || [], status: msg.status || store.get().status, scanning: !!msg.scanning, ...sidecarTrack(msg.runs || []) });
  // The frame carries one entry per attended run and a revision, never the log —
  // 200 rows on a 5s tick would dwarf the fleet itself. A `rev` that moved is what
  // tells an open Attendant pane its list is stale.
  const summary = msg.attend;
  if (!summary) return;
  const attend = store.get().attend;
  const stale = attend.status === "ready" && summary.rev !== attend.rev;
  setIn("attend", { mode: summary.mode || "off", by_run: summary.by_run || {}, rev: summary.rev || 0 });
  if (stale && store.get().mode === "attend") loadAttend();
}

/** A single-run delta: same row shape as an entry in `state.runs`, merged in
 *  place so the other rows are not re-created and lose focus. */
function applyRun(msg) {
  const row = msg.run;
  if (!row) return;
  const runs = store.get().runs.slice();
  const at = runs.findIndex((r) => r.id === row.id);
  if (at >= 0) runs[at] = row;
  else runs.push(row);
  runs.sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name));
  store.set({ runs: runs, ...sidecarTrack(runs) });
}

/** When the page first saw each container run without its sidecar, and which
 *  runs answered a retry with nothing. Both clear the moment the row says the
 *  sidecar is back, because the row is what tells the page it dropped. */
function sidecarTrack(runs) {
  const snap = store.get();
  let lost = snap.sidecarLost;
  let still = snap.stillDown;
  for (const row of runs) {
    if (row.native) continue;
    if (row.sidecar) {
      if (lost[row.id] !== undefined) lost = Object.assign({}, lost, { [row.id]: undefined });
      if (still[row.id]) still = Object.assign({}, still, { [row.id]: false });
    } else if (lost[row.id] === undefined) {
      lost = Object.assign({}, lost, { [row.id]: Date.now() });
    }
  }
  return { sidecarLost: lost, stillDown: still };
}

function sidecarDown(id) {
  const row = store.get().runs.find((run) => run.id === id);
  return !!row && !row.native && !row.sidecar;
}

// --------------------------------------------------------------------------- //
// Connection — socket, four-state machine, backoff reconnect, HTTP resync
// --------------------------------------------------------------------------- //
// The server's live ticker is the heartbeat. Three missed ticks is `stale`; a
// minute of a closed socket is `offline`. Both thresholds are generous multiples
// of the 5s tick so a slow push or one dropped frame does not flap the chip.
export const STALE_AFTER_MS = 15000;
export const OFFLINE_AFTER_MS = 60000;
const EVAL_EVERY_MS = 1000;
const RESYNC_EVERY_MS = 5000;
const BACKOFF_BASE_MS = 500;
const BACKOFF_MAX_MS = 30000;

/**
 * The four-state machine, as a pure function of observations so it can be
 * asserted against synthetic timestamps instead of a real socket.
 *
 *   open, a frame within STALE_AFTER_MS  → live
 *   open, silent past that               → stale        (start resyncing)
 *   closed, under OFFLINE_AFTER_MS       → reconnecting (backoff is in flight)
 *   closed longer                        → offline      (resync on an interval)
 *
 * `resyncing` is what the caller acts on: anything but `live` means the socket
 * is not a trustworthy source of truth and `GET /api/state` has to carry the tab.
 */
export function deriveConnection(obs) {
  const { now, socketOpen, lastMessageTs, closedSince } = obs;
  if (socketOpen) {
    const silent = now - (lastMessageTs || 0);
    if (silent <= STALE_AFTER_MS) return { phase: "live", resyncing: false };
    return { phase: "stale", resyncing: true };
  }
  if (now - (closedSince || 0) <= OFFLINE_AFTER_MS) return { phase: "reconnecting", resyncing: true };
  return { phase: "offline", resyncing: true };
}

export function backoffDelay(attempt) {
  return Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * Math.pow(2, attempt));
}

const conn = {
  socket: null,
  open: false,
  lastMessageTs: 0,
  closedSince: Date.now(),
  attempt: 0,
  resyncInFlight: false,
  lastResyncTs: 0,
};

/** Send a command frame up the socket. Returns false when there is no socket to
 *  send it on, so the caller can say so rather than silently dropping it. */
export function sendCommand(payload) {
  if (!conn.socket || conn.socket.readyState !== WebSocket.OPEN) return false;
  conn.socket.send(JSON.stringify(payload));
  return true;
}

function onFrame(msg) {
  conn.lastMessageTs = Date.now();
  if (msg.type === "state") applyState(msg);
  else if (msg.type === "run") applyRun(msg);
  else if (msg.type === "detail") onDetail(msg);
  else if (msg.type === "notify") onNotify(msg.message);
  else if (msg.type === "answered") onAnswered(msg);
  else if (msg.type === "answer_rejected") onAnswerRejected(msg);
}

/** Tell the server which run's detail pane this tab has open — the subscription
 *  that replaced polling `GET /worker/{id}/live`. Sent on selection and re-sent
 *  on every socket open, because the server forgets a tab the moment it drops. */
export function sendWatch(runId) {
  return sendCommand({ cmd: "watch", run_id: runId || "" });
}

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(proto + "//" + location.host + "/ws");
  conn.socket = socket;
  socket.addEventListener("open", () => {
    conn.open = true;
    conn.attempt = 0;
    // Not a live timestamp yet: the server's first frame is what proves the
    // connection actually carries data, and that is what `live` should mean.
    conn.lastMessageTs = Date.now();
    // The subscription lived on the old socket. Re-declaring it here is what makes
    // a reconnect self-healing — the server answers with the current detail, so an
    // open pane recovers without a fetch and without the operator touching anything.
    const selected = store.get().selected;
    if (selected) sendWatch(selected);
  });
  socket.addEventListener("message", (evt) => {
    let msg;
    try {
      msg = JSON.parse(evt.data);
    } catch (err) {
      return; // a frame we cannot parse is a frame we cannot act on
    }
    onFrame(msg);
  });
  const down = () => {
    if (!conn.open && conn.socket !== socket) return;
    conn.open = false;
    if (conn.socket === socket) conn.closedSince = Date.now();
    const delay = backoffDelay(conn.attempt++);
    setTimeout(connect, delay);
  };
  socket.addEventListener("close", down);
  socket.addEventListener("error", () => socket.close());
}

/** Pull the full fleet over HTTP. The body is the same payload the socket
 *  pushes, so it goes through the same `applyState()`. */
async function resync() {
  if (conn.resyncInFlight) return;
  conn.resyncInFlight = true;
  try {
    const response = await fetch("/api/state", { headers: { accept: "application/json" } });
    if (response.ok) {
      applyState(await response.json());
      conn.lastResyncTs = Date.now();
    }
  } catch (err) {
    // Offline stays offline; the next tick tries again.
  } finally {
    conn.resyncInFlight = false;
  }
}

function evaluateConnection() {
  const next = deriveConnection({
    now: Date.now(),
    socketOpen: conn.open,
    lastMessageTs: conn.lastMessageTs,
    closedSince: conn.closedSince,
  });
  const current = store.get().conn;
  if (next.phase !== current.phase || next.resyncing !== current.resyncing) store.set({ conn: next });
  if (next.resyncing && Date.now() - conn.lastResyncTs >= RESYNC_EVERY_MS) resync();
}

function startConnection() {
  connect();
  setInterval(evaluateConnection, EVAL_EVERY_MS);
  // A tab that comes back from the background has usually missed ticks; resync
  // immediately rather than showing a stale fleet for up to a full interval.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      evaluateConnection();
      if (store.get().conn.phase !== "live") resync();
    }
  });
}

// --------------------------------------------------------------------------- //
// Shared presentation
// --------------------------------------------------------------------------- //
function StateDot({ state }) {
  return html`<span class="dot ${state}" aria-hidden="true"></span>`;
}

function TypeBadge({ type, hue }) {
  if (!type) return null;
  return html`<span class="badge" data-type=${type} style=${{ "--type-hue": hue }}>${type}</span>`;
}

// Gate questions are LLM-authored markdown and untrusted. marked parses, DOMPurify
// sanitizes, and only then does the result reach the DOM — the one place in this
// module where markup is set rather than built. With the libraries absent (the
// unit harness), the raw text renders as a text node instead, which is the safe
// degradation rather than the pretty one.
function mdHtml(source) {
  const text = source || "";
  if (!window.marked || !window.DOMPurify) return null;
  return DOMPurify.sanitize(marked.parse(text));
}

function Markdown({ className, source }) {
  const markup = mdHtml(source);
  if (markup === null) return html`<div class=${className}>${source || ""}</div>`;
  return html`<div class=${className} dangerouslySetInnerHTML=${{ __html: markup }}></div>`;
}

// --------------------------------------------------------------------------- //
// Tree view (shared by the Files and Diff panels)
// --------------------------------------------------------------------------- //
// The server sends flat paths — the nesting is a pure function of them, and which
// directories start open is a display decision, so both live here.
function buildTree(entries) {
  const root = { dirs: {}, files: [] };
  entries.forEach((entry) => {
    const parts = String(entry.path).split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      node.dirs[parts[i]] = node.dirs[parts[i]] || { dirs: {}, files: [] };
      node = node.dirs[parts[i]];
    }
    node.files.push({ name: parts[parts.length - 1], entry: entry });
  });
  return root;
}

// Collapse state is component-local on purpose: it belongs to this directory in
// this tab and nothing else reads it, so it stays out of the store — and it
// survives a re-render because the node is keyed by name.
function TreeDir({ name, node, leaf, fold, trail = "" }) {
  const [localOpen, setLocalOpen] = useState(true);
  const key = trail + name;
  const open = fold ? !fold.shut[key] : localOpen;
  const toggle = fold ? () => fold.toggle(key) : () => setLocalOpen(!localOpen);
  return html`<div class=${"tree-dir" + (open ? "" : " collapsed")}>
    <button
      type="button"
      class="tree-dir-head"
      aria-expanded=${String(open)}
      onClick=${toggle}
    >
      <span class="tchev" aria-hidden="true">▾</span>${name}
    </button>
    <div class="tree-children"><${TreeLevel} node=${node} leaf=${leaf} fold=${fold} trail=${key + "/"} /></div>
  </div>`;
}

function compactDirs(node) {
  const dirs = {};
  Object.keys(node.dirs).forEach((name) => {
    let label = name;
    let child = node.dirs[name];
    for (;;) {
      const names = Object.keys(child.dirs);
      if (names.length !== 1 || child.files.length) break;
      label += "/" + names[0];
      child = child.dirs[names[0]];
    }
    dirs[label] = compactDirs(child);
  });
  return { dirs, files: node.files };
}

function TreeLevel({ node, leaf, fold, trail = "" }) {
  const dirs = Object.keys(node.dirs).sort();
  const files = node.files.slice().sort((a, b) => a.name.localeCompare(b.name));
  return html`
    ${dirs.map((d) => html`<${TreeDir} key=${"dir:" + d} name=${d} node=${node.dirs[d]} leaf=${leaf} fold=${fold} trail=${trail} />`)}
    ${files.map((f) => leaf(f))}
  `;
}

// --------------------------------------------------------------------------- //
// Runs: the fleet list and the status bar
// --------------------------------------------------------------------------- //
// `data-worker-id` / `data-state` / `data-live` are not decoration: the j/k row
// navigation reads the fleet back off the DOM through them, so they are part of
// this component's contract.
function RowFigures({ figures, narrow }) {
  let cost;
  if (!figures.finished) cost = html`<span class="dim">no cost yet</span>`;
  else if (!figures.reports_cost) cost = html`<span class="warn">no cost reported</span>`;
  else {
    cost = html`<span>${fmtUsd(figures.cost_usd)} <span class="dim">${figures.priced_turns}/${figures.turns}${narrow ? "" : " priced"}</span></span>`;
  }
  return html`<span class="line3">
    ${cost}
    <span>${fmtSpan(figures.active_s)} <span class="dim">active</span></span>
    ${figures.items_total ? html`<span class="dim">${figures.items_done}/${figures.items_total} items</span>` : null}
  </span>`;
}

function RunRow({ run, selected, narrow }) {
  const cls = "row" + (run.state === "blocked" ? " blocked" : "") + (selected ? " selected" : "");
  return html`
    <button
      type="button"
      class=${cls}
      data-worker-id=${run.id}
      data-state=${run.state}
      data-live=${run.live}
      aria-current=${selected ? "true" : null}
    >
      <span class="line1">
        <${StateDot} state=${run.state} />
        <${TypeBadge} type=${run.type} hue=${run.type_hue} />
        <span class="repo-branch">${run.repo}</span>
        <span class="wid">#${run.row_id}</span>
        ${run.live_label ? html`<span class="pulse ${run.live}">${run.live_label}</span>` : null}
      </span>
      <span class="line2">
        <span class="doing">${run.doing}</span>
        <${MiniClock} clock=${run.clock} mini=${run.mini} />
      </span>
      ${run.question ? html`<span class="q">${run.question}</span>` : null}
      ${run.figures ? html`<${RowFigures} figures=${run.figures} narrow=${narrow} />` : null}
    </button>
  `;
}

function Fleet() {
  const { runs, scanning, query, selected } = useStore();
  // Filtering is client-side: the server pushes the whole (small) fleet on every
  // tick, so a server-filtered list would be clobbered by the next push — and
  // filtering a few dozen rows locally needs no debounce at all.
  const q = query.trim().toLowerCase();
  const shown = q ? runs.filter((r) => rowHaystack(r).indexOf(q) >= 0) : runs;
  if (!shown.length) {
    // A fleet that has not been scanned yet must read as *loading*, not as
    // *finished and empty* — but only when the operator is not mid-filter, where
    // an empty result is the honest answer.
    if (scanning && !q) {
      return html`<div class="empty loading"><span class="spin"></span>Discovering containers…</div>`;
    }
    return html`<div class="empty">No workhorse runs — nothing is running.</div>`;
  }
  return shown.map((run) => html`<${RunRow} key=${run.id} run=${run} selected=${run.id === selected} narrow=${Boolean(selected)} />`);
}

function rowHaystack(run) {
  return [run.name, run.repo, run.type, run.node, run.activity, run.doing, run.question, run.run_id]
    .join(" ")
    .toLowerCase();
}

const CONN_TITLE = {
  live: "Receiving live updates.",
  stale: "The socket is open but has gone quiet — falling back to polling.",
  reconnecting: "The socket dropped; reconnecting and polling meanwhile.",
  offline: "No socket. Polling for updates.",
};

function ConnectionChip() {
  const { conn: c } = useStore();
  // Its own live region: the phase changing is exactly the kind of thing that
  // should be announced, and it changes independently of the fleet counts beside
  // it. The word is the accessible name — the dot is decoration, so a degraded
  // socket does not depend on color to be legible.
  return html`<span
    class="stat conn"
    data-conn=${c.phase}
    role="status"
    aria-label=${"Connection: " + c.phase}
    title=${CONN_TITLE[c.phase] || ""}
    ><span class="ws-dot" aria-hidden="true"></span>${c.phase}</span
  >`;
}

const STAT_ORDER = ["blocked", "running", "idle", "finished"];

function StatusBar() {
  const { status } = useStore();
  const counts = status.counts || {};
  return html`
    ${STAT_ORDER.map(
      (s) => html`<span class="stat" key=${s}>
        <${StateDot} state=${s} /><span class="n">${counts[s] || 0}</span> ${s}
      </span>`
    )}
    <span class="status-right">
      <span>${status.repos || 0} repos · ${status.workers || 0} workers</span>
      <${ConnectionChip} />
      <button
        type="button"
        id="btn-refresh-bar"
        class="statusbar-refresh"
        aria-label="Rescan containers (reconcile + prune)"
        title="Rescan containers (reconcile + prune)"
      >
        <span aria-hidden="true">⟳</span>
      </button>
      <button type="button" id="btn-palette" class="palette-open" aria-label="Open command palette">
        <span class="kbd" aria-hidden="true">⌘K</span> palette
      </button>
    </span>
  `;
}

// --------------------------------------------------------------------------- //
// Detail pane — the open run (`GET /worker/{id}` + the pushed `detail` frame)
// --------------------------------------------------------------------------- //
function RunHead({ head, onClose, sidecar }) {
  const meta =
    head.state + (head.node ? " · node " + head.node : "") +
    (head.cli ? " · " + head.cli : "") + (head.pid ? " · pid " + head.pid : "");
  // The id is its own element rather than a slice of `meta`, because it is the
  // one part of this line anybody copies: `user-select: all` (see the CSS) turns
  // a single click into the whole id, and a partial selection cannot cut it in
  // half mid-paste.
  // role="status" because that is what it is: the line that says what this run is
  // doing right now, re-rendered on the server's clock.
  return html`<div class="detail-head" role="status" aria-label="Selected run">
    <${StateDot} state=${head.state} />
    <${TypeBadge} type=${head.type} hue=${head.type_hue} />
    <span class="repo-branch">${head.repo}</span>
    ${head.live_label ? html`<span class="pulse ${head.live}">${head.live_label}</span>` : null}
    <span class="run-id" title="Run id — click to select">${head.handle}</span>
    ${sidecar ? html`<span id="run-sidecar-chip" class="chip">${sidecar === "live" ? "docker · sidecar" : "docker"}</span>` : null}
    <span class="meta">${meta}</span>
    ${head.exit_hint
      ? html`<span class=${"exit-hint " + (head.exit_ok ? "exit-ok" : "exit-err")}>${head.exit_hint}</span>`
      : null}
    ${head.activity ? html`<span class="doing-line">${head.activity}</span>` : null}
    ${head.worktree ? html`<span class="doing-line">${head.worktree}</span>` : null}
    ${onClose
      ? html`<button type="button" class="btn ghost close-detail" aria-label="Close run detail" title="Close run detail" onClick=${onClose}>Close</button>`
      : null}
  </div>`;
}

function Metrics({ metrics }) {
  if (metrics.empty) {
    return html`<div class="metrics">
      <div class="fd-empty">
        No telemetry for this run — it is either pre-OTel or exporting to another collector.
      </div>
    </div>`;
  }
  const foot = metrics.alerts.length || metrics.run_dir;
  return html`<div class="metrics">
    <div class="metrics-grid">
      ${metrics.cells.map(
        (cell) => html`<div class=${"metric" + (cell.cls ? " " + cell.cls : "")} key=${cell.key}>
          <span class="m-k">${cell.key}</span><span class="m-v">${cell.value}</span>
        </div>`
      )}
    </div>
    ${foot
      ? html`<div class="metrics-foot">
          ${metrics.alerts.map((rule) => html`<span class="alert-chip" key=${rule}>${rule}</span>`)}
          ${metrics.run_dir ? html`<code>${metrics.run_dir}</code>` : null}
        </div>`
      : null}
  </div>`;
}

const TRAIL_VIEWS = [
  ["all", "All"],
  ["transcript", "Transcript"],
  ["telemetry", "Telemetry"],
];

function storedTrailView() {
  try {
    const saved = localStorage.getItem("groom.trailView");
    return TRAIL_VIEWS.some(([id]) => id === saved) ? saved : "all";
  } catch (e) {
    return "all";
  }
}

function rememberTrailView(view) {
  try {
    localStorage.setItem("groom.trailView", view);
  } catch (e) {}
}

function TurnGroup({ line, opened }) {
  const open = line.slug in opened ? opened[line.slug] : line.status === "running";
  const toggled = (event) => {
    const now = event.currentTarget.open;
    if (now !== open) opened[line.slug] = now;
  };
  return html`<details class=${"log-line turn" + (line.cls ? " " + line.cls : "")}
    open=${open} onToggle=${toggled}>
    <summary class="lt-turn-head">
      <span class="lt-ts" title=${line.ts}>${line.ts}</span>
      <span class="lt-node">${line.node}</span>
      <span class="lt-slug">${line.slug}</span>
      <span class=${"lt-status " + line.status}>${line.status}</span>
      <span class="lt-dur">${line.duration}</span>
    </summary>
    <div class="lt-turn-body">
      ${line.entries.map((entry) => html`<${AttendEntry} key=${entry.key} entry=${entry} />`)}
    </div>
  </details>`;
}

function TrailLine({ line, opened }) {
  if (line.kind === "turn") return html`<${TurnGroup} line=${line} opened=${opened} />`;
  return html`<div class=${"log-line" + (line.cls ? " " + line.cls : "")}>
    <span class="lt-ts" title=${line.ts}>${line.ts}</span>
    <span class="lt-lvl">${line.level}</span>
    <span class="lt-node">${line.node}</span>
    <span class="lt-body">${line.body}</span>
  </div>`;
}

function LogTrail({ lines }) {
  const [kind, setKind] = useState("");
  const [view, setView] = useState(storedTrailView);
  const pick = (id) => {
    setView(id);
    rememberTrailView(id);
  };
  const opened = useRef({}).current;
  const byView = lines.filter((line) =>
    view === "all" ? !line.absorbed : (line.kind === "turn") === (view === "transcript")
  );
  const shown = kind && view !== "transcript" ? byView.filter((line) => line.kind === kind) : byView;
  return html`<div>
    <div class="history-filter">
      <span class="trail-views" role="group" aria-label="History view">
        ${TRAIL_VIEWS.map(
          ([id, label]) => html`<button type="button" class="btn ghost" key=${id}
            aria-pressed=${String(view === id)} onClick=${() => pick(id)}>${label}</button>`
        )}
      </span>
      ${view === "transcript"
        ? null
        : html`<label>Show
            <select aria-label="Telemetry history type" value=${kind}
              onChange=${(event) => setKind(event.currentTarget.value)}>
              <option value="">All telemetry</option>
              <option value="log">Log records</option>
              <option value="span">Completed spans</option>
              <option value="metric">Metric samples</option>
            </select>
          </label>`}
    </div>
    <div class="log-trail" role="log" aria-label="Telemetry history" aria-live="polite">
      ${shown.length ? shown.map((line, i) => html`<${TrailLine} key=${line.key ?? i} line=${line} opened=${opened} />`)
        : html`<div class="fd-empty">${lines.length
        ? "No records of this type in the recent history."
        : "No telemetry history has been received for this run yet."}</div>`}
    </div>
  </div>`;
}

// The wire contract is what it was in the ws-send days — `cmd=answer` plus the
// (workflow_id, file_path) that scope the write, so several simultaneously-live
// gates stay unambiguous. The hidden fields stay because the delegated submit
// handler reads them, which keeps the frame's provenance visible in the DOM
// instead of hidden in a closure. The textarea is uncontrolled: Preact never
// writes its value, and the keyed gate block keeps it the same DOM node across a
// push, so a half-typed answer survives a refresh.
function AnswerForm({ workflowId, filePath }) {
  return html`<form class="answer" data-answer>
    <input type="hidden" name="cmd" value="answer" />
    <input type="hidden" name="workflow_id" value=${workflowId} />
    <input type="hidden" name="file_path" value=${filePath} />
    <textarea name="answer" aria-label="Your answer" placeholder="Your answer…" rows="2"></textarea>
    <div class="answer-actions"><button type="submit" class="btn">Send answer</button></div>
  </form>`;
}

function GateWait({ running }) {
  useSecondTick();
  return fmtSpan(Date.now() / 1000 - running.since_ts);
}

function gateLead(gate) {
  return gate.kind === "machine" ? "Waiting on a machine result" : "Waiting on you";
}

function GateBlock({ detail, gate, onCollapse }) {
  const waiting = detail.running && detail.running.wait_kind ? detail.running : null;
  return html`<div class="gate-block">
    <div class="gate-line">
      <${StateDot} state="blocked" />
      <b>${gateLead(gate)}</b>
      <span class="dim mono gate-meta" title=${gate.file_path}>${detail.node ? detail.node + " · " : ""}${waiting ? html`<${GateWait} running=${waiting} /> · ` : null}${gate.file_path}</span>
      ${onCollapse ? html`<button type="button" class="btn ghost gate-fold" aria-expanded="true" aria-controls="gate-blocks" onClick=${onCollapse}>Collapse</button>` : null}
    </div>
    <${Markdown} className="question" source=${gate.question} />
    ${gate.kind === "machine"
      ? html`<div class="no-gate">Waiting for a machine result.</div>`
      : html`<${AnswerForm} workflowId=${detail.id} filePath=${gate.file_path} />`}
  </div>`;
}

function GateStrip({ detail, collapsed }) {
  const root = useRef(null);
  const moveFocusTo = useRef("");
  useEffect(() => {
    const want = moveFocusTo.current;
    if (!want || !root.current) return;
    if ((want === "unfold") !== collapsed) return;
    moveFocusTo.current = "";
    const target = want === "unfold"
      ? root.current.querySelector(".gate-unfold")
      : root.current.querySelector(".gate-blocks textarea") || root.current.querySelector(".gate-fold");
    if (target) target.focus();
  });
  const fold = (next) => {
    moveFocusTo.current = next ? "unfold" : "answer";
    store.set({ gatesCollapsed: next });
  };
  const gates = detail.gates;
  const waiting = detail.running && detail.running.wait_kind ? detail.running : null;
  const answerable = gates.some((gate) => gate.kind !== "machine");
  return html`<div class="gate-strip" role="region" aria-label="Open gates" ref=${root}>
    ${collapsed
      ? html`<div class="gate-line gate-folded">
          <${StateDot} state="blocked" />
          <b>${gateLead(gates[0])}</b>
          ${gates.length > 1 ? html`<span class="chip">${gates.length} gates open</span>` : null}
          <span class="gq">${gates[0].preview || gates[0].question}</span>
          ${waiting ? html`<span class="dim mono gate-meta"><${GateWait} running=${waiting} /></span>` : null}
          <button type="button" class="btn gate-unfold" aria-expanded="false" aria-controls="gate-blocks" onClick=${() => fold(false)}>${answerable ? "Answer" : "Show"}</button>
        </div>`
      : null}
    <div class="gate-blocks" id="gate-blocks" hidden=${collapsed}>
      ${gates.map((gate, index) => html`<${GateBlock} key=${gate.file_path} detail=${detail} gate=${gate} onCollapse=${index === 0 ? () => fold(true) : null} />`)}
    </div>
  </div>`;
}

function fmtSpan(seconds) {
  const secs = Math.max(0, Math.round(seconds || 0));
  if (secs < 60) return secs + "s";
  if (secs < 3600) return Math.floor(secs / 60) + "m " + (secs % 60) + "s";
  return Math.floor(secs / 3600) + "h " + Math.floor((secs % 3600) / 60) + "m";
}

function fmtUsd(value) {
  return "$" + value.toFixed(2);
}

function fmtTokens(count) {
  if (count >= 1e6) return (count / 1e6).toFixed(1) + "M";
  if (count >= 1e3) return (count / 1e3).toFixed(1) + "k";
  return String(count);
}

function fmtPercent(part, whole) {
  return whole > 0 ? ((part / whole) * 100).toFixed(1) + "%" : "—";
}

function runningMark(running) {
  if (!running.wait_kind) return { lead: "running", cls: "ok" };
  const on = running.wait_kind === "operator" ? "the operator" : running.wait_kind;
  return { lead: "waiting on " + on, cls: "bad" };
}

const tickers = new Set();
let tickTimer = null;

function useSecondTick() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const listener = () => setTick((n) => n + 1);
    tickers.add(listener);
    if (tickTimer === null) tickTimer = setInterval(() => tickers.forEach((fn) => fn()), 1000);
    return () => {
      tickers.delete(listener);
      if (tickers.size === 0) {
        clearInterval(tickTimer);
        tickTimer = null;
      }
    };
  }, []);
}

function Elapsed({ since, seconds }) {
  useSecondTick();
  return fmtSpan(since === null || since === undefined ? seconds : Date.now() / 1000 - since);
}

function MiniClock({ clock, mini }) {
  useSecondTick();
  if (!clock) return mini ? html`<span class="mini">${mini}</span>` : null;
  const now = Date.now() / 1000;
  const idle = clock.idle_since_ts === null ? 0 : now - clock.idle_since_ts;
  return html`<span class="mini">${clock.label} ${fmtSpan(now - clock.since_ts)}${idle > 60 ? " · agent idle " + fmtSpan(idle) : ""}</span>`;
}

function timeCell(seconds, total) {
  const share = total > 0 ? Math.max(1, Math.min(100, (seconds / total) * 100)) : 0;
  return html`<span class="tb">${fmtSpan(seconds)}<s aria-hidden="true"><u style=${"width:" + share + "%"}></u></s></span>`;
}

function plural(count, one, many) {
  return count + " " + (count === 1 ? one : many);
}

function Tile({ label, value, children, id }) {
  return html`<div class="kpi" id=${id}>
    <div class="kk"><span>${label}</span></div>
    <div class="vv">${value}</div>
    <div class="ss">${children}</div>
  </div>`;
}

function CostTile({ figures, asOf }) {
  useSecondTick();
  if (!figures.reports_cost) {
    const who = figures.backends.length ? figures.backends.join(", ") : "This backend";
    return html`<${Tile} label="Cost" id="detail-cost-tile" value=${html`<span class="dim">—</span>`}>
      <span class="warn">${who} reports no cost</span>
      ${figures.est_usd !== null ? html` · est ${fmtUsd(figures.est_usd)} at list price` : null}
    <//>`;
  }
  const ago = asOf ? ", " + fmtSpan(Date.now() / 1000 - asOf) + " ago" : "";
  const burn = figures.active_s > 0 ? " · " + fmtUsd(figures.cost_usd / (figures.active_s / 3600)) + " per active hour" : "";
  return html`<${Tile} label="Cost so far" id="detail-cost-tile" value=${fmtUsd(figures.cost_usd)}>
    as of the last finished turn${ago} · ${figures.priced_turns} of ${figures.turns} turns priced${burn}
  <//>`;
}

function ItemsTile({ figures }) {
  if (!figures.items_total) {
    return html`<${Tile} label="Work items" id="detail-items-tile" value=${html`<span class="dim">—</span>`}>no item count reported<//>`;
  }
  let each = "none finished yet";
  if (figures.items_done > 0) {
    each = figures.reports_cost
      ? fmtUsd(figures.cost_usd / figures.items_done) + " per finished item"
      : "no cost per item without a price";
  }
  return html`<${Tile} label="Work items" id="detail-items-tile" value=${figures.items_done + " of " + figures.items_total}>${each}<//>`;
}

function AttentionTile({ standing, running }) {
  useSecondTick();
  const open = running && running.wait_kind === "operator" ? running : null;
  const gates = standing.gates + (open ? 1 : 0);
  const waited = standing.gate_wait_s + (open ? Math.max(0, Date.now() / 1000 - open.since_ts) : 0);
  const parts = [
    plural(standing.failed_steps, "failed step", "failed steps"),
    plural(standing.retries, "backend retry", "backend retries"),
    plural(standing.failed_gate_checks, "failed gate check", "failed gate checks"),
    plural(standing.churn_alerts, "churn alert", "churn alerts"),
  ];
  return html`<${Tile} label="Attention" id="detail-attention-tile" value=${plural(gates, "gate", "gates")}>
    ${fmtSpan(waited)} waiting · <span title=${parts.join(", ")}>${plural(standing.problems, "problem", "problems")}</span>
  <//>`;
}

function OverviewTiles({ data, running }) {
  const figures = data.figures;
  return html`<div class="kpis">
    <${CostTile} figures=${figures} asOf=${data.as_of_ts} />
    <${Tile} label="Active time" id="detail-active-tile" value=${fmtSpan(figures.active_s)}>${fmtSpan(figures.wall_s)} wall, ${plural(figures.sessions, "session", "sessions")}<//>
    <${ItemsTile} figures=${figures} />
    <${Tile} label="Agent turns" id="detail-turns-tile" value=${String(figures.turns)}>${plural(data.standing.retries, "backend retry", "backend retries")}<//>
    <${AttentionTile} standing=${data.standing} running=${running} />
  </div>`;
}

function normNote(strip, lasted) {
  const norm = strip.norm;
  if (!norm) return html`<span class="dim">reading the norm</span>`;
  if (strip.kind === "node") return html`<span class="dim">no finished visit to compare yet</span>`;
  if (norm.median_s === null) {
    return html`<span class="dim">no norm yet: ${norm.runs} comparable ${norm.runs === 1 ? "run" : "runs"}</span>`;
  }
  const usual = (strip.kind === "step" ? "this step" : "a turn here") + " usually takes " + fmtSpan(norm.median_s);
  return lasted > norm.median_s && strip.kind !== "between"
    ? html`<span class="warn">longer than usual: ${usual}</span>`
    : html`<span class="dim">${usual}</span>`;
}

function NowStrip({ strip }) {
  useSecondTick();
  const now = Date.now() / 1000;
  const lasted = now - strip.started_ts;
  const waiting = strip.kind === "wait";
  const operator = waiting && strip.wait_kind === "operator";
  const lead = waiting
    ? operator ? "Waiting on you" : "Waiting on " + strip.wait_kind
    : { step: "In step", between: "Between turns", node: "In node" }[strip.kind] || "In turn";
  const quiet = { step: "no agent in a step", between: "no turn running", node: "—" }[strip.kind] || "";
  let idle = html`<span class="dim">${quiet}</span>`;
  if (strip.idle_since_ts !== null) idle = fmtSpan(now - strip.idle_since_ts);
  return html`<div class="now" role="group" aria-label="Where the run is now">
    <div><span class="k2">Node</span><span class="v2"><span class=${"dot " + (operator ? "blocked" : "running")} aria-hidden="true"></span>${strip.node}</span></div>
    <div><span class="k2">${lead}</span><span class="v2">${fmtSpan(lasted)} ${waiting ? html`<span class="dim">no norm while waiting</span>` : normNote(strip, lasted)}</span></div>
    <div><span class="k2">Agent idle</span><span class="v2">${idle}</span></div>
    <div><span class="k2">Last beat</span><span class="v2">${strip.beat_ts ? fmtSpan(now - strip.beat_ts) + " ago" : "—"}</span></div>
  </div>`;
}

function flowKey(path, row) {
  return path + "/" + row.kind + ":" + row.name + ":" + (row.title || "");
}

function sortRows(rows, sort, reports) {
  const weight = (row) => {
    const value = reports ? row.cost_usd : row.output_tokens;
    return value === null ? -1 : value;
  };
  const rank = sort === "cost" ? weight : (row) => row.time_s;
  return [...rows].sort((a, b) => rank(b) - rank(a));
}

function moneyCell(row, data) {
  const reports = data.cost.reports_cost;
  if (!reports) return fmtTokens(row.output_tokens);
  return row.cost_usd !== null ? fmtUsd(row.cost_usd) : "—";
}

function moneyShare(row, data) {
  const reports = data.cost.reports_cost;
  return reports && row.cost_usd !== null ? fmtPercent(row.cost_usd, data.cost.usd) : "—";
}

function FlowRows({ rows, depth, path, open, toggle, data, sort }) {
  return sortRows(rows, sort, data.cost.reports_cost).map((row) => {
    const key = flowKey(path, row);
    const has = row.children.length > 0;
    const expanded = open.has(key);
    return html`<tr key=${key} class=${row.kind}>
        <td style=${"padding-left:" + (8 + depth * 14) + "px"}>
          ${has
            ? html`<button type="button" class="ch-btn" aria-expanded=${expanded ? "true" : "false"} aria-label=${(expanded ? "Collapse " : "Expand ") + row.name} onClick=${() => toggle(key)}>
                <span class="ch" aria-hidden="true">${expanded ? "▾" : "▸"}</span>${row.name}
              </button>`
            : html`<span class="ch" aria-hidden="true"></span><span>${row.name}</span>`}
          ${row.title ? html` <span class="dim" title=${"missing parent span " + row.title}>(no span recorded)</span>` : null}
        </td>
        <td>${row.visits === null ? html`<span class="none">—</span>` : row.visits}</td>
        <td class="barcell">${timeCell(row.time_s, data.time_s)}</td>
        <td>${fmtPercent(row.time_s, data.time_s)}</td>
        <td>${moneyCell(row, data)}</td>
        <td>${moneyShare(row, data)}</td>
        <td>${row.retries}</td>
      </tr>
      ${has && expanded
        ? html`<${FlowRows} key=${key + "/rows"} rows=${row.children} depth=${depth + 1} path=${key} open=${open} toggle=${toggle} data=${data} sort=${sort} />`
        : null}`;
  });
}

function RunningRow({ running, before, after }) {
  const mark = runningMark(running);
  const seconds = running.wait_kind ? running.wait_elapsed_s : running.elapsed_s;
  const blanks = (count) => Array.from({ length: count }, (_, i) => html`<td key=${i}><span class="none">—</span></td>`);
  return html`<tr class="flow cur">
    <td><span class="ch" aria-hidden="true"></span>${running.node} <span class=${"chip " + mark.cls}>${mark.lead} <${Elapsed} since=${running.since_ts} seconds=${seconds} /></span></td>
    ${blanks(before)}
    <td><${Elapsed} since=${running.since_ts} seconds=${seconds} /></td>
    ${blanks(after)}
  </tr>`;
}

const BREAKDOWN_TITLES = { flow: "Time and cost per flow", node: "Time and cost per node", item: "Time and cost per work item" };

function Segment({ id, label, value, options, onPick, marked }) {
  return html`<span id=${id} class=${"seg" + (marked ? " marked" : "")} role="group" aria-label=${label}>
    ${options.map(([key, text]) => html`<button type="button" key=${key} aria-pressed=${value === key ? "true" : "false"} onClick=${() => onPick(key)}>${text}</button>`)}
  </span>`;
}

function BreakdownHead({ view, sort, hasItems, finished }) {
  const views = [["flow", "By flow"], ["node", "By node"]];
  if (hasItems) views.push(["item", "By work item"]);
  return html`<div class="sec-h">
    <span>${BREAKDOWN_TITLES[view]}</span>
    ${finished
      ? html`<${Segment} label="Breakdown view" value=${view} options=${views} onPick=${(next) => setIn("breakdown", { view: next })} />`
      : null}
    ${finished && view !== "item"
      ? html`<span class="aside"><${Segment} label="Sort by" value=${sort} options=${[["time", "Time"], ["cost", "Cost"]]} onPick=${(next) => setIn("breakdown", { sort: next })} /></span>`
      : null}
  </div>`;
}

function FlowTree({ data, running, finished, sort, open, toggle, head }) {
  const reports = data.cost.reports_cost;
  return html`<section>
    ${head}
    <table class="tt" aria-label="Time and cost per flow">
      <thead><tr>
        <th scope="col">Flow › state › node</th>
        <th scope="col">Visits</th>
        <th scope="col">Time</th>
        ${finished
          ? html`<th scope="col">Time %</th>
              <th scope="col">${reports ? "Cost" : "Output tokens"}</th>
              <th scope="col">Cost %</th>
              <th scope="col">Retries</th>`
          : null}
      </tr></thead>
      <tbody>
        ${running ? html`<${RunningRow} running=${running} before=${1} after=${finished ? 4 : 0} />` : null}
        <${FlowRows} rows=${data.flows} depth=${0} path="" open=${open} toggle=${toggle} data=${data} sort=${sort} />
      </tbody>
    </table>
  </section>`;
}

const MEDIAN_WARN = 20;

function medianCell(row) {
  const norm = row.norm;
  if (!norm) return html`<span class="none">—</span>`;
  if (norm.median_s === null) {
    return html`<span class="none" title=${plural(norm.runs, "comparable run", "comparable runs") + ", under five"}>—</span>`;
  }
  const mean = row.time_s / row.samples;
  const change = ((mean - norm.median_s) / norm.median_s) * 100;
  const text = (change >= 0 ? "+" : "-") + Math.abs(change).toFixed(0) + "%";
  const title = "mean " + fmtSpan(mean) + ", median " + fmtSpan(norm.median_s) + " across " + plural(norm.runs, "run", "runs");
  return change >= MEDIAN_WARN
    ? html`<span class="warn" title=${title}>${text} longer</span>`
    : html`<span class="dim" title=${title}>${text}</span>`;
}

function medianHeading(runs) {
  return runs >= 5 ? "vs median of " + runs : "vs median: " + plural(runs, "run", "runs") + ", under five";
}

function NodeTable({ data, running, sort }) {
  const reports = data.cost.reports_cost;
  const rows = sortRows(data.nodes, sort, reports);
  return html`<table class="tt" aria-label="Time and cost per node">
    <thead><tr>
      <th scope="col">Node</th>
      <th scope="col">Kind</th>
      <th scope="col">Visits</th>
      <th scope="col">Time</th>
      <th scope="col">Mean</th>
      <th scope="col">${medianHeading(data.norm_runs)}</th>
      <th scope="col">Longest</th>
      <th scope="col">${reports ? "Cost" : "Output tokens"}</th>
      <th scope="col">Cost %</th>
      <th scope="col">Retries</th>
    </tr></thead>
    <tbody>
      ${running ? html`<${RunningRow} running=${running} before=${2} after=${6} />` : null}
      ${rows.map((row) => html`<tr key=${row.node} class="flow">
        <td><span class="ch" aria-hidden="true"></span>${row.node}</td>
        <td><span class="dim">${row.kind}</span></td>
        <td>${row.visits}</td>
        <td class="barcell">${timeCell(row.time_s, data.time_s)}</td>
        <td>${row.samples > 0 ? fmtSpan(row.time_s / row.samples) : html`<span class="none">—</span>`}</td>
        <td>${medianCell(row)}</td>
        <td>${fmtSpan(row.longest_s)}</td>
        <td>${moneyCell(row, data)}</td>
        <td>${moneyShare(row, data)}</td>
        <td>${row.retries}</td>
      </tr>`)}
    </tbody>
  </table>`;
}

function itemOutcome(row, open) {
  if (open) return html`<span class="chip ok">open</span>`;
  if (row.outcome === "done") return html`<span class="chip ok">done</span>`;
  if (row.outcome === "uncounted") return html`<span class="dim" title="The run's item count has not moved past this item">not counted</span>`;
  return html`<span class="none" title="No item count reported for this item">—</span>`;
}

function passMix(nodes) {
  return Object.entries(nodes)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .map(([node, count]) => node + " ×" + count);
}

function ItemTable({ data, running }) {
  const reports = data.cost.reports_cost;
  const { rows, outside, total } = data.items;
  const latest = running ? rows.reduce((best, row, i) => (row.last_ts > rows[best].last_ts ? i : best), 0) : -1;
  const money = (usd, tokens) => (reports ? (usd !== null ? fmtUsd(usd) : "—") : fmtTokens(tokens));
  return html`<table class="tt" aria-label="Time and cost per work item">
    <thead><tr>
      <th scope="col">Work item</th>
      <th scope="col">Passes</th>
      <th scope="col">Agent time</th>
      <th scope="col">${reports ? "Cost" : "Output tokens"}</th>
      <th scope="col">Outcome</th>
    </tr></thead>
    <tbody>
      ${rows.map((row, i) => html`<tr key=${row.work_id} class=${i === latest ? "flow cur" : "flow"}>
        <td><span class="ch" aria-hidden="true"></span>${row.work_id}</td>
        <td>${row.passes} <span class="dim" title=${passMix(row.nodes).join(", ")}>${passMix(row.nodes)[0].split(" ×")[0]}</span></td>
        <td class="barcell">${timeCell(row.seconds, total.time_s)}</td>
        <td>${money(row.cost_usd, row.output_tokens)}</td>
        <td>${itemOutcome(row, i === latest)}</td>
      </tr>`)}
      <tr class="flow">
        <td><span class="ch" aria-hidden="true"></span><span class="dim">outside any work item</span></td>
        <td><span class="none">—</span></td>
        <td class="barcell">${timeCell(outside.time_s, total.time_s)}</td>
        <td>${money(outside.cost_usd, outside.output_tokens)}</td>
        <td><span class="none">—</span></td>
      </tr>
      <tr class="workflow">
        <td><span class="ch" aria-hidden="true"></span>Total</td>
        <td><span class="none">—</span></td>
        <td>${fmtSpan(total.time_s)}</td>
        <td>${money(total.cost_usd, total.output_tokens)}</td>
        <td><span class="none">—</span></td>
      </tr>
    </tbody>
  </table>`;
}

function Breakdown({ data, running, finished }) {
  const { breakdown } = useStore();
  const [open, setOpen] = useState(() => new Set(data.flows.map((row) => flowKey("", row))));
  const toggle = (key) => {
    const next = new Set(open);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setOpen(next);
  };
  const hasItems = Boolean(data.items);
  const view = breakdown.view === "item" && !hasItems ? "flow" : breakdown.view;
  const head = html`<${BreakdownHead} view=${view} sort=${breakdown.sort} hasItems=${hasItems} finished=${finished} />`;
  if (view === "node") {
    return html`<section>${head}<${NodeTable} data=${data} running=${running} sort=${breakdown.sort} /></section>`;
  }
  if (view === "item") {
    return html`<section>${head}<${ItemTable} data=${data} running=${running} /></section>`;
  }
  return html`<${FlowTree} data=${data} running=${running} finished=${finished} sort=${breakdown.sort} open=${open} toggle=${toggle} head=${head} />`;
}

let overviewSeq = 0;

async function loadOverview(runId, rev = 0, refresh = false) {
  const seq = ++overviewSeq;
  if (!refresh) store.set({ overview: { runId, status: "loading", data: null, rev } });
  try {
    const response = await fetch("/api/run/" + encodeURIComponent(runId) + "/overview");
    if (!response.ok) throw new Error("overview " + response.status);
    const data = await response.json();
    if (seq === overviewSeq) store.set({ overview: { runId, status: "ready", data, rev } });
  } catch (err) {
    if (seq !== overviewSeq) return;
    if (refresh) store.set({ overview: { ...store.get().overview, rev } });
    else store.set({ overview: { runId, status: "failed", data: null, rev } });
  }
}

const CLOCK_SEGMENTS = [
  ["agent", "Agent turns", "seg-agent"],
  ["deterministic", "Deterministic", "seg-det"],
  ["infra", "Infrastructure", "seg-infra"],
  ["wait", "Waits", "seg-wait"],
  ["unclassified", "Unclassified", "seg-unc"],
  ["resume_gap", "Stopped between sessions", "seg-gap"],
];

function WallClock({ clock }) {
  const wall = clock.wall;
  const named = CLOCK_SEGMENTS.map(([key, label]) => label + " " + fmtSpan(clock[key])).join(", ");
  return html`<section id="detail-wall-clock" aria-label="Where the wall clock went">
    <div class="sec-h"><span>Where the wall clock went</span><span class="aside">${fmtSpan(wall)} from first to last record</span></div>
    <div class="tbar" role="img" aria-label=${"Wall clock split: " + named}>
      ${CLOCK_SEGMENTS.map(([key, , cls]) => html`<i class=${cls} style=${"width:" + (wall > 0 ? (clock[key] / wall) * 100 : 0) + "%"}></i>`)}
    </div>
    <ul class="legend">
      ${CLOCK_SEGMENTS.map(([key, label, cls]) => html`<li data-segment=${key} data-seconds=${clock[key]}><i class=${cls} aria-hidden="true"></i>${label} <b>${fmtSpan(clock[key])}</b></li>`)}
    </ul>
  </section>`;
}

function ModelCost({ row }) {
  if (row.cost_usd === null) return html`<span class="cov">not reported</span>`;
  const partial = row.cost_turns < row.turns ? html`<span class="cov">${row.cost_turns} of ${row.turns} priced</span>` : null;
  return html`${fmtUsd(row.cost_usd)}${partial}`;
}

function Models({ models }) {
  return html`<section id="detail-models">
    <div class="sec-h"><span>Models</span></div>
    <table class="tt" aria-label="Models">
      <thead><tr>
        <th scope="col">Model</th>
        <th scope="col">Turns</th>
        <th scope="col">Cost</th>
        <th scope="col">Output</th>
        <th scope="col">Cache read</th>
      </tr></thead>
      <tbody>
        ${models.map((row) => html`<tr key=${row.model} class="sub">
          <td>${row.model}</td>
          <td>${row.turns}</td>
          <td><${ModelCost} row=${row} /></td>
          <td>${fmtTokens(row.output_tokens)}</td>
          <td title=${fmtTokens(row.cache_read_tokens) + " tokens"}>${row.cache_read_share === null ? "—" : Math.round(row.cache_read_share * 100) + "%"}</td>
        </tr>`)}
      </tbody>
    </table>
  </section>`;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    return false;
  }
}

function CopyButton({ what, text }) {
  const [result, setResult] = useState("");
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    const ok = await copyText(text);
    setResult(ok ? "Copied " + what : "Could not copy " + what);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setResult(""), 4000);
  };
  const failed = result.startsWith("Could not");
  return html`<button type="button" class="copy" title=${"Copy " + what} aria-label=${"Copy " + what} onClick=${copy}><span aria-hidden="true">⧉</span></button><span class=${failed ? "copy-note bad" : "copy-note"} role="status">${result}</span>`;
}

function fmtWhen(ts) {
  return new Date(ts * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

function RunFacts({ facts, runId, checkout }) {
  const rows = [
    facts.started_ts ? ["Started", fmtWhen(facts.started_ts), "start time"] : null,
    facts.branch ? ["Branch", facts.branch, "branch"] : null,
    facts.run_dir ? ["Run dir", facts.run_dir, "run directory"] : null,
    checkout ? ["Checkout", checkout, "checkout path"] : null,
    ["Run id", runId, "run id"],
  ].filter(Boolean);
  return html`<section id="detail-facts">
    <div class="sec-h"><span>Run</span></div>
    <dl class="facts">
      ${rows.map(([label, value, what]) => html`<dt>${label}</dt><dd><span class="fv">${value}</span><${CopyButton} what=${what} text=${value} /></dd>`)}
    </dl>
  </section>`;
}

const ENDINGS = {
  terminal: "finished",
  ended: "finished",
  interrupted: "interrupted",
  reload: "reloaded",
  fail: "failed",
  aborted: "aborted",
};

function sessionEnding(row, last, live) {
  if (row.ended) {
    const word = ENDINGS[row.ended.terminal] || row.ended.terminal;
    const why = row.ended.message || row.ended.error_class;
    return why ? word + ": " + why : word;
  }
  return last && live ? "running" : "no recorded ending";
}

function Sessions({ sessions, live }) {
  return html`<section id="detail-sessions">
    <div class="sec-h"><span>Sessions</span><span class="aside">why the run stopped between them</span></div>
    <table class="tt" aria-label="Sessions">
      <thead><tr>
        <th scope="col">Session</th>
        <th scope="col">Started</th>
        <th scope="col">Active</th>
        <th scope="col">Stopped for</th>
        <th scope="col">How it stopped</th>
      </tr></thead>
      <tbody>
        ${sessions.map((row, i) => {
          const last = i === sessions.length - 1;
          const gap = row.gap_s !== null ? fmtSpan(row.gap_s) : last && live && !row.ended ? "still running" : "—";
          return html`<tr key=${row.start_ts} class="sub">
            <td>${i + 1}</td>
            <td>${fmtWhen(row.start_ts)}</td>
            <td>${fmtSpan(row.active_s)}</td>
            <td>${gap}</td>
            <td class="how">${sessionEnding(row, last, live)}</td>
          </tr>`;
        })}
      </tbody>
    </table>
  </section>`;
}

function Overview({ detail }) {
  const { overview } = useStore();
  const runId = detail.run_id;
  const rev = detail.figures_rev || 0;
  const mounted = useRef(false);
  useEffect(() => {
    const first = !mounted.current;
    mounted.current = true;
    const current = store.get().overview;
    if (!runId || current.status === "loading") return;
    if (current.status === "failed" && current.runId === runId) {
      if (first) loadOverview(runId, rev);
      return;
    }
    if (current.runId !== runId) loadOverview(runId, rev);
    else if (current.rev !== rev) loadOverview(runId, rev, true);
  }, [runId, rev, overview.status, overview.rev]);
  if (!runId) {
    return html`<div class="side-state"><h3>No figures for this run</h3>It has not reported a telemetry run id.</div>`;
  }
  if (overview.runId === runId && overview.status === "failed") {
    return html`<div class="side-state" role="alert">
      <h3>These figures could not be read</h3>
      The Details tab still works.
      <div class="acts"><button type="button" class="btn ghost retry-overview" onClick=${() => loadOverview(runId, rev)}>Retry now</button></div>
    </div>`;
  }
  if (overview.runId !== runId || overview.status !== "ready") {
    return html`<div class="detail-empty loading" role="status" aria-busy="true">
      <span class="spin" aria-hidden="true"></span>Reading this run's figures…
    </div>`;
  }
  const data = overview.data;
  const strip = detail.strip ? html`<${NowStrip} strip=${detail.strip} />` : null;
  if (!data.finished) {
    return html`<div class="ov">
      ${strip}
      <div class="side-state" role="status">
        <h3>No finished work yet</h3>
        Figures appear when the first node finishes.
      </div>
      <${RunFacts} facts=${data.facts} runId=${runId} checkout=${detail.head.checkout} />
      ${detail.running ? html`<${Breakdown} data=${Object.assign({}, data, { flows: [], items: null })} running=${detail.running} finished=${false} />` : null}
    </div>`;
  }
  return html`<div class="ov">
    ${strip}
    <${OverviewTiles} data=${data} running=${detail.running} />
    <${WallClock} clock=${data.clock} />
    <${Breakdown} key=${runId} data=${data} running=${detail.running} finished=${true} />
    <div class="pair">
      <${Models} models=${data.models} />
      <${RunFacts} facts=${data.facts} runId=${runId} checkout=${detail.head.checkout} />
    </div>
    <${Sessions} sessions=${data.sessions} live=${detail.head.state === "running" || detail.head.state === "blocked"} />
  </div>`;
}

function DetailsTab({ detail }) {
  return html`<div class="ov">
    <${AttendLink} runId=${detail.run_id} />
    ${detail.gates.length
      ? null
      : html`<div class="no-gate">
          Nothing to answer — this run is <b>${detail.state}</b>${detail.node
            ? html` at node <code>${detail.node}</code>`
            : null}.
        </div>`}
    <div class="live-sec">
      <div class="live-sec-head">Metrics</div>
      <${Metrics} metrics=${detail.metrics} />
    </div>
    <div class="live-sec">
      <div class="live-sec-head">Recent telemetry history</div>
      <${LogTrail} key=${detail.id} lines=${detail.history || []} />
    </div>
  </div>`;
}

const BASE_TABS = [
  ["overview", "Overview"],
  ["details", "Details"],
];

function runDiffSize(runDiff) {
  if (runDiff.status !== "ready") return null;
  const add = runDiff.files.reduce((sum, file) => sum + file.addedLines, 0);
  const del = runDiff.files.reduce((sum, file) => sum + file.deletedLines, 0);
  return add || del ? { add, del } : null;
}

function clockTime(epochMs) {
  const at = new Date(epochMs);
  return [at.getHours(), at.getMinutes(), at.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

function StillNote({ still }) {
  return html`<span class="sr-only" role="status">${still ? "The sidecar is still not answering." : ""}</span>`;
}

function StaleStrip({ lostAt, still, readAt, busy, onRetry }) {
  useSecondTick();
  const ago = fmtSpan((Date.now() - lostAt) / 1000);
  return html`<div id="detail-stale-strip" class="stale-strip" role="group" aria-label="Sidecar not answering">
    <${StillNote} still=${still} />
    <b>${still ? "The sidecar is still not answering." : "The sidecar stopped answering " + ago + " ago."}</b>
    ${still ? " It stopped answering " + ago + " ago." : ""} The run may still be working. This is the diff from ${clockTime(readAt)}.
    <button type="button" class="btn ghost" disabled=${busy} onClick=${onRetry}>Retry now</button>
  </div>`;
}

function StaleFiles({ id, lostAt, still }) {
  useSecondTick();
  const ago = fmtSpan((Date.now() - lostAt) / 1000);
  return html`<div id="detail-files-stale" class="side-state">
    <${StillNote} still=${still} />
    <h3>The sidecar stopped answering ${ago} ago</h3>
    The run may still be working.${still ? " The sidecar is still not answering." : ""}
    <div class="acts"><button type="button" class="btn ghost" onClick=${() => loadRunFiles(id)}>Retry now</button></div>
  </div>`;
}

function DiffRead({ runDiff, onRefresh }) {
  useSecondTick();
  const ago = Math.max(0, Math.round((Date.now() - runDiff.readAt) / 1000));
  return html`<span id="detail-diff-read" class="dim" style="font-size:11px">${runDiff.refreshing ? "reading…" : "read " + clockTime(runDiff.readAt) + " · " + fmtSpan(ago) + " ago"}</span>
    <button type="button" class="btn ghost" aria-label="Read the diff again" disabled=${runDiff.refreshing} onClick=${onRefresh}>Refresh</button>`;
}

function checkoutNames(snap) {
  return snap.runDiff.repos.length ? snap.runDiff.repos : snap.runFiles.repos;
}

function checkoutFor(id, snap = store.get()) {
  const repos = checkoutNames(snap);
  const chosen = snap.checkouts[id] || "";
  return repos.length && !repos.includes(chosen) ? repos[0] : chosen;
}

function setCheckout(id, name) {
  resetRunFiles();
  const snap = store.get();
  store.set({
    checkouts: Object.assign({}, snap.checkouts, { [id]: name }),
    runFiles: Object.assign(idleRunFiles(), { repos: snap.runFiles.repos }),
  });
}

function selectCheckout(id, name) {
  if (name === checkoutFor(id)) return;
  setCheckout(id, name);
  if (sidecarDown(id)) showKept(id);
  else loadRunDiff(id, true);
}

function CheckoutSelect({ id, repos, value }) {
  return html`<select
    class="repo-mini"
    id="detail-checkout"
    aria-label="Checkout"
    value=${value}
    onChange=${(e) => selectCheckout(id, e.target.value)}
  >${repos.map((name) => html`<option key=${name} value=${name} selected=${name === value}>${name || "(workspace root)"}</option>`)}</select>`;
}

function diffViewFor(id, snap = store.get()) {
  return snap.diffViews[id] === BRANCH_VIEW ? BRANCH_VIEW : UNCOMMITTED_VIEW;
}

function selectDiffView(id, view) {
  if (view === diffViewFor(id)) return;
  const snap = store.get();
  store.set({ diffViews: Object.assign({}, snap.diffViews, { [id]: view }) });
  if (sidecarDown(id)) showKept(id);
  else loadRunDiff(id, true);
}

function DiffViewSwitch({ id, value }) {
  return html`<${Segment}
    id="detail-diff-view-switch"
    label="Diff view"
    value=${value}
    marked=${true}
    options=${[[UNCOMMITTED_VIEW, "Uncommitted"], [BRANCH_VIEW, "Since branch start"]]}
    onPick=${(next) => selectDiffView(id, next)}
  />`;
}

function DetailTabs({ id, tab, hasDiff, stale, runDiff, repos, checkout, view }) {
  const tabs = hasDiff ? BASE_TABS.concat([["files", "Files"], ["diff", "Diff"]]) : BASE_TABS;
  const size = hasDiff && !stale ? runDiffSize(runDiff) : null;
  const switcher = hasDiff && tab === "diff" ? html`<${DiffViewSwitch} id=${id} value=${view} />` : null;
  const picker = hasDiff && (tab === "diff" || tab === "files") && repos.length > 1
    ? html`<${CheckoutSelect} id=${id} repos=${repos} value=${checkout} />`
    : null;
  const read = tab === "diff" && hasDiff && !stale && runDiff.readAt && !(view === BRANCH_VIEW && runDiff.start && runDiff.start.state !== "found")
    ? html`<${DiffRead} runDiff=${runDiff} onRefresh=${() => loadRunDiff(runDiff.id)} />`
    : null;
  const onKeyDown = (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const index = tabs.findIndex(([id]) => id === tab);
    const next = tabs[(index + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length][0];
    store.set({ tab: next });
    requestAnimationFrame(() => {
      const button = document.getElementById("tab-" + next);
      if (button) button.focus();
    });
    e.preventDefault();
  };
  return html`<div class="dtabs">
    <div class="dtablist" role="tablist" aria-label="Run detail" onKeyDown=${onKeyDown}>
    ${tabs.map(([id, label]) => {
      const counted = id === "diff" && size;
      const marked = id === "diff" && stale;
      return html`<button
        type="button"
        class="dtab"
        role="tab"
        id=${"tab-" + id}
        aria-selected=${id === tab ? "true" : "false"}
        aria-controls="detail-panel"
        aria-label=${marked ? "Diff, stale" : counted ? "Diff, " + plural(size.add, "line", "lines") + " added, " + plural(size.del, "line", "lines") + " removed" : null}
        tabindex=${id === tab ? "0" : "-1"}
        onClick=${() => store.set({ tab: id })}
      >${label}${marked ? html`<span id="detail-diff-stale" class="cnt"><span class="chip warn">stale</span></span>` : counted ? html`<span id="detail-diff-count" class="cnt"><span class="add">+${size.add}</span> <span class="del">−${size.del}</span></span>` : null}</button>`;
    })}
    </div>
    ${switcher || picker || read ? html`<span class="right">${switcher}${picker}${read}</span>` : null}
  </div>`;
}

function useHoldPlace() {
  const held = useRef({ el: null, top: 0, scroll: 0, watcher: null });
  useLayoutEffect(() => {
    const now = held.current;
    const hold = () => {
      if (!now.el || !now.el.isConnected) return;
      const top = now.el.getBoundingClientRect().top;
      const moved = top - now.top;
      now.top = top;
      if (Math.abs(moved) >= 0.5 && now.scroll > 0) now.el.scrollTop = now.scroll + moved;
      now.scroll = now.el.scrollTop;
    };
    const scroller = document.querySelector("#detail-panel > .ov");
    if (scroller === now.el) {
      hold();
      return;
    }
    if (now.watcher) now.watcher.disconnect();
    now.watcher = null;
    now.el = scroller;
    if (!scroller) return;
    now.top = scroller.getBoundingClientRect().top;
    now.scroll = scroller.scrollTop;
    scroller.addEventListener("scroll", () => { now.scroll = scroller.scrollTop; });
    if (typeof ResizeObserver !== "undefined") {
      now.watcher = new ResizeObserver(hold);
      now.watcher.observe(scroller);
      for (const above of scroller.parentElement.children) {
        if (above === scroller) break;
        now.watcher.observe(above);
      }
    }
  });
  useEffect(() => () => {
    if (held.current.watcher) held.current.watcher.disconnect();
  }, []);
}

function Detail() {
  const snap = useStore();
  const { selected, detail, tab: chosen, gatesCollapsed, runs, runDiff, runFiles } = snap;
  useHoldPlace();
  const row = runs.find((run) => run.id === selected);
  const container = !!row && !row.native && row.state !== "finished";
  const live = container && row.sidecar;
  const stale = container && !row.sidecar && !!snap.diffKept[selected];
  const hasDiff = live || stale;
  const mark = stale
    ? { lostAt: snap.sidecarLost[selected] || Date.now(), still: !!snap.stillDown[selected], anyRead: Object.keys(snap.diffKept[selected].entries).length > 0 }
    : null;
  useRunDiff(selected, live, stale, runDiff.id, runDiff.shownKept);
  useRunFiles(selected, live, chosen === "files", runFiles.id);
  const tab = (chosen === "diff" || chosen === "files") && !hasDiff ? "overview" : chosen;
  useEffect(() => {
    if (chosen !== tab) store.set({ tab });
  }, [chosen, tab]);
  if (!selected) return null;
  if (!detail) return html`<div class="detail-empty loading" role="status" aria-label="Loading telemetry history" aria-busy="true">
    <span class="spin" aria-hidden="true"></span>Loading telemetry history…
  </div>`;
  if (!detail.found) return html`<div class="detail-empty">Run not found.</div>`;
  return html`
    <${RunHead} head=${detail.head} onClose=${closeDetail} sidecar=${live ? "live" : stale ? "lost" : ""} />
    ${detail.gates.length ? html`<${GateStrip} detail=${detail} collapsed=${gatesCollapsed} />` : null}
    <${DetailTabs} id=${selected} tab=${tab} hasDiff=${hasDiff} stale=${stale} runDiff=${runDiff} repos=${checkoutNames(snap)} checkout=${checkoutFor(selected, snap)} view=${diffViewFor(selected, snap)} />
    <div class="fill" id="detail-panel" role="tabpanel" aria-labelledby=${"tab-" + tab}>
      ${tab === "diff"
        ? html`<${DiffTab} runDiff=${runDiff} mark=${mark} />`
        : tab === "files"
          ? (mark ? html`<${StaleFiles} id=${selected} lostAt=${mark.lostAt} still=${mark.still} />` : html`<${FilesTab} runFiles=${runFiles} />`)
          : tab === "details"
            ? html`<${DetailsTab} detail=${detail} />`
            : html`<${Overview} detail=${detail} />`}
    </div>
  `;
}

// A fetch and a push race whenever a run is selected. The sequence number settles
// it in the fetch's favour only while nothing newer has landed: a `detail` frame
// that arrives first is the fresher truth and must not be overwritten by the
// reply to a request that was issued before it.
let detailSeq = 0;

async function select(id) {
  const seq = ++detailSeq;
  overviewSeq++;
  const same = id === store.get().selected;
  const breakdown = same ? store.get().breakdown : { view: "flow", sort: "time" };
  const gatesCollapsed = same ? store.get().gatesCollapsed : false;
  runDiffSeq++;
  resetRunFiles();
  store.set({ selected: id, detail: null, tab: "overview", gatesCollapsed, runDiff: idleRunDiff(), runFiles: idleRunFiles(), overview: { runId: "", status: "idle", data: null, rev: 0 }, breakdown });
  if (sendWatch(id)) return;
  try {
    const response = await fetch("/worker/" + encodeURIComponent(id));
    const body = await response.json();
    if (seq === detailSeq && store.get().detail === null) store.set({ detail: body });
  } catch (err) {
    // Reconnecting re-declares the watch and seeds the pane.
  }
}

function closeDetail() {
  detailSeq++;
  overviewSeq++;
  sendWatch("");
  runDiffSeq++;
  resetRunFiles();
  store.set({ selected: null, detail: null, tab: "overview", gatesCollapsed: false, runDiff: idleRunDiff(), runFiles: idleRunFiles(), overview: { runId: "", status: "idle", data: null, rev: 0 }, breakdown: { view: "flow", sort: "time" } });
}

/** A pushed refresh of the open run. It carries the whole pane — gates included —
 *  because the components are keyed, so a gate that opened or closed appears
 *  without a round trip and the answer textarea keeps its DOM node regardless. */
function onDetail(msg) {
  if (msg.id !== store.get().selected) return;
  store.set({ detail: msg.detail });
}

// The answer form is rendered by Preact and re-rendered on every push, so the
// submit handler is delegated rather than bound per-form. The client serializes
// the frame itself, which is also what lets a failed send *say* it failed.
const sentAnswers = new Map();

function gateKey(workflowId, filePath) {
  return workflowId + "\n" + filePath;
}

function answerBox(workflowId, filePath) {
  for (const form of document.querySelectorAll("form[data-answer]")) {
    if (form.elements.workflow_id.value === workflowId && form.elements.file_path.value === filePath) {
      return form.querySelector("textarea");
    }
  }
  return null;
}

function wireAnswerForm() {
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("form[data-answer]");
    if (!form) return;
    e.preventDefault();
    const data = new FormData(form);
    const payload = {};
    data.forEach((value, key) => {
      payload[key] = value;
    });
    if (sendCommand(payload)) {
      sentAnswers.set(gateKey(payload.workflow_id, payload.file_path), payload.answer);
      form.querySelector("textarea").value = "";
    } else pushToast("blocked", "✗ not sent", "No connection to groom — your answer is still in the box.", 7000);
  });
}

/** highlight.js output is escaped HTML, so it is safe to set; `null` means the
 *  library is absent or choked and the caller should fall back to a text node. */
function highlight(text, lang) {
  if (!window.hljs) return null;
  try {
    if (lang && hljs.getLanguage(lang)) return hljs.highlight(text, { language: lang, ignoreIllegals: true }).value;
    return hljs.highlightAuto(text).value;
  } catch (err) {
    return null;
  }
}

// The language comes from the server (projection.file_lang) so the extension
// table is one table, next to the rest of the presentation policy.
function fileCode(content, lang) {
  const markup = highlight(content, lang);
  return markup === null
    ? html`<code class=${lang ? "language-" + lang : null}>${content}</code>`
    : html`<code
        class=${lang ? "language-" + lang : null}
        dangerouslySetInnerHTML=${{ __html: markup }}
      ></code>`;
}

// --------------------------------------------------------------------------- //
// Diff rendering shared by the run Diff tab
// --------------------------------------------------------------------------- //
// diff2html both parses the unified text and renders it, and it escapes what it
// emits — which is why the raw diff rides through the wire unsplit rather than
// having half a parser reimplemented server-side.
function fileDiffMarkup(file) {
  if (!window.Diff2Html) return "";
  return Diff2Html.html([file], { drawFileList: false, matching: "lines", outputFormat: "line-by-line", colorScheme: "dark" });
}

function diffEntries(files) {
  return files.map((file, i) => ({
    path: file.newName && file.newName !== "/dev/null" ? file.newName : file.oldName,
    idx: i,
    add: file.addedLines,
    del: file.deletedLines,
  }));
}

// --------------------------------------------------------------------------- //
// Attendant panel — the log of claudes groom sent at a stopped run
// --------------------------------------------------------------------------- //
// Two states and no refresh button, by design: a row is written `running` before
// the process emits a byte and flipped to `completed` by the thread that owns it,
// so there is nothing here to poll. The list is fetched when the pane opens and
// again when a `state` frame reports a revision it has not seen.
function attendWhen(epoch) {
  if (!epoch) return "";
  return new Date(epoch * 1000).toLocaleString();
}

function attendElapsed(row) {
  const end = row.ended_at || Date.now() / 1000;
  const secs = Math.max(0, Math.round(end - (row.started_at || 0)));
  if (secs < 60) return secs + "s";
  if (secs < 3600) return Math.floor(secs / 60) + "m " + (secs % 60) + "s";
  return Math.floor(secs / 3600) + "h " + Math.floor((secs % 3600) / 60) + "m";
}

function AttendRow({ row, selected }) {
  const running = row.status === "running";
  const session = (row.session_ids || [])[row.session_ids.length - 1] || "";
  const outcome = running
    ? "running"
    : "completed" +
      (row.exit_code === null || row.exit_code === undefined ? "" : " · exit " + row.exit_code) +
      (row.released_state ? " · " + row.released_state : "");
  return html`<div class=${"attend-row" + (selected ? " active" : "")}>
    <button
      type="button"
      class="attend-open"
      aria-current=${selected ? "true" : null}
      onClick=${() => openAttendSession(session, row)}
      disabled=${!session}
    >
      <span class="line1">
        <${StateDot} state=${running ? "running" : "finished"} />
        <span class="repo-branch">${row.workflow || "(unknown workflow)"}</span>
        <span class="wid">${row.run_id}</span>
        <span class=${"attend-status " + row.status}>${outcome}</span>
      </span>
      <span class="attend-reason">${row.reason || row.kind}</span>
      <span class="attend-meta">${attendWhen(row.started_at)} · ${attendElapsed(row)}${
        row.node ? " · node " + row.node : ""
      }</span>
    </button>
    ${running
      ? html`<button
          type="button"
          class="attend-stop"
          title="Kill this attendant and take the run in your own terminal"
          onClick=${() => stopAttend(row.job_id)}
        >
          Stop
        </button>`
      : null}
  </div>`;
}

function AttendList() {
  const { attend } = useStore();
  if (attend.status === "idle" || attend.status === "loading") {
    return html`<div class="empty loading"><span class="spin"></span>Loading attendances…</div>`;
  }
  if (attend.status === "error") return html`<div class="empty">failed to load</div>`;
  if (!attend.sessions.length) {
    return html`<div class="empty">
      No attendance yet — groom has not sent an agent at a parked or dead run.
    </div>`;
  }
  return attend.sessions.map(
    (row) =>
      html`<${AttendRow}
        key=${row.job_id}
        row=${row}
        selected=${attend.selected === ((row.session_ids || [])[row.session_ids.length - 1] || "")}
      />`
  );
}

// A tool call is one line plus its arguments and its result, both collapsed: the
// point of this pane is reading what the agent *said*, with the tool traffic
// there to be opened when a claim needs checking.
function AttendTool({ entry }) {
  const body = [entry.detail, entry.result].filter(Boolean).join("\n\n");
  const head = html`<span class=${"at-tool-head" + (entry.failed ? " failed" : "")}
    ><span class="at-tool-name">${entry.name}</span><span class="at-tool-sum">${entry.summary}</span></span
  >`;
  if (!body) return html`<div class="at-tool">${head}</div>`;
  return html`<details class="at-tool">
    <summary>${head}</summary>
    <pre class="at-tool-body">${body}</pre>
  </details>`;
}

function AttendEntry({ entry }) {
  if (entry.kind === "divider") return html`<div class="at-divider">${entry.label}</div>`;
  if (entry.kind === "tool") return html`<${AttendTool} entry=${entry} />`;
  if (entry.collapsed) {
    return html`<details class=${"at-msg " + entry.role}>
      <summary class="at-role">${entry.role}</summary>
      <${Markdown} className="at-text" source=${entry.text} />
    </details>`;
  }
  return html`<div class=${"at-msg " + (entry.role || "assistant") + (entry.sidechain ? " sidechain" : "")}>
    <span class="at-role">${entry.role || "assistant"}</span>
    <${Markdown} className="at-text" source=${entry.text} />
  </div>`;
}

function AttendDetail() {
  const { attend } = useStore();
  const record = attend.record;
  if (!attend.selected) {
    return html`<div class="detail-empty">Select an attendance to read what the agent did.</div>`;
  }
  if (!record) return html`<div class="detail-empty">Loading…</div>`;
  if (record.error) return html`<div class="detail-empty">failed to load this transcript</div>`;
  const row = record.record || {};
  const attempts = record.attempts || [];
  return html`
    <div class="at-head">
      <div class="at-head-line">
        <span class="repo-branch">${row.workflow || ""}</span>
        <span class="wid">${row.run_id || ""}</span>
        <span class=${"attend-status " + (row.status || "")}>${row.status || ""}</span>
      </div>
      ${row.reason ? html`<div class="at-head-reason">${row.reason}</div>` : null}
      ${row.run_dir ? html`<div class="at-head-dir">${row.run_dir}</div>` : null}
      <div class="at-resume" title="Resume this session in your own terminal">${record.resume}</div>
      ${attempts.length > 1
        ? html`<div class="at-attempts">
            earlier sessions:
            ${attempts.slice(0, -1).map((id) => html`<code key=${id}>${id}</code>`)}
          </div>`
        : null}
    </div>
    ${record.present
      ? html`<div class="at-body">
          ${record.entries.map((entry, i) => html`<${AttendEntry} key=${i} entry=${entry} />`)}
        </div>`
      : html`<div class="detail-empty">
          No transcript on disk for this session yet — it is copied when the agent exits.
        </div>`}
  `;
}

function loadAttend() {
  setIn("attend", { status: store.get().attend.status === "ready" ? "ready" : "loading" });
  fetch("/api/attend/sessions")
    .then((r) => r.json())
    .then((body) =>
      setIn("attend", { status: "ready", sessions: body.sessions || [], mode: body.mode || "off" })
    )
    .catch(() => setIn("attend", { status: "error", sessions: [] }));
}

function openAttendSession(sessionId, row) {
  if (!sessionId) return;
  setIn("attend", { selected: sessionId, record: null });
  fetch("/api/attend/sessions/" + encodeURIComponent(sessionId))
    .then((r) => r.json())
    .then((body) => {
      if (store.get().attend.selected !== sessionId) return; // a later click won
      if (!body.record && row) body.record = row;
      setIn("attend", { record: body });
    })
    .catch(() => {
      if (store.get().attend.selected !== sessionId) return;
      setIn("attend", { record: { error: true } });
    });
}

function stopAttend(jobId) {
  fetch("/api/attend/sessions/" + encodeURIComponent(jobId) + "/stop", { method: "POST" })
    .then((r) => r.json())
    .then((body) => {
      if (!body.ok) pushToast("blocked", "✗ not stopped", "That attendant was already gone.", 5000);
      loadAttend();
    })
    .catch(() => pushToast("blocked", "✗ not stopped", "groom did not answer the stop.", 7000));
}

/** The link a blocked or dead run draws to whoever is working it. Reads the
 *  `state` frame's per-run summary, so it is current without a second fetch. */
function AttendLink({ runId }) {
  const { attend } = useStore();
  const entry = runId ? attend.by_run[runId] : null;
  if (!entry) return null;
  const label = entry.status === "running" ? "an attendant is on this run" : "last attendant";
  return html`<button
    type="button"
    class="attend-link"
    onClick=${() => {
      setMode("attend");
      openAttendSession(entry.session_id || "", null);
    }}
  >
    <${StateDot} state=${entry.status === "running" ? "running" : "finished"} />
    ${label}${entry.reason ? " · " + entry.reason : ""}
  </button>`;
}

// --------------------------------------------------------------------------- //
// Settings panel
// --------------------------------------------------------------------------- //
// One toggle for now, and it is deliberately not an echo of what was posted: the
// server answers with the freshly re-read effective settings, because a save that
// silently did not take is the one failure a switch can hide. `sources` says where
// each value actually came from — a mode set in the environment is not something
// this toggle can overrule, and the operator has to be able to see that.
function AttendSetting() {
  const { settings } = useStore();
  const value = settings.attend;
  if (!value) return html`<div class="setting-loading">Loading settings…</div>`;
  const on = value.mode !== "off";
  const source = (value.sources || {}).mode || "default";
  return html`
    <div class="setting-head">
      <label class="switch">
        <input
          type="checkbox"
          checked=${on}
          disabled=${settings.saving}
          onChange=${(e) => saveAttendEnabled(e.target.checked)}
        />
        <span class="switch-label">Attend parked and dead runs</span>
      </label>
      <span class="setting-mode">${value.mode}${settings.saving ? " · saving…" : ""}</span>
    </div>
    <p class="setting-why">
      When a run parks on an operator gate or dies, groom sends an agent at it —${" "}
      <code>headless</code> spawns <code>${value.cli}</code> and owns the process;${" "}
      <code>session</code> only publishes the job for a terminal you already have open.
      Turning this off leaves every stopped run for you.
    </p>
    <p class="setting-source">value from ${source}${source === "environment" ? " — the config is not carrying this key" : ""}</p>
  `;
}

function loadAttendSettings() {
  fetch("/api/settings/attend")
    .then((r) => r.json())
    .then((body) => setIn("settings", { status: "ready", attend: body }))
    .catch(() => setIn("settings", { status: "error" }));
}

function saveAttendEnabled(enabled) {
  setIn("settings", { saving: true });
  fetch("/api/settings/attend", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ enabled: !!enabled }),
  })
    .then((r) => r.json())
    .then((body) => setIn("settings", { saving: false, attend: body }))
    .catch(() => {
      setIn("settings", { saving: false });
      pushToast("blocked", "✗ not saved", "groom did not accept the setting.", 7000);
    });
}

// --------------------------------------------------------------------------- //
// Dispatch panel — config-declared work queues
// --------------------------------------------------------------------------- //
// No socket push (a queue's occupancy lives only in the semaphores a request
// thread holds, never broadcast state), so this pane polls while it is open —
// the same tradeoff `doRefresh` makes for a manual docker rescan, just on a timer
// instead of a button. `_dispatchPoll` is cleared whenever the mode changes away.
let _dispatchPoll = null;

function DispatchQueueRow({ row }) {
  return html`<div class="dispatch-queue-row">
    <button
      type="button"
      class=${"dispatch-queue-open" + (store.get().dispatch.selectedQueue === row.name ? " active" : "")}
      onClick=${() => selectDispatchQueue(row.name)}
    >
      <span class="repo-branch">${row.name}</span>
      <span class="wid">${row.running}/${row.concurrency} running</span>
      <span class="attend-meta">${row.command}</span>
    </button>
  </div>`;
}

function DispatchQueues() {
  const { dispatch } = useStore();
  if (dispatch.status === "idle" || dispatch.status === "loading") {
    return html`<div class="empty loading"><span class="spin"></span>Loading queues…</div>`;
  }
  if (dispatch.status === "error") return html`<div class="empty">failed to load</div>`;
  if (!dispatch.queues.length) {
    return html`<div class="empty">
      No dispatch queues configured — add a [groom.dispatch.${"<name>"}] section to enable one.
    </div>`;
  }
  return dispatch.queues.map((row) => html`<${DispatchQueueRow} key=${row.name} row=${row} />`);
}

// One control per `params` entry the selected queue's config declares — a select
// for a fixed choice (e.g. which agent CLI to run on), a text input otherwise (e.g.
// a plan path). The form is uncontrolled, like `AnswerForm`: Preact never owns the
// input values, so `wireDispatchEnqueueForm`'s delegated submit handler reads them
// straight off the DOM via `FormData` at submit time.
function DispatchEnqueueField({ param }) {
  const id = "dispatch-field-" + param.name;
  const label = html`<label class="dispatch-field-label" for=${id}>${param.label}${param.required ? " *" : ""}</label>`;
  const control =
    param.type === "select"
      ? html`<select id=${id} name=${param.name} required=${param.required} defaultValue=${param.default || ""}>
          ${param.default ? null : html`<option value="">select…</option>`}
          ${(param.options || []).map((opt) => html`<option value=${opt}>${opt}</option>`)}
        </select>`
      : html`<input type="text" id=${id} name=${param.name} required=${param.required} defaultValue=${param.default} />`;
  return html`<div class="dispatch-field">${label}${control}</div>`;
}

function DispatchEnqueueForm() {
  const { dispatch } = useStore();
  const queue = dispatch.selectedQueue;
  if (!queue) return null;
  const row = dispatch.queues.find((q) => q.name === queue);
  const params = (row && row.params) || [];
  if (!params.length) return null;
  return html`<form class="dispatch-enqueue" data-dispatch-enqueue key=${queue}>
    <input type="hidden" name="queue" value=${queue} />
    ${params.map((param) => html`<${DispatchEnqueueField} key=${param.name} param=${param} />`)}
    <div class="dispatch-enqueue-actions"><button type="submit" class="btn">Enqueue</button></div>
  </form>`;
}

function enqueueDispatchItem(queue, params) {
  return fetch("/api/dispatch/" + encodeURIComponent(queue) + "/items", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ params: params }),
  })
    .then((r) => r.json())
    .then((body) => {
      loadDispatchItems(queue);
      loadDispatchQueues();
      if (body.ok) closeDispatchEnqueue();
      else pushToast("blocked", "✗ not enqueued", "groom did not accept the item.", 7000);
      return body;
    })
    .catch(() => {
      pushToast("blocked", "✗ not enqueued", "groom did not accept the item.", 7000);
    });
}

// Delegated the same way `wireAnswerForm` is: the form is re-rendered whenever the
// selected queue's items change, so a handler bound per-form would go stale.
function wireDispatchEnqueueForm() {
  document.addEventListener("submit", (e) => {
    const form = e.target.closest("form[data-dispatch-enqueue]");
    if (!form) return;
    e.preventDefault();
    const data = new FormData(form);
    const queue = data.get("queue");
    data.delete("queue");
    const params = {};
    data.forEach((value, key) => {
      params[key] = value;
    });
    // Read the fields before clearing them: the form is uncontrolled, so this is
    // the only place its values ever exist, and the operator expects a blank form
    // back the moment they hit submit rather than their last plan path lingering.
    form.reset();
    enqueueDispatchItem(queue, params);
  });
}

function DispatchItemRow({ item, queue, active }) {
  const pending = item.status === "pending";
  const running = item.status === "running";
  return html`<div class=${"dispatch-item-row" + (active ? " active" : "")}>
    <button
      type="button"
      class="dispatch-item-open"
      aria-current=${active ? "true" : null}
      onClick=${() => selectDispatchItem(item.item_id)}
    >
      <span class=${"attend-status " + item.status}>${item.status}</span>
      <span class="wid">${item.item_id}</span>
      <span class="attend-meta">${item.exit_code === null || item.exit_code === undefined ? "" : "exit " + item.exit_code}</span>
    </button>
    ${pending
      ? html`<button type="button" class="attend-stop" onClick=${() => cancelDispatchItem(queue, item.item_id)}>
          Cancel
        </button>`
      : null}
    ${running
      ? html`<button type="button" class="attend-stop" onClick=${() => stopDispatchItem(queue, item.item_id)}>
          Stop
        </button>`
      : null}
  </div>`;
}

function DispatchItems() {
  const { dispatch } = useStore();
  if (!dispatch.selectedQueue) {
    return html`<div class="detail-empty">Select a queue to see its items.</div>`;
  }
  if (!dispatch.items.length) {
    return html`<div class="empty">no items on this queue.</div>`;
  }
  return dispatch.items.map(
    (item) => html`<${DispatchItemRow}
      key=${item.item_id}
      item=${item}
      queue=${dispatch.selectedQueue}
      active=${dispatch.selectedItem === item.item_id}
    />`
  );
}

// The item detail: params and pid, read straight off the already-loaded items
// list — `loadDispatchItems` carries both on every row, so selecting an item is a
// pure store update, no second fetch.
function DispatchItemDetail() {
  const { dispatch } = useStore();
  if (!dispatch.selectedItem) {
    return html`<div class="detail-empty">Select an item to see its parameters.</div>`;
  }
  const item = dispatch.items.find((i) => i.item_id === dispatch.selectedItem);
  if (!item) {
    return html`<div class="detail-empty">That item is no longer on this queue.</div>`;
  }
  return html`
    <div class="at-head-line">
      <span class="repo-branch">${item.queue || dispatch.selectedQueue || ""}</span>
      <span class="wid">${item.item_id}</span>
      <span class=${"attend-status " + item.status}>${item.status}</span>
    </div>
    <div class="dispatch-detail-row"><span class="dispatch-detail-label">command</span><span class="attend-meta">${item.command || ""}</span></div>
    <div class="dispatch-detail-row"><span class="dispatch-detail-label">pid</span><span class="attend-meta">${item.pid ?? "—"}</span></div>
    <div class="dispatch-detail-row"><span class="dispatch-detail-label">exit code</span><span class="attend-meta">${
      item.exit_code === null || item.exit_code === undefined ? "—" : item.exit_code
    }</span></div>
    <div class="dispatch-detail-row"><span class="dispatch-detail-label">started</span><span class="attend-meta">${attendWhen(item.started_at)}</span></div>
    <div class="dispatch-detail-label">params</div>
    <pre class="at-tool-body">${JSON.stringify(item.params || {}, null, 2)}</pre>
  `;
}

function loadDispatchQueues() {
  setIn("dispatch", { status: store.get().dispatch.status === "ready" ? "ready" : "loading" });
  fetch("/api/dispatch/queues")
    .then((r) => r.json())
    .then((body) => setIn("dispatch", { status: "ready", queues: body.queues || [] }))
    .catch(() => setIn("dispatch", { status: "error", queues: [] }));
}

function loadDispatchItems(queue) {
  fetch("/api/dispatch/" + encodeURIComponent(queue) + "/items")
    .then((r) => r.json())
    .then((body) => {
      if (store.get().dispatch.selectedQueue !== queue) return; // a later click won
      setIn("dispatch", { items: body.items || [] });
    });
}

function selectDispatchQueue(queue) {
  setIn("dispatch", { selectedQueue: queue, items: [], selectedItem: null });
  loadDispatchItems(queue);
  document.getElementById("btn-dispatch-new").disabled = false;
}

function selectDispatchItem(itemId) {
  setIn("dispatch", { selectedItem: itemId });
}

function cancelDispatchItem(queue, itemId) {
  fetch("/api/dispatch/" + encodeURIComponent(queue) + "/items/" + encodeURIComponent(itemId), {
    method: "DELETE",
  })
    .then((r) => r.json())
    .then((body) => {
      if (!body.ok) pushToast("blocked", "✗ not cancelled", "That item was already running or done.", 5000);
      loadDispatchItems(queue);
      loadDispatchQueues();
    });
}

function stopDispatchItem(queue, itemId) {
  fetch("/api/dispatch/" + encodeURIComponent(queue) + "/items/" + encodeURIComponent(itemId) + "/stop", {
    method: "POST",
  })
    .then((r) => r.json())
    .then((body) => {
      if (!body.ok) pushToast("blocked", "✗ not stopped", "That item was already gone.", 5000);
      loadDispatchItems(queue);
      loadDispatchQueues();
    });
}

function loadDispatch() {
  loadDispatchQueues();
  const selected = store.get().dispatch.selectedQueue;
  if (selected) loadDispatchItems(selected);
  if (_dispatchPoll) clearInterval(_dispatchPoll);
  _dispatchPoll = setInterval(() => {
    if (store.get().mode !== "dispatch") return;
    loadDispatch();
  }, 5000);
}

function stopDispatchPoll() {
  if (_dispatchPoll) clearInterval(_dispatchPoll);
  _dispatchPoll = null;
}

// --------------------------------------------------------------------------- //
// Activity bar (mode switch)
// --------------------------------------------------------------------------- //
function setMode(mode) {
  if (!document.getElementById(mode + "-pane")) mode = "runs";
  document.querySelector(".app").dataset.mode = mode;
  document.querySelectorAll(".act-btn").forEach((b) => {
    const on = b.dataset.mode === mode;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  store.set({ mode: mode });
  if (mode !== "dispatch") stopDispatchPoll();
  if (mode === "attend") loadAttend();
  else if (mode === "dispatch") loadDispatch();
  else if (mode === "settings") loadAttendSettings();
}

// Manual reconcile: rescan docker (adds + prunes vanished workers). The
// resulting state broadcast arrives on the socket, so nothing is rendered here.
function doRefresh(btn) {
  if (btn.dataset.busy) return;
  btn.dataset.busy = "1";
  btn.classList.add("spinning");
  fetch("/refresh", { method: "POST" }).finally(() => {
    delete btn.dataset.busy;
    btn.classList.remove("spinning");
  });
}

// --------------------------------------------------------------------------- //
// Command palette
// --------------------------------------------------------------------------- //
const pal = document.getElementById("palette");
const palIn = document.getElementById("palette-input");
let palInvoker = null; // focus goes back here on close — never dropped to <body>

// Reads the fleet from the store rather than from the rendered rows: the palette
// should find a run the filter box is currently hiding.
function paletteHits(runs, query) {
  const q = query.trim().toLowerCase();
  return q ? runs.filter((r) => rowHaystack(r).indexOf(q) >= 0) : runs;
}

function PaletteResults() {
  const { runs, palette } = useStore();
  const hits = paletteHits(runs, palette.query);
  const active = Math.max(0, Math.min(hits.length - 1, palette.active));
  useEffect(() => {
    if (!hits.length) {
      palIn.removeAttribute("aria-activedescendant");
      return;
    }
    palIn.setAttribute("aria-activedescendant", "presult-" + active);
    const el = document.getElementById("presult-" + active);
    if (el) el.scrollIntoView({ block: "nearest" });
  });
  return hits.map((run, i) => {
    const hint = run.state === "blocked" ? "gate" : run.live || run.state;
    const text = [run.repo, "#" + run.row_id, run.doing].filter(Boolean).join(" ");
    return html`<div
      class=${"presult" + (i === active ? " active" : "")}
      id=${"presult-" + i}
      key=${run.id}
      role="option"
      aria-selected=${i === active ? "true" : "false"}
      onClick=${() => choosePaletteHit(run.id)}
    >
      <${StateDot} state=${run.state} />
      <span class="rb">${text}</span>
      <span class="hint">${hint}</span>
    </div>`;
  });
}

function openPalette(invoker) {
  palInvoker = invoker || document.activeElement;
  pal.classList.add("open");
  palIn.setAttribute("aria-expanded", "true");
  palIn.value = "";
  setIn("palette", { open: true, query: "", active: 0 });
  palIn.focus();
}

function closePalette() {
  if (!pal.classList.contains("open")) return;
  pal.classList.remove("open");
  palIn.setAttribute("aria-expanded", "false");
  palIn.removeAttribute("aria-activedescendant");
  setIn("palette", { open: false });
  if (palInvoker && palInvoker.focus && pal.contains(document.activeElement)) palInvoker.focus();
}

// --------------------------------------------------------------------------- //
// Dispatch "new run" dialog
// --------------------------------------------------------------------------- //
const dispatchModal = document.getElementById("dispatch-enqueue-modal");
let dispatchModalInvoker = null; // focus goes back here on close — never dropped to <body>

function dispatchModalFocusables() {
  return [].slice.call(
    dispatchModal.querySelectorAll("button:not([disabled]), input:not([type=hidden]):not([disabled]), select:not([disabled])")
  );
}

function openDispatchEnqueue(invoker) {
  dispatchModalInvoker = invoker || document.activeElement;
  dispatchModal.classList.add("open");
  const focusables = dispatchModalFocusables();
  const firstField = focusables.find((el) => el.tagName !== "BUTTON") || focusables[0];
  if (firstField) firstField.focus();
}

function closeDispatchEnqueue() {
  if (!dispatchModal.classList.contains("open")) return;
  dispatchModal.classList.remove("open");
  const focus = document.activeElement;
  const dropped = !focus || focus === document.body || dispatchModal.contains(focus);
  if (dispatchModalInvoker && dispatchModalInvoker.focus && dropped) dispatchModalInvoker.focus();
}

function trapDispatchModalTab(e) {
  const focusables = dispatchModalFocusables();
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const inside = dispatchModal.contains(document.activeElement);
  if (e.shiftKey && (!inside || document.activeElement === first)) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && (!inside || document.activeElement === last)) {
    e.preventDefault();
    first.focus();
  }
}

function movePaletteActive(delta) {
  const snap = store.get();
  const hits = paletteHits(snap.runs, snap.palette.query);
  if (!hits.length) return;
  setIn("palette", { active: Math.max(0, Math.min(hits.length - 1, snap.palette.active + delta)) });
}

function choosePaletteHit(id) {
  setMode("runs");
  select(id);
  closePalette();
}

// --------------------------------------------------------------------------- //
// Toasts + server events
// --------------------------------------------------------------------------- //
function pushToast(variant, titleText, bodyText, ttl) {
  const t = document.createElement("div");
  t.className = "toast " + variant;
  const title = document.createElement("div");
  title.className = "t-title";
  title.textContent = titleText;
  t.appendChild(title);
  if (bodyText) {
    const b = document.createElement("div");
    b.className = "t-body";
    b.textContent = bodyText;
    t.appendChild(b);
  }
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), ttl || 7000);
}

// A new block (or a fired alert rule): toast + optional browser notification.
function onNotify(message) {
  const body = message || "A workflow needs your input.";
  pushToast("blocked", "⛔ worker blocked", body, 7000);
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification("groom: workflow blocked", { body: body });
  }
}

// A gate somebody answered. Every tab is told, and the confirmation plus dropping
// the held answer is all this has to do: the pane itself is refreshed by the
// `detail` push the same command triggers, which now carries the gates — so no
// tab re-fetches, and a half-typed answer against a different run is never touched.
function onAnswered(msg) {
  sentAnswers.delete(gateKey(msg.id, msg.file_path));
  pushToast("ok", "✓ answer sent", "", 3500);
}

function onAnswerRejected(msg) {
  const key = gateKey(msg.id, msg.file_path);
  const sent = sentAnswers.get(key);
  sentAnswers.delete(key);
  const box = sent === undefined ? null : answerBox(msg.id, msg.file_path);
  if (box && !box.value) box.value = sent;
  pushToast("blocked", "✗ answer not taken", msg.reason || "groom refused the answer.", 7000);
}

// --------------------------------------------------------------------------- //
// Wiring
// --------------------------------------------------------------------------- //
function wireEvents() {
  document.getElementById("activitybar").addEventListener("click", (e) => {
    const btn = e.target.closest(".act-btn");
    if (btn) setMode(btn.dataset.mode);
  });

  document.querySelector("#runs .filter").addEventListener("input", (e) => {
    store.set({ query: e.target.value });
  });

  // Worker selection + the status-bar/settings buttons, delegated: the rows are
  // re-rendered on every push, and a delegated handler outlives every one of them.
  document.body.addEventListener("click", (e) => {
    if (e.target.closest("form")) return; // don't hijack the answer form
    if (e.target.closest(".fd-tree")) return; // panel-local handlers own these
    const node = e.target.closest("[data-worker-id]");
    if (node) {
      select(node.dataset.workerId);
      return;
    }
    const refreshBtn = e.target.closest("#btn-refresh-bar");
    if (refreshBtn) {
      doRefresh(refreshBtn);
      return;
    }
    const palBtn = e.target.closest("#btn-palette");
    if (palBtn) {
      openPalette(palBtn);
      return;
    }
    const newRunBtn = e.target.closest("#btn-dispatch-new");
    if (newRunBtn && !newRunBtn.disabled) {
      openDispatchEnqueue(newRunBtn);
      return;
    }
    if (e.target.closest(".dispatch-enqueue-close")) {
      closeDispatchEnqueue();
      return;
    }
    if (e.target === dispatchModal) {
      closeDispatchEnqueue();
      return;
    }
  });

  palIn.addEventListener("input", (e) => setIn("palette", { query: e.target.value, active: 0 }));
  palIn.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    movePaletteActive(e.key === "ArrowDown" ? 1 : -1);
  });

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (pal.classList.contains("open")) closePalette();
      else openPalette();
      return;
    }
    if (e.key === "Escape") {
      closePalette();
      closeDispatchEnqueue();
      return;
    }
    // modal focus trap: the palette's only focusable element is its input
    if (pal.classList.contains("open") && e.key === "Tab") {
      e.preventDefault();
      palIn.focus();
      return;
    }
    if (dispatchModal.classList.contains("open") && e.key === "Tab") {
      trapDispatchModalTab(e);
      return;
    }
    if (pal.classList.contains("open") && e.key === "Enter") {
      const snap = store.get();
      const hits = paletteHits(snap.runs, snap.palette.query);
      const hit = hits[Math.max(0, Math.min(hits.length - 1, snap.palette.active))];
      if (hit) choosePaletteHit(hit.id);
      return;
    }
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if (!typing && (e.key === "j" || e.key === "k")) {
      const rows = [].slice.call(document.querySelectorAll("#runs-list .row"));
      const idx = rows.findIndex((r) => r.dataset.workerId === store.get().selected);
      const next = rows[Math.max(0, Math.min(rows.length - 1, idx + (e.key === "j" ? 1 : -1)))];
      if (next) {
        setMode("runs");
        select(next.dataset.workerId);
      }
    }
  });

  // Notification permission is requested on the operator's first click rather
  // than on load — an unprompted permission dialog is a dark pattern and Chrome
  // ignores it anyway without a user gesture.
  if ("Notification" in window && Notification.permission === "default") {
    document.body.addEventListener(
      "click",
      function requestOnce() {
        Notification.requestPermission();
        document.body.removeEventListener("click", requestOnce);
      },
      { once: true }
    );
  }
}

// --------------------------------------------------------------------------- //
// Boot
// --------------------------------------------------------------------------- //
// One island per region of the shell. Each is mounted *into* an element the
// static HTML already carries its role and live-region attributes on, so those
// never re-render and a screen reader keeps tracking the same region.
const ISLANDS = [
  ["runs-list", Fleet],
  ["statusbar", StatusBar],
  ["detail", Detail],
  ["attend-list", AttendList],
  ["attend-detail", AttendDetail],
  ["dispatch-queues", DispatchQueues],
  ["dispatch-enqueue", DispatchEnqueueForm],
  ["dispatch-items", DispatchItems],
  ["dispatch-detail", DispatchItemDetail],
  ["setting-attend", AttendSetting],
  ["palette-results", PaletteResults],
];
ISLANDS.forEach(([id, Component]) => render(html`<${Component} />`, document.getElementById(id)));

const runsPane = document.getElementById("runs-pane");
store.subscribe((snap) => runsPane.classList.toggle("has-detail", !!snap.selected));

const runsButton = document.querySelector('.act-btn[data-mode="runs"]');
const runsBadge = document.getElementById("runs-badge");
function paintRunsBadge(snap) {
  const blocked = ((snap.status || {}).counts || {}).blocked || 0;
  const show = snap.mode !== "runs" && blocked > 0;
  const name = show ? "Runs, " + plural(blocked, "blocked run", "blocked runs") : "Runs";
  runsBadge.hidden = !show;
  runsBadge.textContent = show ? String(blocked) : "";
  runsButton.setAttribute("aria-label", name);
  runsButton.title = name;
}
store.subscribe(paintRunsBadge);
paintRunsBadge(store.get());

wireEvents();
wireAnswerForm();
wireDispatchEnqueueForm();
startConnection();

// --------------------------------------------------------------------------- //
// Run Diff tab — a connected container run's uncommitted change
// --------------------------------------------------------------------------- //
// The read is driven by the selection and the sidecar's presence, not by the tab
// being open: the tab's size shows before it is opened, and the one read serves both.

function idleRunDiff() {
  return { id: "", status: "idle", view: UNCOMMITTED_VIEW, files: [], untracked: [], path: null, readAt: 0, reported: true, refreshing: false, repos: [], start: null, startState: "", key: "", shownKept: false };
}

function keptKey(name, view) {
  return name + "\n" + view;
}

function keepDiff(id, repo, view, entry) {
  const snap = store.get();
  const prev = snap.diffKept[id] || { repos: [], entries: {} };
  const repos = entry.repos.length ? entry.repos : prev.repos;
  const kept = { repos, entries: Object.assign({}, prev.entries, { [keptKey(repo || repos[0] || "", view)]: entry }) };
  store.set({ diffKept: Object.assign({}, snap.diffKept, { [id]: kept }) });
}

function pickDiffFile(path) {
  const { id, key } = store.get().runDiff;
  setIn("runDiff", { path });
  const kept = store.get().diffKept[id];
  if (!kept || !kept.entries[key]) return;
  const entries = Object.assign({}, kept.entries, { [key]: Object.assign({}, kept.entries[key], { path }) });
  store.set({ diffKept: Object.assign({}, store.get().diffKept, { [id]: Object.assign({}, kept, { entries }) }) });
}

function showKept(id) {
  const snap = store.get();
  const kept = snap.diffKept[id];
  if (!kept) return;
  runDiffSeq++;
  const view = diffViewFor(id, snap);
  const chosen = snap.checkouts[id] || "";
  const name = kept.repos.length && !kept.repos.includes(chosen) ? kept.repos[0] : chosen;
  const entry = kept.entries[keptKey(name, view)];
  const shown = entry
    ? Object.assign({}, entry, { id, shownKept: true, refreshing: false })
    : Object.assign(idleRunDiff(), { id, view, status: "unread", repos: kept.repos, shownKept: true });
  store.set({ runDiff: shown });
}

function markStill(id) {
  store.set({ stillDown: Object.assign({}, store.get().stillDown, { [id]: true }) });
}

let runDiffSeq = 0;

function useRunDiff(id, live, stale, have, shownKept) {
  useEffect(() => {
    if (live && (have !== id || shownKept)) loadRunDiff(id);
    else if (stale && (have !== id || !shownKept)) showKept(id);
    else if (!live && !stale && have) {
      runDiffSeq++;
      setIn("runDiff", idleRunDiff());
    }
  }, [id, live, stale, have, shownKept]);
}

function loadRunDiff(id, switched) {
  const seq = ++runDiffSeq;
  const before = store.get().runDiff;
  const known = before.id === id ? before.repos : [];
  const view = diffViewFor(id);
  const refresh = !switched && before.id === id && before.status === "ready" && before.view === view;
  const repo = checkoutFor(id);
  if (!store.get().diffKept[id]) store.set({ diffKept: Object.assign({}, store.get().diffKept, { [id]: { repos: [], entries: {} } }) });
  if (refresh) setIn("runDiff", { refreshing: true });
  else setIn("runDiff", Object.assign(idleRunDiff(), { id, view, status: "loading", repos: known }));
  const failed = (repos) => {
    if (seq === runDiffSeq) setIn("runDiff", Object.assign(idleRunDiff(), { id, view, status: "failed", repos: repos || known }));
  };
  const miss = () => {
    if (seq !== runDiffSeq) return;
    if (sidecarDown(id)) {
      markStill(id);
      showKept(id);
    } else failed();
  };
  const query = "?repo=" + encodeURIComponent(repo) + (view === BRANCH_VIEW ? "&view=" + BRANCH_VIEW : "");
  fetch("/diff/" + encodeURIComponent(id) + query)
    .then((response) => {
      if (!response.ok) throw new Error("diff " + response.status);
      return response.json();
    })
    .then((body) => {
      if (seq !== runDiffSeq) return;
      const repos = body.repos || [];
      if (repos.length && repo && !repos.includes(repo)) {
        setCheckout(id, repos[0]);
        return loadRunDiff(id, true);
      }
      if (body.served === "volume" || (body.failed && sidecarDown(id))) return miss();
      const text = body.diff || "";
      if (body.failed || (text.trim() && !window.Diff2Html)) return failed(repos);
      const start = view !== BRANCH_VIEW ? null : branchStart(body);
      const shown = !start || start.state === "found";
      const files = shown && text.trim() ? Diff2Html.parse(text) : [];
      const entry = {
        id,
        view,
        start,
        startState: start ? start.state : "",
        status: "ready",
        files,
        untracked: shown ? body.untracked || [] : [],
        reported: body.reported !== false,
        readAt: Date.now(),
        refreshing: false,
        path: refresh ? before.path : null,
        repos,
        key: keptKey(repo || repos[0] || "", view),
        shownKept: false,
      };
      setIn("runDiff", entry);
      keepDiff(id, repo, view, entry);
    })
    .catch(miss);
}

const UNTRACKED_GROUP = "Not tracked by git yet";

function branchStart(body) {
  if (!body.based) return { state: "old", commit: "", branch: "", ref: "" };
  const state = body.base_reason === "default-branch" ? "default-branch" : body.base_reason ? "not-found" : "found";
  return { state, commit: body.base || "", branch: body.base_branch || "", ref: body.base_ref || "" };
}

function startName(start) {
  return start.commit.slice(0, 7) + " on " + start.branch;
}

function BranchStartNotice({ runDiff }) {
  const start = runDiff.start;
  if (start.state === "old") {
    return html`<div class="fd-view"><div id="detail-diff-branch-old" class="detail-empty">This view needs a newer sidecar. Uncommitted still works.</div></div>`;
  }
  if (start.state === "default-branch") {
    return html`<div class="fd-view"><div id="detail-diff-branch-default" class="detail-empty">This checkout is on ${start.branch}, its default branch, so it has no branch of its own to compare.</div></div>`;
  }
  return html`<div id="detail-diff-branch-missing" class="side-state" role="status">
    <h3>Where this branch started could not be found</h3>
    ${start.branch
      ? "This branch shares no history with " + start.branch + ". Uncommitted still works."
      : "The checkout has no default branch to compare with. Uncommitted still works."}
    <div class="acts"><button type="button" class="btn ghost" onClick=${() => loadRunDiff(runDiff.id)}>Retry now</button></div>
  </div>`;
}

function DiffTab({ runDiff, mark }) {
  const strip = mark && runDiff.status === "ready"
    ? html`<${StaleStrip} lostAt=${mark.lostAt} still=${mark.still} readAt=${runDiff.readAt} busy=${runDiff.refreshing} onRetry=${() => loadRunDiff(runDiff.id)} />`
    : null;
  return html`${strip}<${DiffBody} runDiff=${runDiff} mark=${mark} />`;
}

function DiffBody({ runDiff, mark }) {
  const branch = runDiff.view === BRANCH_VIEW;
  if (runDiff.status === "unread" && mark) {
    return html`<div id="detail-diff-unread" class="side-state">
      <${StillNote} still=${mark.still} />
      <h3>${mark.anyRead ? "This view was not read before the sidecar stopped answering" : "The sidecar stopped answering before a diff was read"}</h3>
      The run may still be working.${mark.still ? " The sidecar is still not answering." : ""}
      <div class="acts"><button type="button" class="btn ghost" onClick=${() => loadRunDiff(runDiff.id)}>Retry now</button></div>
    </div>`;
  }
  if (runDiff.status === "idle" || runDiff.status === "loading" || runDiff.status === "unread") {
    return html`<div class="detail-empty loading" role="status" aria-busy="true">
      <span class="spin" aria-hidden="true"></span>${branch ? "Reading the change since the branch started…" : "Reading the diff…"}
    </div>`;
  }
  if (runDiff.status === "failed") {
    return html`<div id="detail-diff-unreadable" class="side-state" role="alert">
      <h3>${branch ? "This view could not be read" : "This diff could not be read"}</h3>
      ${branch ? "This does not mean there is no change." : "This does not mean there are no changes."}
      <div class="acts"><button type="button" class="btn ghost" onClick=${() => loadRunDiff(runDiff.id)}>Retry now</button></div>
    </div>`;
  }
  if (branch && runDiff.start.state !== "found") return html`<${BranchStartNotice} runDiff=${runDiff} />`;
  if (!runDiff.files.length && !runDiff.untracked.length) {
    if (branch) {
      return html`<div class="fd-view"><div id="detail-diff-branch-empty" class="detail-empty">This branch has no change since it started at ${startName(runDiff.start)}.</div></div>`;
    }
    return html`<div class="fd-view"><div class="detail-empty">${runDiff.reported
      ? "There are no uncommitted changes in this checkout."
      : "This sidecar is too old to report a failed read, so it cannot confirm there are no changes."}</div></div>`;
  }
  const entries = diffEntries(runDiff.files);
  const tracked = compactDirs(buildTree(entries));
  const untrackedNode = {
    dirs: {},
    files: runDiff.untracked.map((path) => ({ name: path, entry: { path, untracked: true } })),
  };
  const paths = new Map(entries.map((entry) => [entry.path, entry]));
  runDiff.untracked.forEach((path) => paths.set(path, { path, untracked: true }));
  const firstTracked = firstLeaf(tracked);
  const current = paths.has(runDiff.path) ? runDiff.path : firstTracked ? firstTracked.entry.path : null;
  const leaf = (node) => {
    const on = node.entry.path === current;
    return html`<button
      type="button"
      key=${(node.entry.untracked ? "u:" : "t:") + node.entry.path}
      class=${"tree-file" + (on ? " active" : "")}
      aria-current=${on ? "true" : null}
      onClick=${() => pickDiffFile(node.entry.path)}
    >
      <span class="fname">${node.name}</span>
      ${node.entry.untracked ? null : html`<span class="fstat"><span class="add">+${node.entry.add}</span> <span class="del">−${node.entry.del}</span></span>`}
    </button>`;
  };
  const chosen = current === null ? null : paths.get(current);
  let view;
  if (!chosen) view = html`<div class="detail-empty">${branch ? "No tracked file has changed since this branch started at " + startName(runDiff.start) + "." : "No tracked file has changed in this checkout."}</div>`;
  else if (chosen.untracked) view = html`<div class="detail-empty">${chosen.path} has no diff because git does not track it yet.</div>`;
  else view = html`<${RunFileDiff} file=${runDiff.files[chosen.idx]} entry=${chosen} scope=${branch ? "since " + startName(runDiff.start) : "uncommitted"} title=${branch ? "against " + runDiff.start.commit + " from " + runDiff.start.ref : null} />`;
  return html`<div class=${"fd-split" + (mark ? " stale" : "")}>
    <div class="fd-tree">
      <${TreeLevel} node=${tracked} leaf=${leaf} />
      ${runDiff.untracked.length ? html`<${TreeDir} name=${UNTRACKED_GROUP} node=${untrackedNode} leaf=${leaf} />` : null}
    </div>
    <div class="fd-view">${view}</div>
  </div>`;
}

function RunFileDiff({ file, entry, scope, title }) {
  const renamed = file.oldName && file.newName && file.oldName !== file.newName && !file.isNew && !file.isDeleted;
  const kind = file.isNew ? "new file" : file.isDeleted ? "deleted file" : renamed ? "renamed from " + file.oldName : "";
  return html`<div class="run-file-diff">
    <div id="detail-diff-file-head" class="diff-head">
      <span class="diff-path">${entry.path}</span>
      <span class="add">+${entry.add}</span> <span class="del">−${entry.del}</span>
      ${kind ? html`<span class="dim">${kind}</span>` : null}
      <span class="dim diff-scope" title=${title}>${scope}</span>
    </div>
    <div dangerouslySetInnerHTML=${{ __html: fileDiffMarkup(file) }}></div>
  </div>`;
}

function firstLeaf(node) {
  const dirs = Object.keys(node.dirs).sort();
  for (const name of dirs) {
    const found = firstLeaf(node.dirs[name]);
    if (found) return found;
  }
  const files = node.files.slice().sort((a, b) => a.name.localeCompare(b.name));
  return files.length ? files[0] : null;
}

// --------------------------------------------------------------------------- //
// Run Files tab — a connected container run's checkout, read-only
// --------------------------------------------------------------------------- //
// Unlike the Diff read, the tree is read when the tab is first opened for a
// selection, so selecting a run costs no tree read. Leaving the tab keeps the
// tree, the open file and the collapsed folders; selecting another run, or losing the sidecar, drops them.
function idleRunFiles() {
  return {
    id: "",
    status: "idle",
    paths: [],
    reported: true,
    repos: [],
    path: null,
    shut: {},
    view: { status: "idle", content: "", lang: "", reported: true },
  };
}

function toggleRunFolder(key) {
  const shut = Object.assign({}, store.get().runFiles.shut);
  if (shut[key]) delete shut[key];
  else shut[key] = true;
  setIn("runFiles", { shut });
}

let runFilesSeq = 0;
let runFileSeq = 0;

function resetRunFiles() {
  runFilesSeq++;
  runFileSeq++;
}

function useRunFiles(id, present, open, have) {
  useEffect(() => {
    if (present && open && have !== id) loadRunFiles(id);
    else if (!present && have) {
      resetRunFiles();
      setIn("runFiles", idleRunFiles());
    }
  }, [id, present, open, have]);
}

function loadRunFiles(id) {
  resetRunFiles();
  const seq = runFilesSeq;
  const known = store.get().runFiles.repos;
  const repo = checkoutFor(id);
  if (!sidecarDown(id)) setIn("runFiles", Object.assign(idleRunFiles(), { id, status: "loading", repos: known }));
  const failed = (repos) => {
    if (seq === runFilesSeq) setIn("runFiles", Object.assign(idleRunFiles(), { id, status: "failed", repos: repos || known }));
  };
  const miss = () => {
    if (seq !== runFilesSeq) return;
    if (sidecarDown(id)) markStill(id);
    else failed();
  };
  fetch("/files/" + encodeURIComponent(id) + "?repo=" + encodeURIComponent(repo))
    .then((response) => {
      if (!response.ok) throw new Error("files " + response.status);
      return response.json();
    })
    .then((body) => {
      if (seq !== runFilesSeq) return;
      const repos = body.repos || [];
      if (repos.length && repo && !repos.includes(repo)) {
        setCheckout(id, repos[0]);
        return loadRunDiff(id, true);
      }
      if (body.served === "volume" || (body.failed && sidecarDown(id))) return miss();
      if (body.failed) return failed(repos);
      setIn("runFiles", { status: "ready", paths: body.paths || [], reported: body.reported !== false, repos });
    })
    .catch(miss);
}

function openRunFile(id, path) {
  const seq = ++runFileSeq;
  setIn("runFiles", { path, view: { status: "loading", content: "", lang: "", reported: true } });
  const failed = () => {
    if (seq === runFileSeq) setIn("runFiles", { view: { status: "failed", content: "", lang: "", reported: true } });
  };
  fetch("/file/" + encodeURIComponent(id) + "?repo=" + encodeURIComponent(checkoutFor(id)) + "&path=" + encodeURIComponent(path))
    .then((response) => {
      if (!response.ok) throw new Error("file " + response.status);
      return response.json();
    })
    .then((body) => {
      if (seq !== runFileSeq) return;
      if (body.failed) return failed();
      setIn("runFiles", {
        view: { status: "ready", content: body.content || "", lang: body.lang || "", reported: body.reported !== false },
      });
    })
    .catch(failed);
}

function ReadFailed({ id, title, text, onRetry }) {
  return html`<div id=${id} class="side-state" role="alert">
    <h3>${title}</h3>
    ${text}
    <div class="acts"><button type="button" class="btn ghost" onClick=${onRetry}>Retry now</button></div>
  </div>`;
}

function FilesTab({ runFiles }) {
  if (runFiles.status === "idle" || runFiles.status === "loading") {
    return html`<div class="detail-empty loading" role="status" aria-busy="true">
      <span class="spin" aria-hidden="true"></span>Reading the checkout…
    </div>`;
  }
  if (runFiles.status === "failed") {
    return html`<${ReadFailed}
      id="detail-files-unreadable"
      title="This checkout could not be read"
      text=""
      onRetry=${() => loadRunFiles(runFiles.id)}
    />`;
  }
  if (!runFiles.paths.length) {
    return html`<div class="fd-view"><div class="detail-empty">${runFiles.reported
      ? "This checkout has no files."
      : "This sidecar is too old to report a failed read, so it cannot confirm this checkout has no files."}</div></div>`;
  }
  const tree = compactDirs(buildTree(runFiles.paths.map((path) => ({ path }))));
  const leaf = (node) => {
    const path = node.entry.path;
    const on = path === runFiles.path;
    return html`<button
      type="button"
      key=${path}
      class=${"tree-file" + (on ? " active" : "")}
      aria-current=${on ? "true" : null}
      onClick=${() => openRunFile(runFiles.id, path)}
    >
      <span class="fname">${node.name}</span>
    </button>`;
  };
  return html`<div class="fd-split">
    <div class="fd-tree"><${TreeLevel} node=${tree} leaf=${leaf} fold=${{ shut: runFiles.shut, toggle: toggleRunFolder }} /></div>
    <div class="fd-view"><${RunFileView} runFiles=${runFiles} /></div>
  </div>`;
}

function RunFileView({ runFiles }) {
  const { path, view } = runFiles;
  if (path === null) return html`<div class="detail-empty">Select a file to read it.</div>`;
  if (view.status === "loading") {
    return html`<div class="detail-empty loading" role="status" aria-busy="true">
      <span class="spin" aria-hidden="true"></span>Reading ${path}…
    </div>`;
  }
  if (view.status === "failed") {
    return html`<${ReadFailed}
      id="detail-file-unreadable"
      title=${path + " could not be read"}
      text="This does not mean the file is empty."
      onRetry=${() => openRunFile(runFiles.id, path)}
    />`;
  }
  const lines = view.content.replace(/\n$/, "").split("\n");
  const head = html`<div id="detail-files-file-head" class="file-head">${path}${view.content
    ? " · " + plural(lines.length, "line", "lines") + (view.lang ? " · " + view.lang : "")
    : ""}</div>`;
  if (!view.content) {
    return html`${head}<div class="detail-empty">${view.reported
      ? "This file is empty."
      : "This sidecar is too old to report a failed read, so it cannot confirm this file is empty."}</div>`;
  }
  return html`${head}<div class="code-view">
    <pre class="code-gutter" aria-hidden="true">${lines.map((_, i) => i + 1).join("\n")}</pre>
    <pre class="file-pre hljs">${fileCode(view.content, view.lang)}</pre>
  </div>`;
}
