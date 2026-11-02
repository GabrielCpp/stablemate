"""The Diff tab of a container run, measured on the page the operator gets, against a real sidecar socket."""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

CONTAINER = "diffbox12345"
OTHER = "idlebox12345"
RUN = "diff-run"


def _patch(path: str, removed: list[str], added: list[str], name: str | None = None) -> str:
    head = f"diff --git a/{path} b/{path}\nindex 1111111..2222222 100644\n--- a/{path}\n+++ b/{path}\n"
    body = f"@@ -1,{len(removed) + 1} +1,{len(added) + 1} @@\n context\n"
    body += "".join(f"-{line}\n" for line in removed) + "".join(f"+{line}\n" for line in added)
    return head + body


def _deleted(path: str, lines: list[str]) -> str:
    head = f"diff --git a/{path} b/{path}\ndeleted file mode 100644\nindex 1111111..0000000\n--- a/{path}\n+++ /dev/null\n"
    return head + f"@@ -1,{len(lines)} +0,0 @@\n" + "".join(f"-{line}\n" for line in lines)


SIGN_IN = _patch("services/api/sign_in.py", ["old a"], ["new a", "new b", "new c"])
LOCKOUT = _patch("services/api/lockout.py", [], ["lock one", "lock two"])
README = _deleted("docs/README.md", ["bye"])
DIFF = SIGN_IN + LOCKOUT + README
SIZE = "+5 −2"


def _read(diff: str = DIFF, untracked: tuple[str, ...] = (), failed: bool = False) -> dict:
    return {"diff": diff, "untracked": list(untracked), "failed": failed}


class _Sidecar:
    """A sidecar speaking the real protocol over a real socket, answering getDiff from a script and counting the reads."""

    def __init__(self, live, container: str, reply: dict | None = None) -> None:
        self.container = container
        self.reply = reply if reply is not None else _read()
        self.fail = False
        self.hold = threading.Event()
        self.hold.set()
        self.reads = 0
        self.socket = connect(f"ws://127.0.0.1:{live.port}/sidecar")
        hello = {
            "type": "hello",
            "identity": {"container_id": container, "name": "coder-acme", "run_id": RUN, "workflow": "coder"},
            "snapshot": {"current_node": "build", "terminal": "", "gates": []},
        }
        self.socket.send(json.dumps(hello))
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        try:
            for raw in self.socket:
                message = json.loads(raw)
                if message.get("type") != "rpc":
                    continue
                if message["method"] == "getDiff":
                    self.reads += 1
                    self.hold.wait(10)
                    if self.fail:
                        reply = {"type": "rpc_result", "id": message["id"], "ok": False, "error": "git blew up"}
                    else:
                        reply = {"type": "rpc_result", "id": message["id"], "ok": True, "data": self.reply}
                else:
                    reply = {"type": "rpc_result", "id": message["id"], "ok": True, "data": {}}
                self.socket.send(json.dumps(reply))
        except ConnectionClosed:
            pass

    def drop(self) -> None:
        self.socket.close()
        self.thread.join(timeout=5)


