"""Tests for groom.render: the IDE console fragments and the load-bearing
contracts the browser-side glue (dashboard.html) depends on — stable OOB ids,
the markdown escaping hook, the diff hooks, and the ws-send answer form.

Run: uv run pytest tests/test_render.py
"""
from __future__ import annotations

from groom import render
from groom.models import GateInfo, WorkflowContainer, WorkflowState


def _wf(container_id="abc123", **kwargs) -> WorkflowContainer:
    return WorkflowContainer(container_id=container_id, name=kwargs.pop("name", "demo"), **kwargs)


def _blocked(container_id="abc123", file_path="docs/a.md", question="Which one?", **kwargs) -> WorkflowContainer:
    wf = _wf(container_id, state=WorkflowState.BLOCKED, **kwargs)
    wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=question)
    return wf


# ---- OOB regions carry stable ids (hx-swap-oob no-ops without a match) ----
def test_dynamic_regions_have_stable_ids_and_oob_flag():
    wfs = [_wf(state=WorkflowState.RUNNING)]
    assert 'id="tree"' in render.render_tree(wfs)
    assert 'id="inbox-list"' in render.render_inbox(wfs)
    assert 'id="statusbar"' in render.render_statusbar(wfs)
    assert 'hx-swap-oob="true"' in render.render_tree(wfs, oob=True)
    assert 'hx-swap-oob="true"' in render.render_inbox(wfs, oob=True)
    assert 'hx-swap-oob="true"' in render.render_statusbar(wfs, oob=True)
    shell = render.render_shell_data(wfs)
    assert 'id="tree"' in shell and 'id="inbox-list"' in shell and 'id="statusbar"' in shell


# ---- status bar counts the fleet by state ----
def test_statusbar_counts_states():
    wfs = [
        _blocked("a"),
        _wf("b", state=WorkflowState.RUNNING),
        _wf("c", state=WorkflowState.RUNNING),
        _wf("d", state=WorkflowState.IDLE),
    ]
    html = render.render_statusbar(wfs)
    assert '<span class="n">1</span> blocked' in html
    assert '<span class="n">2</span> running' in html
    assert '<span class="n">1</span> idle' in html
    assert "1 repos · 4 workers" in html


# ---- the markdown security contract: never raw markup ----
def test_gate_question_rendered_as_escaped_data_md_text_node():
    wf = _blocked(question="Use <script>alert(1)</script>?")
    html = render.render_worker_detail(wf)
    assert "data-md" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---- ws-send answer form contract (the /ws handler depends on these names) ----
def test_worker_detail_has_ws_send_answer_form():
    html = render.render_worker_detail(_blocked(file_path="docs/gate.md"))
    assert "ws-send" in html
    assert 'name="cmd" value="answer"' in html
    assert 'name="workflow_id" value="abc123"' in html
    assert 'name="file_path" value="docs/gate.md"' in html
    assert 'name="answer"' in html


# ---- diff hook: exactly one per worker, carrying the container id ----
def test_worker_detail_has_one_diff_disclosure():
    wf = _blocked()
    wf.gates["docs/b.md"] = GateInfo(workflow_id="abc123", file_path="docs/b.md", question="Q2?")
    html = render.render_worker_detail(wf)
    assert html.count('data-diff="abc123"') == 1
    assert 'data-container="abc123"' in html
    # Two gate blocks (question + answer) but one shared working-tree diff.
    assert html.count("gate-block") == 2


def test_worker_detail_not_found_and_no_gate_states():
    assert "Worker not found." in render.render_worker_detail(None)
    running = _wf(state=WorkflowState.RUNNING, current_node="write_epic")
    assert "No open gate" in render.render_worker_detail(running)


# ---- type badge + repo grouping in the picker ----
def test_tree_groups_workers_by_repo_and_badges_type():
    wfs = [
        _wf("a", repo_name="predykt", repo_branch="main", workflow_type="coder", state=WorkflowState.RUNNING),
        _wf("b", repo_name="predykt", repo_branch="main", workflow_type="author", state=WorkflowState.IDLE),
        _wf("c", repo_name="yenta", repo_branch="dev", workflow_type="coder", state=WorkflowState.RUNNING),
    ]
    html = render.render_tree(wfs)
    assert html.count('class="repo"') == 2          # two repo groups
    assert 'data-type="coder"' in html
    assert 'data-type="author"' in html
    assert "predykt@main" in html


def test_blocked_worker_sorts_first_in_inbox_and_shows_preview():
    wfs = [
        _wf("run", state=WorkflowState.RUNNING),
        _blocked("blk", question="CI is red — pick an option"),
    ]
    html = render.render_inbox(wfs)
    assert html.index('data-worker-id="blk"') < html.index('data-worker-id="run"')
    assert "CI is red — pick an option" in html


def test_empty_inbox_message():
    assert "No workflow containers found." in render.render_inbox([])


# ---- answered gate: server dispatches a groom:answered event ----
def test_render_answered_script_carries_worker_and_file():
    html = render.render_answered_script("abc123", "docs/gate.md")
    assert "groom:answered" in html
    assert '"id": "abc123"' in html
    assert '"file_path": "docs/gate.md"' in html


# ---- status bar carries an always-visible refresh control ----
def test_statusbar_has_refresh_button():
    html = render.render_statusbar([_wf(state=WorkflowState.RUNNING)])
    assert 'id="btn-refresh-bar"' in html


# ---- finished worker shows its exit code (and only when finished + known) ----
def test_exit_code_hint_only_on_finished_with_code():
    finished_ok = _wf("a", state=WorkflowState.FINISHED, exit_code=0)
    finished_err = _wf("b", state=WorkflowState.FINISHED, exit_code=1)
    running = _wf("c", state=WorkflowState.RUNNING, exit_code=0)  # code set but still live
    assert "exited 0" in render.render_inbox([finished_ok])
    assert "exit-ok" in render.render_worker_detail(finished_ok)
    assert "exit-err" in render.render_inbox([finished_err])
    assert "exited" not in render.render_inbox([running])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
