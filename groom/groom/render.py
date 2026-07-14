"""HTML fragment rendering for groom's IDE-style console.

The dashboard is a CSS-grid shell (activity bar / three-mode main / status bar)
with three panels — Inbox, Files, Diff — switched from the activity bar. The
server owns these dynamic regions and streams the live ones to browser tabs over
one websocket:

- ``#inbox-list`` — every worker with an open gate (the operator's message list)
- ``#statusbar``  — fleet counts
- ``#detail``     — the selected worker's gate(s): question + answer + diff,
                    fetched on demand via ``GET /worker/{id}`` (not broadcast,
                    so a half-typed answer is never clobbered by a live push)
- ``#repo-menu``  — the container+repo picker for the Files/Diff panels, fetched
                    on demand via ``GET /repos`` (see :func:`render_repo_menu`)

``#inbox-list``/``#statusbar`` are re-rendered whole and pushed as one
``hx-swap-oob`` frame on every state change (the fleet is small); their ids ship
in the static shell so the first out-of-band swap has a matching target. The
Files/Diff panels are container+repo scoped and fetched on demand, not broadcast.

Every dynamic value is passed through :func:`esc` — gate questions and answers
come from LLM-authored context files and are untrusted as far as the browser is
concerned. Gate questions are emitted as an escaped text node in a ``[data-md]``
div and rendered client-side through marked -> DOMPurify, never as raw markup.
"""

from __future__ import annotations

import html as _html
import json
from datetime import datetime
from typing import Any

from . import state
from .models import RunTelemetry, WorkflowContainer, WorkflowState

# Blocked first, then active, then quiet — used for both tree and inbox order.
STATE_ORDER = {
    WorkflowState.BLOCKED: 0,
    WorkflowState.RUNNING: 1,
    WorkflowState.IDLE: 2,
    WorkflowState.FINISHED: 3,
}


def esc(value: str | None) -> str:
    return _html.escape(value or "", quote=True)


def _oob(oob: bool) -> str:
    return ' hx-swap-oob="true"' if oob else ""


def render_loading(message: str = "Discovering containers…") -> str:
    """The placeholder shown in an empty live region while discovery is still
    running, so a not-yet-scanned fleet reads as *loading* rather than
    *finished-and-empty*. Reuses the ``spin`` keyframes from dashboard.css.
    """
    return f'<div class="empty loading"><span class="spin"></span>{esc(message)}</div>'


def _empty_or_loading(text: str, query: str) -> str:
    """Loading spinner while a discovery pass is in flight (and the operator
    isn't mid-search), else the region's normal empty message. A query means the
    operator is filtering an already-loaded fleet, so show the empty result.
    """
    if state.SCANNING and not query:
        return render_loading()
    return f'<div class="empty">{text}</div>'


def _matches(wf: WorkflowContainer, query: str) -> bool:
    if not query:
        return True
    query = query.lower()
    haystacks = [wf.name, wf.repo_name, wf.repo_branch, wf.workflow_type, wf.current_node]
    haystacks += [g.file_path for g in wf.gates.values()]
    return any(query in (h or "").lower() for h in haystacks)


def _repo_label(wf: WorkflowContainer) -> str:
    return f"{wf.repo_name}@{wf.repo_branch}" if wf.repo_branch else (wf.repo_name or "—")


def _short_id(wf: WorkflowContainer) -> str:
    return wf.container_id[:4] or "----"


def _state_dot(state: WorkflowState) -> str:
    return f'<span class="dot {esc(state.value)}"></span>'


def _type_badge(workflow_type: str) -> str:
    """A stable, self-coloring type chip. The hue is derived from the type
    string so a new workflow kind gets a consistent color with no CSS change;
    ``coder``/``author`` also get a fixed look from ``dashboard.css``.
    """
    if not workflow_type:
        return ""
    hue = 0
    for ch in workflow_type:
        hue = (hue * 31 + ord(ch)) % 360
    return (
        f'<span class="badge" data-type="{esc(workflow_type)}" '
        f'style="--type-hue:{hue}">{esc(workflow_type)}</span>'
    )


def _question_preview(question: str) -> str:
    for raw_line in question.splitlines():
        line = raw_line.strip().lstrip("#>*-` ").strip()
        if line:
            return line[:140]
    return ""