def _wait_for(check, what: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


@contextmanager
def _container_run(container: str = CONTAINER, *, native: bool = False, run_id: str = RUN) -> Iterator[None]:
    from groom import app as app_module
    from groom import sidecar_hub, state
    from groom.models import WorkflowState

    async def _no_volumes(_container_id: str) -> None:
        return None

    with patch.object(app_module, "_ensure_volumes", _no_volumes):
        state.upsert_workflow(
            container, name="coder-acme", workflow_type="coder", repo_name="acme", repo_branch="main",
            current_node="build", activity="building", run_id=run_id, state=WorkflowState.RUNNING,
            native=native, workspace_volume="/nonexistent/acme",
        )
        try:
            yield
        finally:
            conn = sidecar_hub.get(container)
            if conn is not None:
                sidecar_hub.unregister(conn)
            state.WORKFLOWS.pop(container, None)


def _connect(live, container: str = CONTAINER, reply: dict | None = None) -> _Sidecar:
    from groom import sidecar_hub

    sidecar = _Sidecar(live, container, reply)
    _wait_for(lambda: sidecar_hub.get(container) is not None, "the sidecar to register")
    return sidecar


def _requests(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if "/diff/" in request.url else None)
    return seen


def _pick(page, container: str = CONTAINER) -> None:
    page.locator(f'#runs-list .row[data-worker-id="{container}"]').click()
    page.wait_for_selector("#detail .dtabs", timeout=10000)


def _tab(page, name: str):
    return page.get_by_role("tab", name=re.compile(rf"^{name}\b"))


def _settle(page, ms: int = 600) -> None:
    page.wait_for_timeout(ms)


def _push_exited(live, container: str) -> None:
    request = urllib.request.Request(
        live.url() + "push/exited",
        data=json.dumps({"container_id": container, "exit_code": 0}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as reply:
        assert reply.status in (200, 201)


def _open_diff(page) -> None:
    _tab(page, "Diff").click()
    page.wait_for_selector("#detail-panel .fd-split, #detail-panel .detail-empty, #detail-panel .side-state", timeout=10000)


def test_a_container_run_with_a_connected_sidecar_has_a_diff_tab_beside_overview_and_details():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            tabs = page.get_by_role("tablist", name="Run detail").get_by_role("tab")
            expect(tabs).to_have_text([re.compile("^Overview$"), re.compile("^Details$"), re.compile("^Files$"), re.compile(r"^Diff")])
        finally:
            page.close()
            sidecar.drop()


def test_the_diff_tab_shows_the_size_of_the_change_before_it_is_opened_after_exactly_one_read():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        seen = _requests(page)
        try:
            _pick(page)
            tab = _tab(page, "Diff")
            expect(tab).to_contain_text(SIZE)
            expect(tab).to_have_accessible_name("Diff, 5 lines added, 2 lines removed")
            assert page.get_by_role("tab", selected=True).inner_text() == "Overview"
            _settle(page)
            assert len(seen) == 1, seen
            assert sidecar.reads == 1
            _open_diff(page)
            _settle(page)
            assert len(seen) == 1, seen
            assert sidecar.reads == 1
        finally:
            page.close()
            sidecar.drop()


def test_rows_that_are_not_selected_cost_no_diff_read():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(), _container_run(OTHER, run_id="idle-run"):
        mine = _connect(live)
        other = _connect(live, OTHER)
        page = _open(live)
        seen = _requests(page)
        try:
            _pick(page)
            _settle(page, 1200)
            assert (mine.reads, other.reads) == (1, 0)
            assert len(seen) == 1
        finally:
            page.close()
            mine.drop()
            other.drop()


def test_a_native_run_an_ended_run_and_a_run_without_a_sidecar_have_no_diff_tab():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run("nativebox123", native=True, run_id="native-run"), _container_run(OTHER, run_id="ended-run"), \
            _container_run("quietbox1234", run_id="quiet-run"):
        ended = _connect(live, OTHER)
        _push_exited(live, OTHER)
        page = _open(live)
        try:
            for container in ("nativebox123", OTHER, "quietbox1234"):
                _pick(page, container)
                expect(page.get_by_role("tab", name="Overview")).to_be_visible()
                expect(_tab(page, "Diff")).to_have_count(0)
        finally:
            page.close()
            ended.drop()


def test_a_diff_tab_appears_within_five_seconds_of_the_sidecar_connecting_and_reads_once():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        page = _open(live)
        seen = _requests(page)
        try:
            _pick(page)
            expect(_tab(page, "Diff")).to_have_count(0)
            sidecar = _connect(live)
            try:
                expect(_tab(page, "Diff")).to_contain_text(SIZE, timeout=5000)
                _settle(page, 1200)
                assert len(seen) == 1, seen
                assert sidecar.reads == 1
            finally:
                sidecar.drop()
        finally:
            page.close()


def test_the_tab_stays_marked_stale_when_the_sidecar_drops_while_diff_is_open():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            sidecar.drop()
            expect(page.locator("#detail-diff-stale")).to_have_text("stale", timeout=5000)
            expect(page.get_by_role("tab", selected=True)).to_have_text(re.compile(r"^Diff"))
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
        finally:
            page.close()


def test_the_tab_goes_and_overview_shows_when_the_run_ends_while_diff_is_open():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _push_exited(live, CONTAINER)
            expect(_tab(page, "Diff")).to_have_count(0, timeout=5000)
            expect(page.get_by_role("tab", selected=True)).to_have_text("Overview")
        finally:
            page.close()
            sidecar.drop()


def test_a_dropped_sidecar_that_reconnects_clears_the_stale_mark_and_keeps_the_diff_tab():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            sidecar.drop()
            expect(page.locator("#detail-diff-stale")).to_have_text("stale", timeout=5000)
            again = _connect(live)
            try:
                expect(page.locator("#detail-diff-stale")).to_have_count(0, timeout=5000)
                expect(page.get_by_role("tab", selected=True)).to_have_text(re.compile(r"^Diff"))
            finally:
                again.drop()
        finally:
            page.close()


def test_opening_diff_lists_changed_files_in_a_tree_with_counts_and_shows_the_first_file():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            tree = page.locator("#detail-panel .fd-tree")
            expect(tree.locator(".tree-dir-head")).to_have_text([re.compile("docs"), re.compile("services/api")])
            first = tree.locator(".tree-file").first
            expect(first).to_contain_text("README.md")
            expect(first).to_contain_text("+0")
            expect(first).to_contain_text("−1")
            sign_in = tree.locator(".tree-file", has_text="sign_in.py")
            expect(sign_in).to_contain_text("+3")
            expect(sign_in).to_contain_text("−1")
            expect(first).to_have_attribute("aria-current", "true")
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("docs/README.md")
            head = page.locator("#detail-diff-file-head")
            expect(head).to_contain_text("docs/README.md")
            expect(head).to_contain_text("+0")
            expect(head).to_contain_text("−1")
            expect(head).to_contain_text("deleted file")
            expect(head).to_contain_text("uncommitted")
            expect(page.locator("#detail-panel .d2h-file-header")).to_be_hidden()
            sign_in.click()
            expect(head).to_contain_text("services/api/sign_in.py")
            expect(head).to_contain_text("+3")
            expect(head).not_to_contain_text("deleted file")
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("new c")
            expect(page.locator("#detail-panel .fd-view")).not_to_contain_text("lock one")
            expect(sign_in).to_have_attribute("aria-current", "true")
            tree.locator(".tree-file", has_text="lockout.py").click()
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("lock one")
        finally:
            page.close()
            sidecar.drop()


def test_selecting_an_untracked_file_leaves_the_dashboard_socket_open_and_the_footer_live():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply=_read(DIFF, ("services/api/lockout_store.py",)))
        page = _open(live)
        closed: list[str] = []
        page.on("websocket", lambda ws: ws.on("close", lambda _: closed.append(ws.url)))
        try:
            expect(page.locator("[data-conn]")).to_have_attribute("data-conn", "live", timeout=10000)
            _pick(page)
            _open_diff(page)
            page.get_by_role("button", name=re.compile("lockout_store.py")).click()
            _settle(page, 1500)
            expect(page.locator("[data-conn]")).to_have_attribute("data-conn", "live")
            assert not closed
        finally:
            page.close()
            sidecar.drop()


def test_a_chain_of_single_child_folders_is_one_row_and_a_folder_with_two_children_is_not():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    diff = (
        _patch("deep/one/two/z.py", [], ["z"])
        + _patch("pkg/core/x.py", [], ["x"])
        + _patch("pkg/web/y.py", [], ["y"])
    )
    with _container_run():
        sidecar = _connect(live, reply=_read(diff))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            heads = page.locator("#detail-panel .fd-tree .tree-dir-head")
            expect(heads).to_have_text([re.compile("deep/one/two"), re.compile("pkg"), re.compile("core"), re.compile("web")])
            expect(page.locator("#detail-panel .fd-tree .tree-file", has_text="z.py")).to_have_count(1)
        finally:
            page.close()
            sidecar.drop()


def test_a_new_file_says_so_in_the_header_above_its_lines():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    diff = "diff --git a/n.py b/n.py\nnew file mode 100644\nindex 0000000..2222222\n--- /dev/null\n+++ b/n.py\n@@ -0,0 +1,2 @@\n+one\n+two\n"
    with _container_run():
        sidecar = _connect(live, reply=_read(diff))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            head = page.locator("#detail-diff-file-head")
            expect(head).to_contain_text("n.py")
            expect(head).to_contain_text("+2")
            expect(head).to_contain_text("new file")
        finally:
            page.close()
            sidecar.drop()


def test_the_run_header_chip_says_docker_sidecar_only_while_the_sidecar_is_connected():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        page = _open(live)
        try:
            _pick(page)
            expect(page.locator("#detail-panel, .detail-head").first).to_be_visible()
            expect(page.locator("#run-sidecar-chip")).to_have_count(0)
            sidecar = _connect(live)
            expect(page.locator("#run-sidecar-chip")).to_have_text("docker · sidecar", timeout=10000)
            sidecar.drop()
            expect(page.locator("#run-sidecar-chip")).to_have_text("docker", timeout=10000)
        finally:
            page.close()


def test_the_tab_says_when_the_diff_was_read_and_refresh_reads_again_and_updates_the_counts():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        seen = _requests(page)
        try:
            _pick(page)
            _open_diff(page)
            clock = page.locator(".dtabs .right")
            expect(clock).to_contain_text(re.compile(r"read \d\d:\d\d:\d\d"))
            first = clock.inner_text()
            page.wait_for_timeout(2500)
            assert clock.inner_text() != first
            sidecar.reply = _read(SIGN_IN)
            page.get_by_role("button", name="Read the diff again").click()
            expect(_tab(page, "Diff")).to_contain_text("+3 −1")
            assert sidecar.reads == 2
            assert len(seen) == 2
            expect(page.locator("#detail-panel .fd-tree .tree-file")).to_have_count(1)
        finally:
            page.close()
            sidecar.drop()


def test_untracked_files_sit_in_their_own_group_and_are_not_counted_in_the_tab():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply=_read(DIFF, ("services/api/lockout_store.py", "notes.md")))
        page = _open(live)
        try:
            _pick(page)
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            _open_diff(page)
            group = page.locator("#detail-panel .fd-tree .tree-dir", has_text="Not tracked by git yet")
            expect(group.locator(".tree-file")).to_have_text([re.compile("notes.md"), re.compile("services/api/lockout_store.py")])
            expect(group.locator(".tree-file .fstat")).to_have_count(0)
            group.get_by_role("button", name=re.compile("lockout_store.py")).click()
            expect(page.locator("#detail-panel .fd-view")).to_have_text(
                "services/api/lockout_store.py has no diff because git does not track it yet."
            )
        finally:
            page.close()
            sidecar.drop()


def test_a_clean_checkout_says_so_and_the_tab_shows_no_count():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply=_read(""))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel")).to_contain_text("There are no uncommitted changes in this checkout.")
            expect(_tab(page, "Diff")).to_have_text("Diff")
        finally:
            page.close()
            sidecar.drop()


