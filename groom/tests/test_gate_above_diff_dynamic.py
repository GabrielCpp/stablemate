"""A gate opening, collapsing and being answered above the Diff and Files tabs, measured on the page the operator gets."""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _box,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_diff_tab_dynamic import (
    CONTAINER,
    OTHER,
    RUN,
    _container_run,
    _patch,
    _pick,
    _requests,
    _settle,
    _tab,
    _wait_for,
)
from test_gate_strip_dynamic import FIRST, SECOND, _post
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

LONG = _patch("services/api/lockout.py", [f"old {n}" for n in range(40)], [f"new line {n}" for n in range(260)])
SMALL = _patch("services/api/sign_in.py", ["old a"], ["new a", "new b"])
DIFF = SMALL + LONG
BODY = "\n".join(f"line_{n:03d} = {n}" for n in range(300)) + "\n"
FILES = {"services/api/lockout.py": BODY, "services/api/sign_in.py": "def sign_in():\n    pass\n"}


class _Sidecar:
    def __init__(self, live, container: str) -> None:
        self.container = container
        self.diff_reads = 0
        self.tree_reads = 0
        self.file_reads: list[str] = []
        self.questions: list[str] = []
        self.answers: list[tuple[str, str]] = []
        self.socket = connect(f"ws://127.0.0.1:{live.port}/sidecar")
        hello = {
            "type": "hello",
            "identity": {"container_id": container, "name": "coder-acme", "run_id": RUN, "workflow": "coder"},
            "snapshot": {"current_node": "build", "terminal": "", "gates": []},
        }
        self.socket.send(json.dumps(hello))
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _answer(self, message: dict) -> dict:
        method = message["method"]
        if method == "getDiff":
            self.diff_reads += 1
            return {"ok": True, "data": {"diff": DIFF, "untracked": [], "failed": False}}
        if method == "getTree":
            self.tree_reads += 1
            return {"ok": True, "data": {"paths": sorted(FILES), "failed": False}}
        if method == "getFile":
            path = message["params"]["path"]
            self.file_reads.append(path)
            return {"ok": True, "data": {"content": FILES[path], "failed": False}}
        if method == "getQuestions":
            return {"ok": True, "data": {"ok": True, "questions": [{"path": path, "kind": "operator"} for path in self.questions]}}
        if method == "answerGate":
            params = message["params"]
            self.answers.append((params["path"], params["body"]))
            return {"ok": True, "data": {"ok": True, "path": params["path"]}}
        return {"ok": True, "data": {}}

    def _serve(self) -> None:
        try:
            for raw in self.socket:
                message = json.loads(raw)
                if message.get("type") != "rpc":
                    continue
                self.socket.send(json.dumps({"type": "rpc_result", "id": message["id"], **self._answer(message)}))
        except ConnectionClosed:
            pass

    def drop(self) -> None:
        from groom import sidecar_hub

        self.socket.close()
        self.thread.join(timeout=5)
        _wait_for(lambda: sidecar_hub.get(self.container) is None, "the sidecar to unregister")


def _connect(live, container: str = CONTAINER) -> _Sidecar:
    from groom import sidecar_hub

    sidecar = _Sidecar(live, container)
    _wait_for(lambda: sidecar_hub.get(container) is not None, "the sidecar to register")
    return sidecar


@contextmanager
def _runs(*containers: str) -> Iterator[None]:
    from contextlib import ExitStack

    with ExitStack() as stack:
        for index, container in enumerate(containers):
            stack.enter_context(_container_run(container, run_id=f"{RUN}-{index}" if index else RUN))
        yield


def _open_gate(live, path: str, question: str, container: str = CONTAINER, sidecar: _Sidecar | None = None) -> None:
    if sidecar is not None:
        sidecar.questions.append(path)
    _post(live, "/push/blocked", {"container_id": container, "file_path": path, "question": question})


def _strip(page):
    return page.get_by_role("region", name="Open gates")


def _view(page) -> dict:
    return page.evaluate(
        "() => { const el = document.querySelector('#detail-panel .fd-view');"
        " return { scrollTop: el.scrollTop, room: el.scrollHeight - el.clientHeight, top: el.getBoundingClientRect().top,"
        " head: (document.querySelector('#detail-diff-file-head, #detail-files-file-head') || {}).textContent || '' }; }"
    )


