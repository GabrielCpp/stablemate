"""The Files tab of a container run, measured on the page the operator gets, against a real sidecar socket."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from unittest.mock import patch

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_diff_tab_dynamic import (
    _container_run,
    _pick as _pick_run_row,
    _push_exited,
    _settle,
    _tab,
    _wait_for,
)
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

CONTAINER = "filesbox1234"
OTHER = "filesbox5678"
RUN = "files-run"
SIGN_IN = 'import json\n\n\ndef sign_in(request):\n    """Return a session."""\n    return {"ok": True}\n'
FILES = {
    "services/api/sign_in.py": SIGN_IN,
    "services/api/lockout.py": "MAX_FAILURES = 5\n",
    "services/api/blank.py": "",
    "tests/test_sign_in.py": "def test_sign_in():\n    assert True\n",
    "README.md": "# acme\n",
}


@dataclass
class _Checkout:
    files: dict[str, str] = field(default_factory=lambda: dict(FILES))
    tree_failed: bool = False
    unreported: bool = False
    unreadable: set[str] = field(default_factory=set)
    erroring: bool = False


class _Sidecar:
    """A sidecar speaking the real protocol over a real socket, answering getTree and getFile from a script and counting the reads."""

    def __init__(self, live, container: str, checkout: _Checkout | None = None) -> None:
        self.container = container
        self.checkout = checkout if checkout is not None else _Checkout()
        self.tree_hold = threading.Event()
        self.tree_hold.set()
        self.file_hold = threading.Event()
        self.file_hold.set()
        self.tree_reads = 0
        self.file_reads: list[str] = []
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
        checkout = self.checkout
        method = message["method"]
        if method == "getTree":
            self.tree_reads += 1
            self.tree_hold.wait(10)
            if checkout.erroring:
                return {"ok": False, "error": "walk blew up"}
            data: dict = {"paths": [] if checkout.tree_failed else sorted(checkout.files)}
            if not checkout.unreported:
                data["failed"] = checkout.tree_failed
            return {"ok": True, "data": data}
        if method == "getFile":
            path = message["params"]["path"]
            self.file_reads.append(path)
            self.file_hold.wait(10)
            if checkout.erroring:
                return {"ok": False, "error": "read blew up"}
            unreadable = path in checkout.unreadable or path not in checkout.files
            data = {"content": "" if unreadable else checkout.files[path]}
            if not checkout.unreported:
                data["failed"] = unreadable
            return {"ok": True, "data": data}
        return {"ok": True, "data": {}}

    def _serve(self) -> None:
        try:
            for raw in self.socket:
                message = json.loads(raw)
                if message.get("type") != "rpc":
                    continue
                reply = {"type": "rpc_result", "id": message["id"], **self._answer(message)}
                self.socket.send(json.dumps(reply))
        except ConnectionClosed:
            pass

    def drop(self) -> None:
        from groom import sidecar_hub

        self.socket.close()
        self.thread.join(timeout=5)
        _wait_for(lambda: sidecar_hub.get(self.container) is None, "the sidecar to unregister")


def _connect(live, container: str = CONTAINER, checkout: _Checkout | None = None) -> _Sidecar:
    from groom import sidecar_hub

    sidecar = _Sidecar(live, container, checkout)
    _wait_for(lambda: sidecar_hub.get(container) is not None, "the sidecar to register")
    return sidecar


def _pick(page, container: str = CONTAINER) -> None:
    _pick_run_row(page, container)


def _reads(page, marker: str) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if marker in request.url else None)
    return seen


def _open_files(page) -> None:
    _tab(page, "Files").click()
    page.wait_for_selector("#detail-panel .fd-split, #detail-panel .detail-empty:not(.loading), #detail-panel .side-state", timeout=10000)


def _open_file(page, name: str) -> None:
    page.locator("#detail-panel .fd-tree").get_by_role("button", name=name, exact=True).click()


def test_a_run_that_shows_a_diff_tab_shows_a_files_tab_before_it_and_other_runs_show_neither():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER), _container_run("nativebox456", native=True, run_id="native-run"), \
            _container_run(OTHER, run_id="ended-run"), _container_run("quietbox5678", run_id="quiet-run"):
        sidecar = _connect(live)
        ended = _connect(live, OTHER)
        _push_exited(live, OTHER)
        page = _open(live)
        try:
            _pick(page)
            tabs = page.get_by_role("tablist", name="Run detail").get_by_role("tab")
            expect(tabs).to_have_text([re.compile("^Overview$"), re.compile("^Details$"), re.compile("^Files$"), re.compile(r"^Diff")])
            for container in ("nativebox456", OTHER, "quietbox5678"):
                _pick(page, container)
                expect(page.get_by_role("tab", name="Overview")).to_be_visible()
                expect(_tab(page, "Files")).to_have_count(0)
                expect(_tab(page, "Diff")).to_have_count(0)
        finally:
            page.close()
            sidecar.drop()
            ended.drop()


def test_selecting_a_run_reads_no_tree_and_the_first_open_of_files_reads_it_once():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        trees = _reads(page, "/files/")
        try:
            _pick(page)
            _settle(page)
            assert trees == []
            assert sidecar.tree_reads == 0
            _tab(page, "Diff").click()
            _settle(page)
            assert trees == []
            _open_files(page)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            assert len(trees) == 1
            assert sidecar.tree_reads == 1
        finally:
            page.close()
            sidecar.drop()


def test_opening_files_lists_the_checkout_in_a_folder_tree_and_a_folder_collapses_and_expands():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            heads = page.locator("#detail-panel .fd-tree .tree-dir-head")
            expect(heads).to_have_text([re.compile("services/api"), re.compile("tests")])
            files = page.locator("#detail-panel .fd-tree .tree-file")
            expect(files).to_have_text(["blank.py", "lockout.py", "sign_in.py", "test_sign_in.py", "README.md"])
            api = page.get_by_role("button", name="services/api")
            expect(api).to_have_attribute("aria-expanded", "true")
            api.click()
            expect(api).to_have_attribute("aria-expanded", "false")
            expect(page.get_by_role("button", name="sign_in.py", exact=True)).not_to_be_visible()
            api.click()
            expect(api).to_have_attribute("aria-expanded", "true")
            expect(page.locator("#detail-panel .fd-tree .tree-file", has_text="lockout.py")).to_be_visible()
        finally:
            page.close()
            sidecar.drop()


def test_before_a_file_is_selected_the_tab_asks_for_one():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            expect(page.locator("#detail-panel .fd-view")).to_have_text("Select a file to read it.")
            assert sidecar.file_reads == []
        finally:
            page.close()
            sidecar.drop()


def test_selecting_a_file_shows_its_content_with_line_numbers_and_syntax_coloring():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "sign_in.py")
            head = page.locator("#detail-files-file-head")
            expect(head).to_contain_text("services/api/sign_in.py")
            expect(head).to_contain_text("6 lines")
            expect(head).to_contain_text("python")
            code = page.locator("#detail-panel .file-pre")
            expect(code).to_contain_text('return {"ok": True}')
            assert page.locator("#detail-panel .file-pre .hljs-keyword").count() > 0
            gutter = page.locator("#detail-panel .code-gutter")
            assert gutter.inner_text().split() == ["1", "2", "3", "4", "5", "6"]
            assert gutter.get_attribute("aria-hidden") == "true"
            metrics = page.evaluate(
                """() => ["#detail-panel .code-gutter", "#detail-panel .file-pre"].map((sel) => {
                  const el = document.querySelector(sel);
                  const style = getComputedStyle(el);
                  return [el.getBoundingClientRect().top, style.lineHeight, style.paddingTop, style.fontSize];
                })"""
            )
            assert metrics[0] == metrics[1]
            expect(page.locator("#detail-panel .fd-tree .tree-file.active")).to_have_text("sign_in.py")
        finally:
            page.close()
            sidecar.drop()


def test_nothing_on_the_tab_can_change_a_file():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "sign_in.py")
            expect(page.locator("#detail-files-file-head")).to_be_visible()
            panel = page.locator("#detail-panel")
            assert panel.get_by_role("textbox").count() == 0
            assert panel.locator("[contenteditable], input, textarea, form").count() == 0
            names = panel.get_by_role("button").all_inner_texts()
            assert not [name for name in names if re.search(r"edit|save|delete|remove|rename", name, re.I)]
        finally:
            page.close()
            sidecar.drop()


def test_files_keeps_its_tree_and_selected_file_across_tabs_of_the_same_run_without_another_read():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        trees = _reads(page, "/files/")
        file_requests = _reads(page, "/file/")
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "sign_in.py")
            expect(page.locator("#detail-files-file-head")).to_be_visible()
            for other in ("Diff", "Details", "Overview"):
                page.get_by_role("tab", name=re.compile(f"^{other}")).click()
            _tab(page, "Files").click()
            expect(page.locator("#detail-files-file-head")).to_contain_text("services/api/sign_in.py")
            expect(page.locator("#detail-panel .fd-tree .tree-file.active")).to_have_text("sign_in.py")
            expect(page.locator("#detail-panel .file-pre")).to_contain_text("def sign_in")
            _settle(page)
            assert len(trees) == 1
            assert len(file_requests) == 1
            assert sidecar.tree_reads == 1
            assert sidecar.file_reads == ["services/api/sign_in.py"]
        finally:
            page.close()
            sidecar.drop()


def test_folders_the_operator_collapsed_stay_collapsed_across_tabs_of_the_same_run_and_reset_on_another_run():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER), _container_run(OTHER, run_id="other-run"):
        sidecar = _connect(live)
        other = _connect(live, OTHER)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            api = page.get_by_role("button", name="services/api")
            api.click()
            expect(api).to_have_attribute("aria-expanded", "false")
            for away in ("Diff", "Details", "Overview"):
                page.get_by_role("tab", name=re.compile(f"^{away}")).click()
            _tab(page, "Files").click()
            expect(page.get_by_role("button", name="services/api")).to_have_attribute("aria-expanded", "false")
            expect(page.get_by_role("button", name="tests")).to_have_attribute("aria-expanded", "true")
            _pick(page, OTHER)
            _open_files(page)
            expect(page.get_by_role("button", name="services/api")).to_have_attribute("aria-expanded", "true")
        finally:
            page.close()
            sidecar.drop()
            other.drop()


def test_close_shares_the_first_row_of_the_run_head_with_a_long_doing_line_at_any_width():
    from groom import state
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        state.WORKFLOWS[CONTAINER].activity = "reading every file in the checkout and writing a very long summary of it " * 3
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            close = page.get_by_role("button", name="Close run detail")
            doing = page.locator("#detail .detail-head .doing-line")
            expect(doing).to_be_visible()
            for width in (1400, 1100, 900):
                page.set_viewport_size({"width": width, "height": 900})
                chip = page.locator("#detail .detail-head .badge, #detail .detail-head .repo-branch").first
                close_box = close.bounding_box()
                chip_box = chip.bounding_box()
                doing_box = doing.bounding_box()
                assert close_box is not None and chip_box is not None and doing_box is not None
                assert close_box["y"] < doing_box["y"], width
                if width >= 1100:
                    assert abs(close_box["y"] + close_box["height"] / 2 - (chip_box["y"] + chip_box["height"] / 2)) < 16, width
                assert close_box["x"] + close_box["width"] <= width
        finally:
            page.close()
            sidecar.drop()


def test_the_code_sits_on_a_darker_band_than_the_pane_with_a_44px_gutter():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "sign_in.py")
            expect(page.locator("#detail-panel .code-view")).to_be_visible()
            band = page.eval_on_selector("#detail-panel .code-view", "(e) => getComputedStyle(e).backgroundColor")
            pane = page.eval_on_selector("#detail-panel .fd-view", "(e) => getComputedStyle(e).backgroundColor")
            assert band != pane
            gutter = page.locator("#detail-panel .code-gutter").bounding_box()
            assert gutter is not None and round(gutter["width"]) == 44
            band_box = page.locator("#detail-panel .code-view").bounding_box()
            view_box = page.locator("#detail-panel .fd-view").bounding_box()
            assert band_box is not None and view_box is not None
            assert band_box["height"] < view_box["height"] - 100
        finally:
            page.close()
            sidecar.drop()


def test_selecting_another_run_resets_files_and_its_first_open_reads_again():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER), _container_run(OTHER, run_id="other-run"):
        sidecar = _connect(live)
        other = _connect(live, OTHER, _Checkout(files={"other.txt": "elsewhere\n"}))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "sign_in.py")
            expect(page.locator("#detail-files-file-head")).to_be_visible()
            _pick(page, OTHER)
            expect(page.get_by_role("tab", selected=True)).to_have_text("Overview")
            assert other.tree_reads == 0
            _open_files(page)
            expect(page.locator("#detail-panel .fd-tree .tree-file")).to_have_text(["other.txt"])
            expect(page.locator("#detail-panel .fd-view")).to_have_text("Select a file to read it.")
            assert other.tree_reads == 1
            _pick(page)
            _open_files(page)
            expect(page.locator("#detail-panel .fd-view")).to_have_text("Select a file to read it.")
            assert sidecar.tree_reads == 2
        finally:
            page.close()
            sidecar.drop()
            other.drop()


def test_files_says_the_sidecar_stopped_answering_and_clears_on_reconnect():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            sidecar.drop()
            expect(page.locator("#detail-files-stale")).to_be_visible(timeout=5000)
            expect(page.locator("#detail-panel .fd-split")).to_have_count(0)
            again = _connect(live)
            try:
                expect(page.locator("#detail-files-stale")).to_have_count(0, timeout=5000)
                expect(page.locator("#detail-panel .fd-split")).to_be_visible(timeout=5000)
            finally:
                again.drop()
        finally:
            page.close()


def test_the_tab_goes_and_overview_shows_when_the_run_ends_while_files_is_open():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            _push_exited(live, CONTAINER)
            expect(_tab(page, "Files")).to_have_count(0, timeout=5000)
            expect(page.get_by_role("tab", selected=True)).to_have_text("Overview")
        finally:
            page.close()
            sidecar.drop()


def test_while_the_tree_and_a_file_are_read_the_tab_says_so_and_each_state_clears_when_it_arrives():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        sidecar.tree_hold.clear()
        page = _open(live)
        try:
            _pick(page)
            _tab(page, "Files").click()
            reading = page.get_by_role("status").filter(has_text="Reading the checkout…")
            expect(reading).to_be_visible()
            expect(reading).to_have_attribute("aria-busy", "true")
            sidecar.tree_hold.set()
            expect(reading).to_have_count(0)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            sidecar.file_hold.clear()
            _open_file(page, "sign_in.py")
            file_reading = page.get_by_role("status").filter(has_text="Reading services/api/sign_in.py…")
            expect(file_reading).to_be_visible()
            expect(file_reading).to_have_attribute("aria-busy", "true")
            sidecar.file_hold.set()
            expect(file_reading).to_have_count(0)
            expect(page.locator("#detail-files-file-head")).to_be_visible()
        finally:
            sidecar.tree_hold.set()
            sidecar.file_hold.set()
            page.close()
            sidecar.drop()


def test_a_tree_that_cannot_be_read_says_so_offers_a_retry_and_clears_when_a_read_succeeds():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live, checkout=_Checkout(tree_failed=True))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            alert = page.locator("#detail-panel").get_by_role("alert")
            expect(alert).to_contain_text("This checkout could not be read")
            expect(page.locator("#detail-panel")).not_to_contain_text("no files")
            sidecar.checkout.tree_failed = False
            alert.get_by_role("button", name="Retry now").click()
            expect(page.locator("#detail-panel").get_by_role("alert")).to_have_count(0)
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            assert sidecar.tree_reads == 2
        finally:
            page.close()
            sidecar.drop()


def test_a_tree_the_sidecar_errors_on_and_the_volume_cannot_read_reads_as_unreadable_never_as_empty():
    from groom import app as app_module
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER), patch.object(app_module.docker_io, "read_tree", return_value={"paths": [], "failed": True}):
        sidecar = _connect(live, checkout=_Checkout(erroring=True))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            expect(page.locator("#detail-panel").get_by_role("alert")).to_contain_text("This checkout could not be read")
            expect(page.locator("#detail-panel")).not_to_contain_text("no files")
        finally:
            page.close()
            sidecar.drop()


def test_a_file_that_cannot_be_read_says_so_offers_a_retry_and_clears_when_a_read_succeeds():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live, checkout=_Checkout(unreadable={"services/api/sign_in.py"}))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "sign_in.py")
            alert = page.locator("#detail-panel .fd-view").get_by_role("alert")
            expect(alert).to_contain_text("services/api/sign_in.py could not be read")
            expect(alert).to_contain_text("This does not mean the file is empty.")
            expect(page.locator("#detail-panel .fd-view")).not_to_contain_text("This file is empty.")
            expect(page.locator("#detail-panel .fd-tree")).to_be_visible()
            sidecar.checkout.unreadable.clear()
            alert.get_by_role("button", name="Retry now").click()
            expect(page.locator("#detail-panel .fd-view").get_by_role("alert")).to_have_count(0)
            expect(page.locator("#detail-panel .file-pre")).to_contain_text("def sign_in")
        finally:
            page.close()
            sidecar.drop()


def test_a_file_the_sidecar_errors_on_and_the_volume_cannot_read_reads_as_unreadable_never_as_empty():
    from groom import app as app_module
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER), patch.object(app_module.docker_io, "read_file", return_value=None):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            sidecar.checkout.erroring = True
            _open_file(page, "sign_in.py")
            expect(page.locator("#detail-panel .fd-view").get_by_role("alert")).to_contain_text("could not be read")
            expect(page.locator("#detail-panel .fd-view")).not_to_contain_text("This file is empty.")
        finally:
            page.close()
            sidecar.drop()


def test_an_empty_file_reads_as_empty_and_never_as_a_file_that_could_not_be_read():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "blank.py")
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("This file is empty.")
            expect(page.locator("#detail-files-file-head")).to_have_text("services/api/blank.py")
            assert page.locator("#detail-panel").get_by_role("alert").count() == 0
            assert page.locator("#detail-panel .code-view").count() == 0
        finally:
            page.close()
            sidecar.drop()


def test_an_empty_answer_from_a_sidecar_too_old_to_report_failure_cannot_be_confirmed():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live, checkout=_Checkout(files={"a.txt": ""}, unreported=True))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            _open_file(page, "a.txt")
            expect(page.locator("#detail-panel .fd-view")).to_contain_text(
                "This sidecar is too old to report a failed read, so it cannot confirm this file is empty."
            )
            expect(page.locator("#detail-panel")).not_to_contain_text("This file is empty.")
        finally:
            page.close()
            sidecar.drop()


def test_a_checkout_with_no_files_says_so():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live, checkout=_Checkout(files={}))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            expect(page.locator("#detail-panel")).to_contain_text("This checkout has no files.")
            assert page.locator("#detail-panel").get_by_role("alert").count() == 0
        finally:
            page.close()
            sidecar.drop()


def test_file_content_and_paths_cannot_inject_markup():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    hostile = {
        "x/<img src=x onerror=window.__pwned=1>.html": '<img src=y onerror="window.__pwned=1">\n<script>window.__pwned=1</script>\n',
        "<b id=bold>u.txt": "<b id=bold>plain</b>\n",
    }
    with _container_run(CONTAINER):
        sidecar = _connect(live, checkout=_Checkout(files=hostile))
        page = _open(live)
        try:
            _pick(page)
            _open_files(page)
            for name in ("<b id=bold>u.txt", "<img src=x onerror=window.__pwned=1>.html"):
                _open_file(page, name)
                expect(page.locator("#detail-files-file-head")).to_contain_text(name)
                expect(page.locator("#detail-panel .file-pre")).to_contain_text("<")
            _settle(page)
            assert page.locator("#detail-panel img, #detail-panel script, #detail-panel #bold").count() == 0
            assert page.evaluate("window.__pwned") is None
        finally:
            page.close()
            sidecar.drop()


def test_files_tab_controls_have_roles_names_and_keyboard_operation_and_pass_axe():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run(CONTAINER):
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            page.get_by_role("tab", name="Details").click()
            page.keyboard.press("ArrowRight")
            expect(_tab(page, "Files")).to_be_focused()
            expect(_tab(page, "Files")).to_have_attribute("aria-selected", "true")
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            page.keyboard.press("ArrowRight")
            expect(_tab(page, "Diff")).to_be_focused()
            page.keyboard.press("ArrowRight")
            expect(page.get_by_role("tab", name="Overview")).to_be_focused()
            page.keyboard.press("ArrowLeft")
            expect(_tab(page, "Diff")).to_be_focused()
            page.keyboard.press("ArrowLeft")
            expect(_tab(page, "Files")).to_be_focused()
            folder = page.get_by_role("button", name="services/api")
            folder.focus()
            page.keyboard.press("Enter")
            expect(folder).to_have_attribute("aria-expanded", "false")
            page.keyboard.press("Enter")
            expect(folder).to_have_attribute("aria-expanded", "true")
            leaf = page.get_by_role("button", name="sign_in.py", exact=True)
            leaf.focus()
            page.keyboard.press("Enter")
            expect(page.locator("#detail-panel .file-pre")).to_contain_text("def sign_in")
            expect(leaf).to_have_attribute("aria-current", "true")
            assert not _scan(page)
        finally:
            page.close()
            sidecar.drop()