def test_a_checkout_with_only_untracked_files_lists_them_and_says_no_tracked_file_changed():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply=_read("", ("scratch.py",)))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("scratch.py")
            expect(page.locator("#detail-panel .fd-view")).to_have_text("No tracked file has changed in this checkout.")
            expect(_tab(page, "Diff")).to_have_text("Diff")
        finally:
            page.close()
            sidecar.drop()


def test_while_the_diff_is_read_the_tab_says_so_and_the_state_clears_when_it_arrives():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        sidecar.hold.clear()
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            reading = page.get_by_role("status").filter(has_text="Reading the diff…")
            expect(reading).to_be_visible()
            expect(reading).to_have_attribute("aria-busy", "true")
            sidecar.hold.set()
            expect(reading).to_have_count(0)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
        finally:
            sidecar.hold.set()
            page.close()
            sidecar.drop()


def test_an_unreadable_diff_says_so_offers_a_retry_and_clears_when_a_read_succeeds():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply=_read("", failed=True))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            alert = page.locator("#detail-panel").get_by_role("alert")
            expect(alert).to_contain_text("This diff could not be read")
            expect(alert).to_contain_text("This does not mean there are no changes.")
            expect(page.locator("#detail-panel")).not_to_contain_text("no uncommitted changes")
            expect(_tab(page, "Diff")).to_have_text("Diff")
            sidecar.reply = _read()
            alert.get_by_role("button", name="Retry now").click()
            expect(page.locator("#detail-panel").get_by_role("alert")).to_have_count(0)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
        finally:
            page.close()
            sidecar.drop()