def _scroll(page, to: int) -> None:
    page.evaluate("(to) => { document.querySelector('#detail-panel .fd-view').scrollTop = to; }", to)
    _settle(page, 150)


def _read_diff(page) -> int:
    _tab(page, "Diff").click()
    page.wait_for_selector("#detail-panel .fd-split", timeout=10000)
    page.locator("#detail-panel .fd-tree").get_by_role("button", name=re.compile("lockout.py")).click()
    page.wait_for_selector("#detail-diff-file-head:has-text('lockout.py')", timeout=10000)
    _scroll(page, 400)
    assert _view(page)["scrollTop"] >= 300
    return int(_view(page)["scrollTop"])


def _read_files(page) -> int:
    _tab(page, "Files").click()
    page.wait_for_selector("#detail-panel .fd-split", timeout=10000)
    page.locator("#detail-panel .fd-tree").get_by_role("button", name="lockout.py", exact=True).click()
    page.wait_for_selector("#detail-files-file-head:has-text('lockout.py')", timeout=10000)
    _scroll(page, 400)
    assert _view(page)["scrollTop"] >= 300
    return int(_view(page)["scrollTop"])


def _selected_file(page) -> str:
    return page.locator("#detail-panel .fd-tree .tree-file[aria-current='true'], #detail-panel .fd-tree .tree-file.active").first.inner_text()


def test_a_gate_that_opens_while_diff_is_open_shows_above_the_tabs_and_leaves_the_file_and_scroll_alone():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        reads = _requests(page)
        try:
            _pick(page)
            before = _read_diff(page)
            file_before = _selected_file(page)
            _settle(page)
            _open_gate(live, "/workspace/gates/1-one.md", FIRST, sidecar=sidecar)
            strip = _strip(page)
            expect(strip).to_contain_text("legacy CSV header order")
            expect(strip.get_by_role("textbox", name="Your answer")).to_be_visible()
            expect(strip.get_by_role("button", name="Send answer")).to_be_visible()
            assert _box(strip)["y"] + _box(strip)["height"] <= _box(page.get_by_role("tablist"))["y"] + 1
            expect(_tab(page, "Diff")).to_have_attribute("aria-selected", "true")
            _settle(page)
            assert _selected_file(page) == file_before
            assert abs(_view(page)["scrollTop"] - before) <= 1
            assert len(reads) == 1 and sidecar.diff_reads == 1
        finally:
            page.close()
            sidecar.drop()


def test_the_question_collapses_to_one_line_and_the_diff_keeps_scrolling():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_gate(live, "/workspace/gates/1-one.md", FIRST, sidecar=sidecar)
            _read_diff(page)
            strip = _strip(page)
            full = _box(strip)["height"]
            strip.get_by_role("button", name="Collapse").click()
            expect(strip.get_by_role("textbox")).to_have_count(0)
            expect(strip.get_by_role("button", name="Answer", exact=True)).to_have_attribute("aria-expanded", "false")
            assert _box(strip)["height"] < full / 2
            expect(_tab(page, "Diff")).to_have_attribute("aria-selected", "true")
            _scroll(page, 600)
            first = _view(page)["scrollTop"]
            assert first >= 500
            page.locator("#detail-panel .fd-view").hover()
            page.mouse.wheel(0, -200)
            _settle(page, 300)
            assert _view(page)["scrollTop"] < first
            assert not _scan(page)
        finally:
            page.close()
            sidecar.drop()


def test_answering_above_the_diff_sends_the_answer_removes_the_question_and_keeps_tab_file_and_scroll_without_a_new_read():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        reads = _requests(page)
        try:
            _pick(page)
            gate = "/workspace/gates/1-one.md"
            _open_gate(live, gate, FIRST, sidecar=sidecar)
            before = _read_diff(page)
            file_before = _selected_file(page)
            _settle(page)
            strip = _strip(page)
            strip.get_by_role("textbox", name="Your answer").fill("keep the legacy order")
            strip.get_by_role("button", name="Send answer").click()
            expect(_strip(page)).to_have_count(0)
            assert sidecar.answers == [(gate, "keep the legacy order")]
            expect(_tab(page, "Diff")).to_have_attribute("aria-selected", "true")
            _settle(page, 500)
            assert _selected_file(page) == file_before
            assert abs(_view(page)["scrollTop"] - before) <= 1
            assert len(reads) == 1 and sidecar.diff_reads == 1
        finally:
            page.close()
            sidecar.drop()