# --------------------------------------------------------------------------- #
# Container + repo picker (Files / Diff panels; fetched via GET /repos)
# --------------------------------------------------------------------------- #
def render_repo_menu(entries: list[tuple[WorkflowContainer, list[str]]]) -> str:
    """The Zed-style container+repo menu: one clickable ``<name>/<repo>`` row per
    (container, checkout). ``entries`` is ``[(wf, [repo_dir, ...]), ...]``; a
    workflow with no discoverable repo still gets a single volume-root entry so
    it can be browsed. dashboard.html injects this into ``#repo-menu`` and does
    the search-filtering client-side, so no query handling is needed here.
    """
    rows = []
    for wf, repo_dirs in sorted(entries, key=lambda e: (STATE_ORDER[e[0].state], e[0].name)):
        for repo in repo_dirs or [""]:
            label = f"{wf.name}/{repo}" if repo else wf.name
            rows.append(
                f'<div class="repo-item" role="option" '
                f'data-container="{esc(wf.container_id)}" data-repo="{esc(repo)}" '
                f'data-label="{esc(label)}">'
                f"{_state_dot(wf.state)}{_type_badge(wf.workflow_type)}"
                f'<span class="repo-item-label">{esc(label)}</span></div>'
            )
    if not rows:
        return '<div class="repo-empty">No repositories available.</div>'
    return "".join(rows)


# --------------------------------------------------------------------------- #
# Inbox
# --------------------------------------------------------------------------- #
def _exit_hint(wf: WorkflowContainer) -> str:
    """A short 'exited N' marker for a finished worker whose exit code is known
    (ok when 0, error otherwise). Empty for still-live or code-less workers.
    """
    if wf.state != WorkflowState.FINISHED or wf.exit_code is None:
        return ""
    cls = "exit-ok" if wf.exit_code == 0 else "exit-err"
    return f'<span class="exit-hint {cls}">exited {esc(str(wf.exit_code))}</span>'


def _inbox_row(wf: WorkflowContainer) -> str:
    gate = next(iter(sorted(wf.gates.values(), key=lambda g: g.file_path)), None)
    tail = esc(gate.file_path) if gate else (_exit_hint(wf) or esc(wf.current_node))
    preview = (
        f'<span class="q">{esc(_question_preview(gate.question))}</span>'
        if wf.state == WorkflowState.BLOCKED and gate
        else ""
    )
    blocked_cls = " blocked" if wf.state == WorkflowState.BLOCKED else ""
    # A real <button> (focusable, Enter/Space) per the a11y contract; children are
    # spans because button content is phrasing content.
    return (
        f'<button type="button" class="row{blocked_cls}" '
        f'data-worker-id="{esc(wf.container_id)}" data-state="{esc(wf.state.value)}">'
        f'<span class="line1">{_state_dot(wf.state)}{_type_badge(wf.workflow_type)}'
        f'<span class="repo-branch">{esc(_repo_label(wf))}</span>'
        f'<span class="wid">#{esc(_short_id(wf))}</span>'
        f'<span class="gate">{tail}</span></span>{preview}</button>'
    )


def render_inbox(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = False) -> str:
    # The inbox is the operator's *message* list — only workers with an open
    # gate (an incoming "I need you" from a container) belong here. The full
    # fleet lives in the tree; a plain RUNNING/FINISHED worker is not a message.
    matching = [wf for wf in workflows if wf.gates and _matches(wf, query)]
    matching.sort(key=lambda wf: (STATE_ORDER[wf.state], wf.name))
    if not matching:
        inner = _empty_or_loading("No incoming messages — inbox zero.", query)
    else:
        inner = "".join(_inbox_row(wf) for wf in matching)
    # OOB swaps replace this element outright, so the live-region attributes must
    # ride along or the pushed update loses its announcement (linter A11Y007).
    return (
        f'<div class="inbox-list" id="inbox-list" role="log" aria-live="polite" '
        f'aria-label="Blocked workers inbox"{_oob(oob)}>{inner}</div>'
    )