def test_a_read_the_sidecar_errors_on_also_reads_as_unreadable_never_as_no_changes():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        sidecar.fail = True
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel").get_by_role("alert")).to_contain_text("This diff could not be read")
            expect(page.locator("#detail-panel")).not_to_contain_text("no uncommitted changes")
        finally:
            page.close()
            sidecar.drop()


def test_an_empty_diff_from_a_sidecar_too_old_to_report_failure_cannot_be_confirmed():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply={"diff": ""})
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel")).to_contain_text(
                "This sidecar is too old to report a failed read, so it cannot confirm there are no changes."
            )
            expect(page.locator("#detail-panel")).not_to_contain_text("There are no uncommitted changes")
        finally:
            page.close()
            sidecar.drop()


def test_the_details_tab_no_longer_shows_the_working_tree_diff_and_reads_as_before():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live)
        page = _open(live)
        seen = _requests(page)
        try:
            _pick(page)
            page.get_by_role("tab", name="Details").click()
            expect(page.locator("#detail-panel")).to_contain_text("Recent telemetry history")
            expect(page.locator("#detail-panel")).to_contain_text("Metrics")
            expect(page.locator("#detail-panel details.disclosure")).to_have_count(0)
            expect(page.locator("#detail-panel")).not_to_contain_text("Working-tree diff")
            _settle(page)
            assert len(seen) == 1
        finally:
            page.close()
            sidecar.drop()