def test_files_keeps_its_file_and_scroll_through_a_gate_and_an_answer_without_a_new_read():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            before = _read_files(page)
            file_before = _selected_file(page)
            _settle(page)
            gate = "/workspace/gates/1-one.md"
            _open_gate(live, gate, FIRST, sidecar=sidecar)
            strip = _strip(page)
            expect(strip).to_contain_text("legacy CSV header order")
            expect(_tab(page, "Files")).to_have_attribute("aria-selected", "true")
            _settle(page)
            assert abs(_view(page)["scrollTop"] - before) <= 1
            strip.get_by_role("textbox", name="Your answer").fill("yes")
            strip.get_by_role("button", name="Send answer").click()
            expect(_strip(page)).to_have_count(0)
            assert sidecar.answers == [(gate, "yes")]
            _settle(page, 500)
            expect(_tab(page, "Files")).to_have_attribute("aria-selected", "true")
            assert _selected_file(page) == file_before
            assert abs(_view(page)["scrollTop"] - before) <= 1
            assert sidecar.tree_reads == 1
            assert sidecar.file_reads == ["services/api/lockout.py"]
        finally:
            page.close()
            sidecar.drop()


def test_j_and_k_typed_in_the_answer_box_type_those_letters_and_leave_the_run_and_the_file_alone():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER, OTHER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_gate(live, "/workspace/gates/1-one.md", FIRST, sidecar=sidecar)
            _read_diff(page)
            file_before = _selected_file(page)
            box = _strip(page).get_by_role("textbox", name="Your answer")
            box.focus()
            page.keyboard.type("jkjk and then jk")
            expect(box).to_have_value("jkjk and then jk")
            expect(box).to_be_focused()
            expect(page.locator("#runs-list .row[aria-current='true']")).to_have_attribute("data-worker-id", CONTAINER)
            assert _selected_file(page) == file_before
            expect(_tab(page, "Diff")).to_have_attribute("aria-selected", "true")
        finally:
            page.close()
            sidecar.drop()


def test_selecting_another_run_keeps_what_was_typed_for_this_runs_gate_until_it_is_sent():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER, OTHER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            gate = "/workspace/gates/1-one.md"
            other_gate = "/workspace/gates/2-two.md"
            _open_gate(live, gate, FIRST, sidecar=sidecar)
            _open_gate(live, other_gate, SECOND, OTHER)
            _pick(page)
            box = _strip(page).get_by_role("textbox", name="Your answer")
            box.fill("half typed for the first run")
            _pick(page, OTHER)
            other_box = _strip(page).get_by_role("textbox", name="Your answer")
            expect(_strip(page)).to_contain_text("changelog mention")
            expect(other_box).to_have_value("")
            other_box.fill("only for the second")
            _pick(page)
            expect(_strip(page).get_by_role("textbox", name="Your answer")).to_have_value("half typed for the first run")
            _pick(page, OTHER)
            expect(_strip(page).get_by_role("textbox", name="Your answer")).to_have_value("only for the second")
            _pick(page)
            _strip(page).get_by_role("button", name="Send answer").click()
            expect(_strip(page)).to_have_count(0)
            assert sidecar.answers == [(gate, "half typed for the first run")]
            _pick(page, OTHER)
            expect(_strip(page).get_by_role("textbox", name="Your answer")).to_have_value("only for the second")
        finally:
            page.close()
            sidecar.drop()


def test_the_answer_box_and_send_control_have_roles_names_and_keyboard_operation_and_pass_axe_on_diff_and_files():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _runs(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            gate = "/workspace/gates/1-one.md"
            _open_gate(live, gate, FIRST, sidecar=sidecar)
            _read_diff(page)
            strip = _strip(page)
            expect(strip).to_contain_text("Waiting on you")
            assert not _scan(page)
            _read_files(page)
            assert not _scan(page)
            box = strip.get_by_role("textbox", name="Your answer")
            box.focus()
            page.keyboard.type("by keyboard")
            page.keyboard.press("Tab")
            expect(strip.get_by_role("button", name="Send answer")).to_be_focused()
            page.keyboard.press("Enter")
            expect(_strip(page)).to_have_count(0)
            assert sidecar.answers == [(gate, "by keyboard")]
            expect(_tab(page, "Files")).to_have_attribute("aria-selected", "true")
        finally:
            page.close()
            sidecar.drop()
