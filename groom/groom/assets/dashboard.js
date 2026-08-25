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
// ships (`#runs-list`, `#statusbar`, `#detail`, `#repo-menu`, the files/diff
// trees and views, `#traces-list`, `#palette-results`), so the live-region and
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

import { html, render, useState, useEffect } from "/assets/htm-preact.js";

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
    // the open run (per-tab subscription + one fetch)
    selected: null,
    detail: null,
    // per-tab, per-selection panels (HTTP; cancel- and cache-friendly)
    mode: "runs",
    repo: { loading: false, groups: [], query: "", active: 0, container: null, dir: "", label: null },
    files: { status: "idle", paths: [], path: null, view: { status: "idle", path: "", content: "", lang: "" } },
    diff: { status: "idle", files: [], idx: -1 },
    traces: { status: "idle", runs: [], spans: [], ended: false },
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
  store.set({ runs: msg.runs || [], status: msg.status || store.get().status, scanning: !!msg.scanning });
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
  store.set({ runs: runs });
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
function TreeDir({ name, node, leaf }) {
  const [open, setOpen] = useState(true);
  return html`<div class=${"tree-dir" + (open ? "" : " collapsed")}>
    <button
      type="button"
      class="tree-dir-head"
      aria-expanded=${String(open)}
      onClick=${() => setOpen(!open)}
    >
      <span class="tchev" aria-hidden="true">▾</span>${name}
    </button>
    <div class="tree-children"><${TreeLevel} node=${node} leaf=${leaf} /></div>
  </div>`;
}

function TreeLevel({ node, leaf }) {
  const dirs = Object.keys(node.dirs).sort();
  const files = node.files.slice().sort((a, b) => a.name.localeCompare(b.name));
  return html`
    ${dirs.map((d) => html`<${TreeDir} key=${"dir:" + d} name=${d} node=${node.dirs[d]} leaf=${leaf} />`)}
    ${files.map((f) => leaf(f))}
  `;
}