def test_diff_content_cannot_inject_markup():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    hostile = _patch("x/<img src=x onerror=window.__pwned=1>.py", [], ['<img src=y onerror="window.__pwned=1">', "<script>window.__pwned=1</script>"])
    with _container_run():
        sidecar = _connect(live, reply=_read(hostile, ("<b id=bold>u</b>.py",)))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("window.__pwned=1")
            _settle(page)
            assert page.locator("#detail-panel img, #detail-panel script, #detail-panel #bold").count() == 0
            assert page.evaluate("window.__pwned") is None
        finally:
            page.close()
            sidecar.drop()


def test_diff_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run():
        sidecar = _connect(live, reply=_read(DIFF, ("scratch.py",)))
        page = _open(live)
        try:
            _pick(page)
            page.get_by_role("tab", name="Details").click()
            page.keyboard.press("ArrowRight")
            expect(_tab(page, "Files")).to_be_focused()
            page.keyboard.press("ArrowRight")
            expect(_tab(page, "Diff")).to_be_focused()
            expect(_tab(page, "Diff")).to_have_attribute("aria-selected", "true")
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            page.keyboard.press("ArrowRight")
            expect(page.get_by_role("tab", name="Overview")).to_be_focused()
            page.keyboard.press("ArrowLeft")
            expect(_tab(page, "Diff")).to_be_focused()
            refresh = page.get_by_role("button", name="Read the diff again")
            refresh.focus()
            sidecar.reply = _read(SIGN_IN)
            page.keyboard.press("Enter")
            expect(_tab(page, "Diff")).to_contain_text("+3 −1")
            assert sidecar.reads == 2
            first = page.locator("#detail-panel .fd-tree .tree-file").first
            first.focus()
            assert first.evaluate("(el) => el.tagName") == "BUTTON"
            assert not _scan(page)
        finally:
            page.close()
            sidecar.drop()
