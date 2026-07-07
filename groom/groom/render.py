"""HTML fragment rendering for groom's IDE-style console.

The dashboard is a CSS-grid shell (activity bar / picker / split inbox+detail /
status bar). The server owns four dynamic regions and streams them to browser
tabs over one websocket:

- ``#tree``       — the Repository -> worker picker tree
- ``#inbox-list`` — every worker, blocked pinned to the top
- ``#statusbar``  — fleet counts
- ``#detail``     — the selected worker's gate(s): question + answer + diff,
                    fetched on demand via ``GET /worker/{id}`` (not broadcast,
                    so a half-typed answer is never clobbered by a live push)

``#tree``/``#inbox-list``/``#statusbar`` are re-rendered whole and pushed as one
``hx-swap-oob`` frame on every state change (the fleet is small); their ids ship
in the static shell so the first out-of-band swap has a matching target.

Every dynamic value is passed through :func:`esc` — gate questions and answers
come from LLM-authored context files and are untrusted as far as the browser is
concerned. Gate questions are emitted as an escaped text node in a ``[data-md]``
div and rendered client-side through marked -> DOMPurify, never as raw markup.
"""

from __future__ import annotations

import html as _html
import json

from .models import WorkflowContainer, WorkflowState

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


def _group_by_repo(workflows: list[WorkflowContainer]) -> list[tuple[str, list[WorkflowContainer]]]:
    groups: dict[str, list[WorkflowContainer]] = {}
    for wf in workflows:
        groups.setdefault(_repo_label(wf), []).append(wf)
    # Repos with a blocked worker float up; then alphabetical.
    def _key(item: tuple[str, list[WorkflowContainer]]) -> tuple[int, str]:
        _, members = item
        has_blocked = any(m.state == WorkflowState.BLOCKED for m in members)
        return (0 if has_blocked else 1, item[0].lower())

    return sorted(groups.items(), key=_key)


# --------------------------------------------------------------------------- #
# Picker tree
# --------------------------------------------------------------------------- #
def _tree_worker(wf: WorkflowContainer) -> str:
    return (
        f'<div class="worker" data-worker-id="{esc(wf.container_id)}" data-state="{esc(wf.state.value)}">'
        f"{_state_dot(wf.state)}{_type_badge(wf.workflow_type)}"
        f'<span class="wid">#{esc(_short_id(wf))}</span>'
        f'<span class="node">{esc(wf.current_node)}</span>'
        f"</div>"
    )


def _tree_group(label: str, members: list[WorkflowContainer]) -> str:
    types: dict[str, int] = {}
    blocked = 0
    for m in members:
        if m.workflow_type:
            types[m.workflow_type] = types.get(m.workflow_type, 0) + 1
        if m.state == WorkflowState.BLOCKED:
            blocked += 1
    summary = " ".join(f"{t}×{n}" for t, n in sorted(types.items()))
    pill = f'<span class="bpill">{blocked}</span>' if blocked else ""
    workers = "".join(
        _tree_worker(m) for m in sorted(members, key=lambda w: (STATE_ORDER[w.state], w.name))
    )
    return (
        f'<div class="repo" data-repo="{esc(label)}">'
        f'<span class="chev">▾</span><span class="name">{esc(label)}</span>'
        f'<span class="sum">{esc(summary)}</span>{pill}</div>{workers}'
    )


def render_tree(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = False) -> str:
    matching = [wf for wf in workflows if _matches(wf, query)]
    if not matching:
        inner = '<div class="empty">No workers.</div>'
    else:
        inner = "".join(_tree_group(label, members) for label, members in _group_by_repo(matching))
    return f'<div class="tree" id="tree"{_oob(oob)}>{inner}</div>'


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
        f'<div class="q">{esc(_question_preview(gate.question))}</div>'
        if wf.state == WorkflowState.BLOCKED and gate
        else ""
    )
    blocked_cls = " blocked" if wf.state == WorkflowState.BLOCKED else ""
    return (
        f'<div class="row{blocked_cls}" data-worker-id="{esc(wf.container_id)}" data-state="{esc(wf.state.value)}">'
        f'<div class="line1">{_state_dot(wf.state)}{_type_badge(wf.workflow_type)}'
        f'<span class="repo-branch">{esc(_repo_label(wf))}</span>'
        f'<span class="wid">#{esc(_short_id(wf))}</span>'
        f'<span class="gate">{tail}</span></div>{preview}</div>'
    )


def render_inbox(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = False) -> str:
    matching = [wf for wf in workflows if _matches(wf, query)]
    matching.sort(key=lambda wf: (STATE_ORDER[wf.state], wf.name))
    if not matching:
        inner = '<div class="empty">No workflow containers found.</div>'
    else:
        inner = "".join(_inbox_row(wf) for wf in matching)
    return f'<div class="inbox-list" id="inbox-list"{_oob(oob)}>{inner}</div>'


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
        + '<button id="btn-refresh-bar" class="statusbar-refresh" title="Rescan containers (reconcile + prune)">⟳</button>'
        + '<span><span class="kbd">⌘K</span> palette</span>'
        + "</span>"
    )
    return f'<div id="statusbar"{_oob(oob)}>{body}</div>'


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
        f'<textarea name="answer" placeholder="Your answer…" rows="4"></textarea>'
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
# Combined broadcast payload
# --------------------------------------------------------------------------- #
def render_shell_data(workflows: list[WorkflowContainer], query: str = "", *, oob: bool = True) -> str:
    """The live regions, concatenated as one out-of-band frame for the initial
    snapshot and every subsequent broadcast.
    """
    return (
        render_tree(workflows, query, oob=oob)
        + render_inbox(workflows, query, oob=oob)
        + render_statusbar(workflows, oob=oob)
    )


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