# --------------------------------------------------------------------------- #
# Status bar
# --------------------------------------------------------------------------- #
def render_statusbar(workflows: list[WorkflowContainer], *, oob: bool = False) -> str:
    counts = {state: 0 for state in WorkflowState}
    repos: set[str] = set()
    for wf in workflows:
        counts[wf.state] += 1
        repos.add(_repo_label(wf))

    def seg(state: WorkflowState) -> str:
        return (
            f'<span class="stat">{_state_dot(state)}'
            f'<span class="n">{counts[state]}</span> {state.value}</span>'
        )

    body = (
        seg(WorkflowState.BLOCKED)
        + seg(WorkflowState.RUNNING)
        + seg(WorkflowState.IDLE)
        + seg(WorkflowState.FINISHED)
        + '<span class="status-right">'
        + f"<span>{len(repos)} repos · {len(workflows)} workers</span>"
        + '<span class="stat"><span class="ws-dot"></span> live</span>'
        + '<button type="button" id="btn-refresh-bar" class="statusbar-refresh" '
        + 'aria-label="Rescan containers" title="Rescan containers (reconcile + prune)">'
        + '<span aria-hidden="true">⟳</span></button>'
        + '<button type="button" id="btn-palette" class="palette-open" aria-label="Open command palette">'
        + '<span class="kbd" aria-hidden="true">⌘K</span> palette</button>'
        + "</span>"
    )
    return (
        f'<div id="statusbar" role="status" aria-live="polite"{_oob(oob)}>{body}</div>'
    )


# --------------------------------------------------------------------------- #
# Detail pane (per selected worker; fetched via GET /worker/{id})
# --------------------------------------------------------------------------- #
def _answer_form(wf: WorkflowContainer, file_path: str) -> str:
    """The unchanged ws-send answer contract: a form serialized to JSON over
    the websocket carrying ``cmd=answer`` + the (workflow_id, file_path) that
    scope the write, so multiple simultaneously-live gates stay unambiguous.
    """
    return (
        f'<form class="answer" ws-send>'
        f'<input type="hidden" name="cmd" value="answer">'
        f'<input type="hidden" name="workflow_id" value="{esc(wf.container_id)}">'
        f'<input type="hidden" name="file_path" value="{esc(file_path)}">'
        f'<textarea name="answer" aria-label="Your answer" placeholder="Your answer…" rows="4"></textarea>'
        f'<div class="answer-actions"><button type="submit" class="btn">Send answer</button></div>'
        f"</form>"
    )


def _diff_disclosure(wf: WorkflowContainer) -> str:
    cid = esc(wf.container_id)
    return (
        f'<details class="disclosure" data-diff="{cid}">'
        f"<summary>Working-tree diff</summary>"
        f'<div class="diff-wrap" data-diff-target data-container="{cid}"></div>'
        f"</details>"
    )


def _detail_head(wf: WorkflowContainer) -> str:
    return (
        f'<div class="detail-head">{_state_dot(wf.state)}{_type_badge(wf.workflow_type)}'
        f'<span class="repo-branch">{esc(_repo_label(wf))}</span>'
        f'<span class="meta">#{esc(wf.container_id[:6])} · {esc(wf.state.value)}'
        f'{(" · node " + esc(wf.current_node)) if wf.current_node else ""}</span>'
        f'{_exit_hint(wf)}</div>'
    )


def render_worker_detail(wf: WorkflowContainer | None) -> str:
    if wf is None:
        return '<div id="detail"><div class="detail-empty">Worker not found.</div></div>'

    gates = sorted(wf.gates.values(), key=lambda g: g.file_path)
    if not gates:
        node = f" at node <code>{esc(wf.current_node)}</code>" if wf.current_node else ""
        body = f'<div class="detail-empty">No open gate — this worker is <b>{esc(wf.state.value)}</b>{node}.</div>'
        return f'<div id="detail">{_detail_head(wf)}{body}</div>'

    blocks = []
    for gate in gates:
        # Raw markdown as an escaped text node; dashboard.html reads it back via
        # textContent and renders through marked+DOMPurify. Never innerHTML raw.
        question = f'<div class="question" data-md>{esc(gate.question)}</div>'
        blocks.append(
            f'<div class="gate-block">'
            f'<div class="gate-path">{esc(gate.file_path)}</div>'
            f"{question}{_answer_form(wf, gate.file_path)}</div>"
        )
    body = f'<div class="detail-body">{"".join(blocks)}{_diff_disclosure(wf)}</div>'
    return f'<div id="detail">{_detail_head(wf)}{body}</div>'


# --------------------------------------------------------------------------- #
# Telemetry pane (SQLite-backed trace search; fetched via GET /traces)
# --------------------------------------------------------------------------- #
def _fmt_ts(ts: float) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def _fmt_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{seconds / 3600:.1f}h"