// --------------------------------------------------------------------------- //
// Runs: the fleet list and the status bar
// --------------------------------------------------------------------------- //
// `data-worker-id` / `data-state` / `data-live` are not decoration: the j/k row
// navigation reads the fleet back off the DOM through them, so they are part of
// this component's contract.
function RunRow({ run, selected }) {
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
        <span class="wid">#${run.short_id}</span>
        ${run.live_label ? html`<span class="pulse ${run.live}">${run.live_label}</span>` : null}
      </span>
      <span class="line2">
        <span class="doing">${run.doing}</span>
        ${run.mini ? html`<span class="mini">${run.mini}</span>` : null}
      </span>
      ${run.question ? html`<span class="q">${run.question}</span>` : null}
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
  return shown.map((run) => html`<${RunRow} key=${run.id} run=${run} selected=${run.id === selected} />`);
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
function RunHead({ head }) {
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
    <span class="meta">${meta}</span>
    ${head.exit_hint
      ? html`<span class=${"exit-hint " + (head.exit_ok ? "exit-ok" : "exit-err")}>${head.exit_hint}</span>`
      : null}
    ${head.activity ? html`<span class="doing-line">${head.activity}</span>` : null}
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

function LogTrail({ lines }) {
  if (!lines.length) {
    return html`<div class="log-trail">
      <div class="fd-empty">No log lines for this run (workhorse ships in-process script logs over OTLP).</div>
    </div>`;
  }
  return html`<div class="log-trail">
    ${lines.map(
      (line, i) => html`<div class=${"log-line" + (line.cls ? " " + line.cls : "")} key=${i}>
        <span class="lt-ts">${line.ts}</span>
        <span class="lt-lvl">${line.level}</span>
        <span class="lt-node">${line.node}</span>
        <span class="lt-body">${line.body}</span>
      </div>`
    )}
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
    <textarea name="answer" aria-label="Your answer" placeholder="Your answer…" rows="4"></textarea>
    <div class="answer-actions"><button type="submit" class="btn">Send answer</button></div>
  </form>`;
}

// The whole gate file, fetched only when the disclosure is opened. The question
// above it is the agent's excerpt (its "Questions" section, capped); the operator
// answering it usually needs the findings, the evidence and the earlier escalations
// that sit around it, and `gate.file_path` is relative to the run's workspace —
// the same base the `/file/` route reads from — so nobody has to go find the file.
function ContextDisclosure({ workflowId, filePath }) {
  const [loaded, setLoaded] = useState(null); // null = untouched, "" = empty file
  const [failed, setFailed] = useState(false);
  const onToggle = (e) => {
    if (!e.target.open || loaded !== null || failed) return;
    fetch("/file/" + encodeURIComponent(workflowId) + "?path=" + encodeURIComponent(filePath))
      .then((r) => r.json())
      .then((body) => setLoaded(body.content || ""))
      .catch(() => setFailed(true));
  };
  let body;
  if (failed) body = html`<div class="detail-empty">failed to load the context file</div>`;
  else if (loaded === null) body = html`<div class="detail-empty">Loading context…</div>`;
  else if (!loaded.trim()) body = html`<div class="detail-empty">(the file is empty or unreadable)</div>`;
  else body = html`<${Markdown} className="question context-file" source=${loaded} />`;
  return html`<details class="disclosure context" onToggle=${onToggle}>
    <summary>Full context — <code>${filePath}</code></summary>
    <div class="context-wrap">${body}</div>
  </details>`;
}

function GateBlock({ workflowId, gate }) {
  return html`<div class="gate-block">
    <div class="gate-path">${gate.file_path}</div>
    <${Markdown} className="question" source=${gate.question} />
    <${ContextDisclosure} workflowId=${workflowId} filePath=${gate.file_path} />
    <${AnswerForm} workflowId=${workflowId} filePath=${gate.file_path} />
  </div>`;
}

// The working-tree diff, fetched only when the disclosure is opened — it is the
// one part of the pane that costs a git invocation, and most visits never want it.
function DiffDisclosure({ containerId }) {
  const [loaded, setLoaded] = useState(null); // null = untouched, "" = no changes
  const [failed, setFailed] = useState(false);
  const onToggle = (e) => {
    if (!e.target.open || loaded !== null || failed) return;
    fetch("/diff/" + encodeURIComponent(containerId))
      .then((r) => r.json())
      .then((body) => setLoaded(body.diff || ""))
      .catch(() => setFailed(true));
  };
  let body;
  if (failed) body = html`<div class="detail-empty">failed to load diff</div>`;
  else if (loaded === null) body = html`<div class="detail-empty">Loading diff…</div>`;
  else if (!loaded.trim()) body = html`<div class="detail-empty">(no changes)</div>`;
  else body = html`<div dangerouslySetInnerHTML=${{ __html: diffMarkup(loaded, true) }}></div>`;
  return html`<details class="disclosure" onToggle=${onToggle}>
    <summary>Working-tree diff</summary>
    <div class="diff-wrap">${body}</div>
  </details>`;
}

function Detail() {
  const { selected, detail } = useStore();
  if (!selected) {
    return html`<div class="detail-empty">
      Select a run to see its activity, answer its gate, and read its metrics and logs.
    </div>`;
  }
  if (!detail) return html`<div class="detail-empty">Loading…</div>`;
  if (!detail.found) return html`<div class="detail-empty">Run not found.</div>`;
  return html`
    <${RunHead} head=${detail.head} />
    <div class="detail-body">
      ${detail.gates.length
        ? detail.gates.map((gate) => html`<${GateBlock} key=${gate.file_path} workflowId=${detail.id} gate=${gate} />`)
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
        <div class="live-sec-head">Logs</div>
        <${LogTrail} lines=${detail.logs} />
      </div>
      <${DiffDisclosure} key=${detail.id} containerId=${detail.id} />
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
  store.set({ selected: id, detail: null });
  sendWatch(id);
  try {
    const response = await fetch("/worker/" + encodeURIComponent(id));
    const body = await response.json();
    if (seq === detailSeq && store.get().detail === null) store.set({ detail: body });
  } catch (err) {
    // The watch subscription fills the pane in on the next tick.
  }
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
    if (sendCommand(payload)) form.querySelector("textarea").value = "";
    else pushToast("blocked", "✗ not sent", "No connection to groom — your answer is still in the box.", 7000);
  });
}

// --------------------------------------------------------------------------- //
// Shared container+repo selection (Files / Diff)
// --------------------------------------------------------------------------- //
const menuWrap = document.getElementById("repo-menu-wrap");
const menuBox = menuWrap.querySelector(".repo-menu-box");
const repoSearch = document.getElementById("repo-search");
let menuInvoker = null;

/** The picker's rows, flattened from the server's per-container groups and
 *  filtered by the search box — the list the keyboard actually moves through. */
function repoItems(repoState) {
  const q = repoState.query.trim().toLowerCase();
  const items = [];
  repoState.groups.forEach((group) => {
    group.repos.forEach((entry) => {
      if (q && entry.label.toLowerCase().indexOf(q) < 0) return;
      items.push({
        container: group.container,
        repo: entry.repo,
        label: entry.label,
        state: group.state,
        type: group.type,
        type_hue: group.type_hue,
      });
    });
  });
  return items;
}

function RepoMenu() {
  const { repo } = useStore();
  const items = repoItems(repo);
  const active = Math.max(0, Math.min(items.length - 1, repo.active));
  // The combobox lives in the static shell, outside this island, so the
  // active-option pointer is published to it here rather than by the keyboard
  // handler — this is the one place that knows which row ended up where.
  useEffect(() => {
    const current = items[active];
    if (!current) {
      repoSearch.removeAttribute("aria-activedescendant");
      return;
    }
    repoSearch.setAttribute("aria-activedescendant", "repo-opt-" + active);
    const el = document.getElementById("repo-opt-" + active);
    if (el) el.scrollIntoView({ block: "nearest" });
  });
  if (repo.loading) return html`<div class="repo-empty">Loading…</div>`;
  if (!items.length) return html`<div class="repo-empty">No repositories available.</div>`;
  return items.map(
    (item, i) => html`<div
      class=${"repo-item" + (i === active ? " active" : "")}
      id=${"repo-opt-" + i}
      key=${item.container + "/" + item.repo}
      role="option"
      aria-selected=${i === active ? "true" : "false"}
      data-container=${item.container}
      data-repo=${item.repo}
      data-label=${item.label}
      onClick=${() => {
        selectRepo(item);
        closeRepoMenu();
      }}
    >
      <${StateDot} state=${item.state} />
      <${TypeBadge} type=${item.type} hue=${item.type_hue} />
      <span class="repo-item-label">${item.label}</span>
    </div>`
  );
}

function openRepoMenu(btn) {
  const r = btn.getBoundingClientRect();
  menuInvoker = btn;
  menuBox.style.left = r.left + "px";
  menuBox.style.top = r.bottom + 4 + "px";
  menuBox.style.minWidth = Math.max(r.width, 240) + "px";
  menuWrap.classList.add("open");
  repoSearch.setAttribute("aria-expanded", "true");
  repoSearch.value = "";
  setIn("repo", { loading: true, groups: [], query: "", active: 0 });
  fetch("/repos")
    .then((r2) => r2.json())
    .then((groups) => setIn("repo", { loading: false, groups: groups || [], active: 0 }))
    .catch(() => setIn("repo", { loading: false, groups: [], active: 0 }));
  repoSearch.focus();
}

function closeRepoMenu() {
  if (!menuWrap.classList.contains("open")) return;
  menuWrap.classList.remove("open");
  repoSearch.setAttribute("aria-expanded", "false");
  repoSearch.removeAttribute("aria-activedescendant");
  // Escape/Enter close with focus still in the box: return it to the picker, never <body>
  if (menuInvoker && menuWrap.contains(document.activeElement)) menuInvoker.focus();
}

function moveRepoActive(delta) {
  const repo = store.get().repo;
  const items = repoItems(repo);
  if (!items.length) return;
  setIn("repo", { active: Math.max(0, Math.min(items.length - 1, repo.active + delta)) });
}

function selectRepo(item) {
  setIn("repo", { container: item.container, dir: item.repo || "", label: item.label });
  document.querySelectorAll(".repo-picker-label").forEach((el) => {
    el.textContent = item.label;
  });
  loadActivePane();
}

function loadActivePane() {
  const mode = store.get().mode;
  if (mode === "files") loadFiles();
  else if (mode === "diff") loadDiff();
}

// --------------------------------------------------------------------------- //
// Files panel — flat paths in, tree + highlighted viewer out
// --------------------------------------------------------------------------- //
function FilesTree() {
  const { repo, files } = useStore();
  if (!repo.container) return html`<div class="fd-empty">Pick a container / repo above.</div>`;
  if (files.status === "loading") return html`<div class="fd-empty">Loading files…</div>`;
  if (files.status === "error") return html`<div class="fd-empty">failed to load</div>`;
  if (!files.paths.length) return html`<div class="fd-empty">(no files)</div>`;
  const leaf = (node) => {
    const path = node.entry.path;
    const on = path === files.path;
    return html`<button
      type="button"
      key=${path}
      class=${"tree-file" + (on ? " active" : "")}
      aria-current=${on ? "true" : null}
      onClick=${() => openFile(path)}
    >
      <span class="fname">${node.name}</span>
    </button>`;
  };
  return html`<${TreeLevel} node=${buildTree(files.paths.map((p) => ({ path: p })))} leaf=${leaf} />`;
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

function FileView() {
  const { files } = useStore();
  const view = files.view;
  if (view.status === "idle") return html`<div class="fd-empty">Select a file to view it.</div>`;
  if (view.status === "loading") return html`<div class="fd-empty">Loading…</div>`;
  if (view.status === "error") return html`<div class="fd-empty">failed to load</div>`;
  if (!view.content) {
    return html`
      <div class="file-head">${view.path}</div>
      <div class="file-body"><div class="fd-empty">(empty or binary file)</div></div>
    `;
  }
  // The language comes from the server (projection.file_lang) so the extension
  // table is one table, next to the rest of the presentation policy.
  const markup = highlight(view.content, view.lang);
  const code =
    markup === null
      ? html`<code class=${view.lang ? "language-" + view.lang : null}>${view.content}</code>`
      : html`<code
          class=${view.lang ? "language-" + view.lang : null}
          dangerouslySetInnerHTML=${{ __html: markup }}
        ></code>`;
  return html`
    <div class="file-head">${view.path}</div>
    <div class="file-body"><pre class="file-pre hljs">${code}</pre></div>
  `;
}

function loadFiles() {
  const repo = store.get().repo;
  if (!repo.container) return;
  setIn("files", { status: "loading", paths: [], path: null, view: { status: "idle", path: "", content: "", lang: "" } });
  fetch("/files/" + encodeURIComponent(repo.container) + "?repo=" + encodeURIComponent(repo.dir))
    .then((r) => r.json())
    .then((body) => setIn("files", { status: "ready", paths: body.paths || [] }))
    .catch(() => setIn("files", { status: "error", paths: [] }));
}

function openFile(path) {
  const repo = store.get().repo;
  setIn("files", { path: path, view: { status: "loading", path: path, content: "", lang: "" } });
  fetch(
    "/file/" +
      encodeURIComponent(repo.container) +
      "?repo=" +
      encodeURIComponent(repo.dir) +
      "&path=" +
      encodeURIComponent(path)
  )
    .then((r) => r.json())
    .then((body) => {
      if (store.get().files.path !== path) return; // a later click won the race
      setIn("files", { view: { status: "ready", path: body.path || path, content: body.content || "", lang: body.lang || "" } });
    })
    .catch(() => {
      if (store.get().files.path !== path) return;
      setIn("files", { view: { status: "error", path: path, content: "", lang: "" } });
    });
}

// --------------------------------------------------------------------------- //
// Diff panel — raw unified diff in, changeset tree + rendered diff out
// --------------------------------------------------------------------------- //
// diff2html both parses the unified text and renders it, and it escapes what it
// emits — which is why the raw diff rides through the wire unsplit rather than
// having half a parser reimplemented server-side.
function diffMarkup(text, drawFileList) {
  if (!window.Diff2Html) return "";
  return Diff2Html.html(text, {
    drawFileList: !!drawFileList,
    matching: "lines",
    outputFormat: "line-by-line",
    colorScheme: "dark",
  });
}

function DiffTree() {
  const { repo, diff } = useStore();
  if (!repo.container) return html`<div class="fd-empty">Pick a container / repo above.</div>`;
  if (diff.status === "loading") return html`<div class="fd-empty">Loading changes…</div>`;
  if (diff.status === "error") return html`<div class="fd-empty">failed to load</div>`;
  if (!diff.files.length) return html`<div class="fd-empty">(no changes)</div>`;
  const entries = diff.files.map((file, i) => ({
    path: file.newName && file.newName !== "/dev/null" ? file.newName : file.oldName,
    idx: i,
    add: file.addedLines,
    del: file.deletedLines,
  }));
  const leaf = (node) => {
    const on = node.entry.idx === diff.idx;
    return html`<button
      type="button"
      key=${node.entry.idx}
      class=${"tree-file" + (on ? " active" : "")}
      aria-current=${on ? "true" : null}
      onClick=${() => setIn("diff", { idx: node.entry.idx })}
    >
      <span class="fname">${node.name}</span>
      <span class="fstat"><span class="add">+${node.entry.add}</span> <span class="del">-${node.entry.del}</span></span>
    </button>`;
  };
  return html`<${TreeLevel} node=${buildTree(entries)} leaf=${leaf} />`;
}

function DiffView() {
  const { diff } = useStore();
  const file = diff.files[diff.idx];
  if (!file) return html`<div class="fd-empty">Select a changed file to see its diff.</div>`;
  const markup = window.Diff2Html
    ? Diff2Html.html([file], { drawFileList: false, matching: "lines", outputFormat: "line-by-line", colorScheme: "dark" })
    : "";
  return html`<div dangerouslySetInnerHTML=${{ __html: markup }}></div>`;
}

function loadDiff() {
  const repo = store.get().repo;
  if (!repo.container) return;
  setIn("diff", { status: "loading", files: [], idx: -1 });
  fetch("/diff/" + encodeURIComponent(repo.container) + "?repo=" + encodeURIComponent(repo.dir))
    .then((r) => r.json())
    .then((body) => {
      const text = body.diff || "";
      const files = text.trim() && window.Diff2Html ? Diff2Html.parse(text) : [];
      setIn("diff", { status: "ready", files: files, idx: -1 });
    })
    .catch(() => setIn("diff", { status: "error", files: [], idx: -1 }));
}

// --------------------------------------------------------------------------- //
// Telemetry panel
// --------------------------------------------------------------------------- //
function RunCard({ card }) {
  return html`<div class="run-card">
    <span class="line1">
      <${StateDot} state=${card.live ? "running" : "finished"} />
      <span class="repo-branch">${card.workflow}</span>
      <span class="wid">${card.run_id}</span>
      ${card.alerts.map((rule) => html`<span class="alert-chip" key=${rule}>${rule}</span>`)}
      ${card.doing ? html`<span class="run-doing">${card.doing}</span>` : null}
    </span>
    <span class="run-meta">
      ${card.window} · ${card.spans} spans ${card.errors ? html`<span class="tr-err">${card.errors} err</span>` : null}
    </span>
  </div>`;
}

function Traces() {
  const { traces } = useStore();
  if (traces.status === "idle") return html`<div class="empty">No telemetry yet.</div>`;
  if (traces.status === "error") return html`<div class="empty">failed to load</div>`;
  const strip = traces.runs.length
    ? html`<div class="run-cards">${traces.runs.map((card) => html`<${RunCard} key=${card.run_id} card=${card} />`)}</div>`
    : null;
  if (!traces.spans.length) {
    return html`
      ${strip}
      <div class="empty">
        ${traces.ended || traces.runs.length
          ? html`No spans match — a run exports automatically once this collector is reachable, provided workhorse
              has the otel extra installed.`
          : html`No run is connected right now. Tick <em>show ended</em> to read the runs that already finished.`}
      </div>
    `;
  }
  return html`
    ${strip}
    <table class="traces">
      <thead>
        <tr>
          <th>started</th><th>run</th><th>node</th><th>span</th><th>duration</th><th>status</th>
        </tr>
      </thead>
      <tbody>
        ${traces.spans.map(
          (span, i) => html`<tr key=${i}>
            <td>${span.started}</td>
            <td class="tr-run">${span.run_id}</td>
            <td>${span.node}</td>
            <td>${span.name}</td>
            <td class="tr-dur">${span.duration}</td>
            <td class=${"tr-status" + (span.status === "ERROR" ? " tr-error" : "")}>${span.status}</td>
          </tr>`
        )}
      </tbody>
    </table>
  `;
}

// The `show_ended` checkbox rides along in the FormData when it is checked and
// is simply absent when it is not — which is exactly the shape /traces reads, so
// the default view is the connected runs and nothing here has to say so.
function loadTraces() {
  const form = document.getElementById("traces-filter");
  const params = new URLSearchParams(new FormData(form));
  const ended = form.elements.show_ended.checked;
  fetch("/traces?" + params.toString())
    .then((r) => r.json())
    .then((body) => setIn("traces", { status: "ready", runs: body.runs || [], spans: body.spans || [], ended: ended }))
    .catch(() => setIn("traces", { status: "error", runs: [], spans: [], ended: ended }));
}

// --------------------------------------------------------------------------- //
// Activity bar (mode switch)
// --------------------------------------------------------------------------- //
function setMode(mode) {
  document.querySelector(".app").dataset.mode = mode;
  document.querySelectorAll(".act-btn").forEach((b) => {
    const on = b.dataset.mode === mode;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  store.set({ mode: mode });
  closeRepoMenu();
  if (mode === "files") loadFiles();
  else if (mode === "diff") loadDiff();
  else if (mode === "telemetry") loadTraces();
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
    const text = [run.repo, "#" + run.short_id, run.doing].filter(Boolean).join(" ");
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

// A gate somebody answered. Every tab is told, and the confirmation is all this
// has to do: the pane itself is refreshed by the `detail` push the same command
// triggers, which now carries the gates — so no tab re-fetches, and a half-typed
// answer against a different run is never touched.
function onAnswered() {
  pushToast("ok", "✓ answer sent", "", 3500);
}

// --------------------------------------------------------------------------- //
// Wiring
// --------------------------------------------------------------------------- //
function wireEvents() {
  repoSearch.addEventListener("input", (e) => setIn("repo", { query: e.target.value, active: 0 }));
  repoSearch.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      moveRepoActive(e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const repo = store.get().repo;
      const items = repoItems(repo);
      const item = items[Math.max(0, Math.min(items.length - 1, repo.active))];
      if (item) {
        selectRepo(item);
        closeRepoMenu();
      }
    }
  });
  document.querySelectorAll(".repo-picker").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (menuWrap.classList.contains("open")) closeRepoMenu();
      else openRepoMenu(btn);
    });
  });
  document.addEventListener("click", (e) => {
    if (
      menuWrap.classList.contains("open") &&
      !e.target.closest("#repo-menu-wrap") &&
      !e.target.closest(".repo-picker")
    ) {
      closeRepoMenu();
    }
  });

  document.getElementById("activitybar").addEventListener("click", (e) => {
    const btn = e.target.closest(".act-btn");
    if (btn) setMode(btn.dataset.mode);
  });

  document.querySelector("#runs .filter").addEventListener("input", (e) => {
    store.set({ query: e.target.value });
  });

  document.getElementById("traces-filter").addEventListener("input", loadTraces);
  document.getElementById("traces-filter").addEventListener("change", loadTraces);
  document.getElementById("traces-filter").addEventListener("submit", (e) => {
    e.preventDefault();
    loadTraces();
  });

  // Worker selection + the status-bar/settings buttons, delegated: the rows are
  // re-rendered on every push, and a delegated handler outlives every one of them.
  document.body.addEventListener("click", (e) => {
    if (e.target.closest("form")) return; // don't hijack the answer form
    if (e.target.closest("#repo-menu-wrap, .repo-picker, .fd-tree")) return; // panel-local handlers own these
    const node = e.target.closest("[data-worker-id]");
    if (node) {
      select(node.dataset.workerId);
      return;
    }
    const refreshBtn = e.target.closest("#btn-refresh, #btn-refresh-bar");
    if (refreshBtn) {
      doRefresh(refreshBtn);
      return;
    }
    const palBtn = e.target.closest("#btn-palette");
    if (palBtn) {
      openPalette(palBtn);
      return;
    }
    if (e.target.id === "btn-notify" && "Notification" in window) Notification.requestPermission();
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
      closeRepoMenu();
      return;
    }
    // modal focus trap: the palette's only focusable element is its input
    if (pal.classList.contains("open") && e.key === "Tab") {
      e.preventDefault();
      palIn.focus();
      return;
    }
    if (pal.classList.contains("open") && e.key === "Enter") {
      const snap = store.get();
      const hits = paletteHits(snap.runs, snap.palette.query);
      const hit = hits[Math.max(0, Math.min(hits.length - 1, snap.palette.active))];
      if (hit) choosePaletteHit(hit.id);
      return;
    }
    const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
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
  ["repo-menu", RepoMenu],
  ["files-tree", FilesTree],
  ["file-view", FileView],
  ["diff-tree", DiffTree],
  ["diff-view", DiffView],
  ["traces-list", Traces],
  ["palette-results", PaletteResults],
];
ISLANDS.forEach(([id, Component]) => render(html`<${Component} />`, document.getElementById(id)));

wireEvents();
wireAnswerForm();
startConnection();