def _run_card(summary: dict[str, Any], telemetry: RunTelemetry | None) -> str:
    live = not summary.get("finished")
    dot = _state_dot(WorkflowState.RUNNING if live else WorkflowState.FINISHED)
    errors = int(summary.get("error_count") or 0)
    err = f'<span class="tr-err">{errors} err</span>' if errors else ""
    chips = "".join(
        f'<span class="alert-chip">{esc(rule)}</span>'
        for rule in sorted(telemetry.fired if telemetry else ())
    )
    window = f"{_fmt_ts(summary.get('first_ts') or 0)} → {_fmt_ts(summary.get('last_ts') or 0)}"
    return (
        f'<div class="run-card">'
        f'<span class="line1">{dot}'
        f'<span class="repo-branch">{esc(summary.get("workflow") or "run")}</span>'
        f'<span class="wid">{esc(summary["run_id"])}</span>{chips}</span>'
        f'<span class="run-meta">{esc(window)} · {summary.get("span_count", 0)} spans {err}</span>'
        f"</div>"
    )


def _span_row(span: dict[str, Any]) -> str:
    status = str(span.get("status") or "UNSET")
    status_cell = (
        f'<td class="tr-status tr-error">{esc(status)}</td>'
        if status == "ERROR"
        else f'<td class="tr-status">{esc(status)}</td>'
    )
    duration = _fmt_duration((span.get("end_ts") or 0) - (span.get("start_ts") or 0))
    return (
        "<tr>"
        f"<td>{esc(_fmt_ts(span.get('start_ts') or 0))}</td>"
        f'<td class="tr-run">{esc(span.get("run_id") or "")}</td>'
        f"<td>{esc(span.get('node') or '')}</td>"
        f"<td>{esc(span.get('name') or '')}</td>"
        f'<td class="tr-dur">{esc(duration)}</td>'
        f"{status_cell}"
        "</tr>"
    )


def render_traces(
    summaries: list[dict[str, Any]],
    spans: list[dict[str, Any]],
    runs: dict[str, RunTelemetry],
) -> str:
    """The telemetry pane's content: a per-run summary strip (with any fired
    alert rules as chips) above the filtered span table. Fetched on demand into
    ``#traces-list`` — not broadcast; telemetry is a pull view, the pushes are
    the alerts."""
    cards = "".join(_run_card(s, runs.get(s["run_id"])) for s in summaries)
    strip = f'<div class="run-cards">{cards}</div>' if cards else ""
    if not spans:
        return strip + '<div class="empty">No spans match — telemetry appears once a run exports with WORKHORSE_OTEL=1.</div>'
    rows = "".join(_span_row(s) for s in spans)
    table = (
        '<table class="traces"><thead><tr>'
        "<th>started</th><th>run</th><th>node</th><th>span</th><th>duration</th><th>status</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return strip + table


# --------------------------------------------------------------------------- #
# Combined broadcast payload
# --------------------------------------------------------------------------- #
def render_shell_data(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = True) -> str:
    """The live regions, concatenated as one out-of-band frame for the initial
    snapshot and every subsequent broadcast. The Files/Diff panels are
    container+repo scoped and fetched on demand, so they are not part of this.
    """
    return render_inbox(workflows, query, oob=oob) + render_statusbar(workflows, oob=oob)


def render_notify_script(message: str) -> str:
    """A same-swap-batch <script> that dispatches the client-side
    ``groom:blocked`` event (htmx executes inline scripts in swapped content).
    Kept out of the broadcast payload so it only accompanies an actual new
    block, not every reconciliation re-render.
    """
    return (
        "<script>document.body.dispatchEvent(new CustomEvent('groom:blocked',"
        f"{{detail:{json.dumps(message)}}}));</script>"
    )


def render_answered_script(container_id: str, file_path: str) -> str:
    """A same-swap-batch <script> dispatching ``groom:answered`` after a gate
    write succeeds (parallels :func:`render_notify_script`). The client shows a
    success toast and, if that worker's detail pane is open, re-fetches it so
    the answered question is dismissed. Appended only on success, so it never
    fires on a rejected/duplicate answer.
    """
    detail = json.dumps({"id": container_id, "file_path": file_path})
    return (
        "<script>document.body.dispatchEvent(new CustomEvent('groom:answered',"
        f"{{detail:{detail}}}));</script>"
    )
