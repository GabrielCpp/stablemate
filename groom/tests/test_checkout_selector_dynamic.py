"""The checkout selector of a container run, and the rail without Files and Diff, measured on the page the operator gets against a real sidecar socket."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_diff_tab_dynamic import (
    _container_run,
    _patch,
    _pick,
    _settle,
    _tab,
    _wait_for,
)
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

CONTAINER = "checkoutbox1"
OTHER = "checkoutbox2"
API_DIFF = _patch("services/api/sign_in.py", ["old a"], ["new a", "new b", "new c"])
WEB_DIFF = _patch("src/app.tsx", ["gone x", "gone y"], ["new z"])
API_SIZE = "+3 −1"
WEB_SIZE = "+1 −2"


@dataclass
class _Checkout:
    files: dict[str, str]
    diff: str
    untracked: tuple[str, ...] = ()
    failed: bool = False


def _api() -> _Checkout:
    return _Checkout(
        {"services/api/sign_in.py": "def sign_in():\n    return 1\n", "README.md": "# api-service\n"},
        API_DIFF,
        ("scratch.py",),
    )


def _web() -> _Checkout:
    return _Checkout(
        {"src/app.tsx": "export const app = 1;\n", "package.json": "{}\n", "src/index.ts": "export {};\n"},
        WEB_DIFF,
    )


def _both() -> dict[str, _Checkout]:
    return {"api-service": _api(), "web-app": _web()}


class _Sidecar:
    """A sidecar over a real socket that holds several checkouts and records every read with the checkout it named."""

    def __init__(self, live, container: str, checkouts: dict[str, _Checkout], *, names: bool = True) -> None:
        self.container = container
        self.checkouts = checkouts
        self.names = names
        self.lock = threading.Lock()
        self.reads: list[tuple[str, str]] = []
        self.socket = connect(f"ws://127.0.0.1:{live.port}/sidecar")
        hello = {
            "type": "hello",
            "identity": {"container_id": container, "name": "coder-acme", "run_id": f"run-{container}", "workflow": "coder"},
            "snapshot": {"current_node": "build", "terminal": "", "gates": []},
        }
        self.socket.send(json.dumps(hello))
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def of(self, method: str) -> list[str]:
        with self.lock:
            return [repo for name, repo in self.reads if name == method]

    def _answer(self, message: dict) -> dict:
        method = message["method"]
        params = message["params"]
        repo = params.get("repo", "")
        with self.lock:
            self.reads.append((method, repo))
        names = sorted(self.checkouts)
        checkout = self.checkouts.get(repo or (names[0] if names else ""))
        extra = {"repos": names} if self.names else {}
        if method == "getTree":
            if checkout is None or checkout.failed:
                return {"ok": True, "data": {"paths": [], "failed": True, **extra}}
            return {"ok": True, "data": {"paths": sorted(checkout.files), "failed": False, **extra}}
        if method == "getDiff":
            if checkout is None or checkout.failed:
                return {"ok": True, "data": {"diff": "", "untracked": [], "failed": True, **extra}}
            return {"ok": True, "data": {"diff": checkout.diff, "untracked": list(checkout.untracked), "failed": False, **extra}}
        if method == "getFile":
            path = params["path"]
            content = checkout.files.get(path) if checkout else None
            return {"ok": True, "data": {"content": content or "", "failed": content is None}}
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
        self.socket.close()
        self.thread.join(timeout=5)


def _connect(live, container: str = CONTAINER, checkouts: dict[str, _Checkout] | None = None, *, names: bool = True) -> _Sidecar:
    from groom import sidecar_hub

    sidecar = _Sidecar(live, container, _both() if checkouts is None else checkouts, names=names)
    _wait_for(lambda: sidecar_hub.get(container) is not None, "the sidecar to register")
    return sidecar


def _requests(page, marker: str) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if marker in request.url else None)
    return seen


def _run(container: str = CONTAINER):
    return _container_run(container, run_id=f"run-{container}")


def _select(page):
    return page.get_by_role("combobox", name="Checkout")


def _show(page, name: str) -> None:
    _tab(page, name).click()
    page.wait_for_selector("#detail-panel .fd-split, #detail-panel .detail-empty:not(.loading), #detail-panel .side-state", timeout=10000)


def _files(page) -> list[str]:
    return page.locator("#detail-panel .fd-tree .tree-file .fname").all_inner_texts()


def test_a_run_with_several_checkouts_shows_a_selector_on_files_and_diff_only():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            for tab in ("Overview", "Activity"):
                _tab(page, tab).click()
                expect(_select(page)).to_have_count(0)
            for tab in ("Files", "Diff"):
                _show(page, tab)
                expect(_select(page)).to_be_visible()
                expect(_select(page).locator("option")).to_have_text(["api-service", "web-app"])
        finally:
            page.close()
            sidecar.drop()


def test_a_run_with_one_checkout_shows_no_selector():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, checkouts={"api-service": _api()})
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(page.locator("#detail-panel .fd-split")).to_be_visible()
            expect(_select(page)).to_have_count(0)
            _show(page, "Files")
            expect(_select(page)).to_have_count(0)
        finally:
            page.close()
            sidecar.drop()


def test_a_sidecar_that_names_no_checkouts_shows_no_selector_and_reads_the_default_one():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, names=False)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
            _show(page, "Files")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("README.md")
            expect(_select(page)).to_have_count(0)
            assert sidecar.of("getDiff") == [""]
            assert sidecar.of("getTree") == [""]
        finally:
            page.close()
            sidecar.drop()


def test_a_run_selected_for_the_first_time_shows_its_first_checkout():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, checkouts={"web-app": _web(), "api-service": _api()})
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_select(page)).to_have_value("api-service")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("sign_in.py")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
        finally:
            page.close()
            sidecar.drop()


def test_selecting_a_checkout_shows_its_change_and_its_tree_and_the_size_follows():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
            _select(page).select_option("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            expect(page.locator("#detail-panel .fd-tree .tree-file")).to_have_text(re.compile("app.tsx"))
            expect(page.locator("#detail-panel .fd-tree")).not_to_contain_text("sign_in.py")
            expect(page.locator("#detail-panel .fd-tree")).not_to_contain_text("Not tracked by git yet")
            assert sidecar.of("getDiff") == ["", "web-app"]
            assert sidecar.of("getTree") == []
            _show(page, "Files")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("package.json")
            assert _files(page) == ["app.tsx", "index.ts", "package.json"]
            assert sidecar.of("getTree") == ["web-app"]
        finally:
            page.close()
            sidecar.drop()


def test_one_selection_governs_files_and_diff_and_moving_between_them_reads_nothing_more():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Files")
            expect(_select(page)).to_have_value("api-service")
            _select(page).select_option("web-app")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("package.json")
            _show(page, "Diff")
            expect(_select(page)).to_have_value("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            _show(page, "Files")
            expect(_select(page)).to_have_value("web-app")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("package.json")
            _settle(page)
            assert sidecar.of("getTree") == ["api-service", "web-app"]
            assert sidecar.of("getDiff") == ["", "web-app"]
        finally:
            page.close()
            sidecar.drop()


def test_refreshing_the_diff_keeps_the_checkout_and_names_it_in_the_read():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            _select(page).select_option("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            sidecar.checkouts["web-app"].diff = _patch("src/app.tsx", [], ["a", "b", "c", "d"])
            page.get_by_role("button", name="Read the diff again").click()
            expect(_tab(page, "Diff")).to_contain_text("+4 −0")
            expect(_select(page)).to_have_value("web-app")
            assert sidecar.of("getDiff") == ["", "web-app", "web-app"]
        finally:
            page.close()
            sidecar.drop()


def test_selecting_another_run_and_coming_back_restores_the_checkout_each_run_had():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run(), _run(OTHER):
        first = _connect(live)
        second = _connect(live, OTHER)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            _select(page).select_option("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            _pick(page, OTHER)
            _show(page, "Diff")
            expect(_select(page)).to_have_value("api-service")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_select(page)).to_have_value("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            _show(page, "Files")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("package.json")
            assert first.of("getDiff") == ["", "web-app", "web-app"]
            assert first.of("getTree") == ["web-app"]
            assert second.of("getDiff") == [""]
        finally:
            page.close()
            first.drop()
            second.drop()


def test_a_reload_starts_again_at_the_first_checkout():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            _select(page).select_option("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            page.reload(wait_until="load")
            page.wait_for_selector("#runs-list .row", timeout=15000)
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_select(page)).to_have_value("api-service")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
        finally:
            page.close()
            sidecar.drop()


def test_changing_the_checkout_clears_the_open_file_and_the_collapsed_folders_of_files():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Files")
            page.locator("#detail-panel .fd-tree").get_by_role("button", name="README.md", exact=True).click()
            expect(page.locator("#detail-files-file-head")).to_contain_text("README.md")
            page.get_by_role("button", name="services/api").click()
            expect(page.get_by_role("button", name="services/api")).to_have_attribute("aria-expanded", "false")
            _select(page).select_option("web-app")
            expect(page.locator("#detail-panel .fd-view")).to_have_text("Select a file to read it.")
            expect(page.get_by_role("button", name="src", exact=True)).to_have_attribute("aria-expanded", "true")
            page.locator("#detail-panel .fd-tree").get_by_role("button", name="app.tsx", exact=True).click()
            expect(page.locator("#detail-panel .file-pre")).to_contain_text("export const app")
            _select(page).select_option("api-service")
            expect(page.locator("#detail-panel .fd-view")).to_have_text("Select a file to read it.")
            expect(page.get_by_role("button", name="services/api")).to_have_attribute("aria-expanded", "true")
            assert sidecar.of("getFile") == ["api-service", "web-app"]
        finally:
            page.close()
            sidecar.drop()


def test_every_file_read_names_the_selected_checkout():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        seen = _requests(page, "/file/")
        try:
            _pick(page, CONTAINER)
            _show(page, "Files")
            _select(page).select_option("web-app")
            page.locator("#detail-panel .fd-tree").get_by_role("button", name="package.json", exact=True).click()
            expect(page.locator("#detail-panel .file-pre")).to_contain_text("{}")
            assert [url.split("repo=")[1].split("&")[0] for url in seen] == ["web-app"]
        finally:
            page.close()
            sidecar.drop()


def test_a_remembered_checkout_that_is_gone_falls_back_to_the_first_one_and_never_shows_an_empty_pane():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run(), _run(OTHER):
        first = _connect(live)
        second = _connect(live, OTHER)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            _select(page).select_option("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            _pick(page, OTHER)
            del first.checkouts["web-app"]
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_select(page)).to_have_count(0)
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("sign_in.py")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
            assert first.of("getDiff") == ["", "web-app", "web-app", "api-service"]
        finally:
            page.close()
            first.drop()
            second.drop()


def test_an_unreadable_checkout_keeps_the_selector_so_the_operator_can_leave_it():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        sidecar.checkouts["web-app"].failed = True
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            _select(page).select_option("web-app")
            expect(page.get_by_role("heading", name="This diff could not be read")).to_be_visible()
            expect(_select(page)).to_have_value("web-app")
            _select(page).select_option("api-service")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("sign_in.py")
        finally:
            page.close()
            sidecar.drop()


def test_checkout_names_are_text_and_never_markup():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    hostile = "<img src=x onerror=window.__pwned=1>"
    with _run():
        sidecar = _connect(live, checkouts={"api-service": _api(), hostile: _web()})
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(_select(page).locator("option")).to_have_text([hostile, "api-service"])
            expect(_select(page)).to_have_value(hostile)
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            _select(page).select_option("api-service")
            expect(_tab(page, "Diff")).to_contain_text(API_SIZE)
            _select(page).select_option(hostile)
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            assert page.locator("#detail img").count() == 0
            assert page.evaluate("() => window.__pwned") is None
            assert sidecar.of("getDiff")[-1] == hostile
        finally:
            page.close()
            sidecar.drop()


def test_the_selector_has_a_role_and_a_name_works_from_the_keyboard_and_passes_axe():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            select = _select(page)
            assert select.evaluate("(el) => el.tagName") == "SELECT"
            select.focus()
            page.keyboard.press("ArrowDown")
            expect(select).to_have_value("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_SIZE)
            assert not _scan(page)
            _show(page, "Files")
            expect(_select(page)).to_be_visible()
            assert not _scan(page)
        finally:
            page.close()
            sidecar.drop()


def test_j_and_k_with_the_selector_focused_do_not_move_the_run_selection():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    selected = "#runs-list .row.selected"
    with _run(), _run(OTHER):
        first = _connect(live)
        second = _connect(live, OTHER)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(page.locator(selected)).to_have_attribute("data-worker-id", CONTAINER)
            page.locator("#detail-panel").click()
            moved = set()
            for key in ("j", "k"):
                page.keyboard.press(key)
                _settle(page, 200)
                moved.add(page.locator(selected).get_attribute("data-worker-id"))
            assert moved != {CONTAINER}, "j and k move the selection when no control has focus"
            _pick(page, CONTAINER)
            _show(page, "Diff")
            _select(page).focus()
            for key in ("j", "k", "j"):
                page.keyboard.press(key)
                _settle(page, 200)
                expect(page.locator(selected)).to_have_attribute("data-worker-id", CONTAINER)
        finally:
            page.close()
            first.drop()
            second.drop()


def test_the_rail_has_no_files_diff_or_repository_picker_and_the_page_never_asks_for_the_repository_list():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = live.browser.new_page(viewport={"width": 1400, "height": 900})
    repos = _requests(page, "/repos")
    try:
        page.goto(live.url(), wait_until="load")
        page.wait_for_selector("#runs-list .row", timeout=15000)
        modes = page.locator("#activitybar .act-btn").evaluate_all("els => els.map((e) => e.dataset.mode)")
        assert modes == ["runs", "history", "attend", "dispatch", "settings"]
        names = page.locator("#activitybar .act-btn").evaluate_all("els => els.map((e) => e.getAttribute('aria-label'))")
        assert not [name for name in names if re.match(r"^(Files|Diff)\b", name)]
        for gone in ("#files-pane", "#diff-pane", "#repo-menu-wrap", "#repo-menu", "#repo-search", ".repo-picker", ".picker-bar", "#files-tree", "#diff-tree"):
            expect(page.locator(gone)).to_have_count(0)
        for mode in ("attend", "dispatch", "settings", "runs"):
            page.click(f'.act-btn[data-mode="{mode}"]')
            page.wait_for_function(f"() => document.querySelector('.app').dataset.mode === '{mode}'", timeout=5000)
        assert repos == []
    finally:
        page.close()


def test_a_pane_that_no_longer_exists_lands_on_runs_and_never_on_a_blank_pane():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click('.act-btn[data-mode="settings"]')
        page.evaluate(
            """() => {
              const stale = document.createElement("button");
              stale.className = "act-btn";
              stale.dataset.mode = "files";
              stale.id = "stale-pane";
              document.getElementById("activitybar").appendChild(stale);
            }"""
        )
        page.click("#stale-pane")
        assert page.evaluate("() => document.querySelector('.app').dataset.mode") == "runs"
        expect(page.locator("#runs-pane")).to_be_visible()
        expect(page.locator('.act-btn[data-mode="runs"]')).to_have_attribute("aria-pressed", "true")
    finally:
        page.close()


def test_a_native_run_has_no_route_to_files_or_a_diff_and_the_rail_offers_none():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run("nativebox789", native=True, run_id="native-run"):
        page = _open(live)
        try:
            _pick(page, "nativebox789")
            expect(page.get_by_role("tab", name="Overview")).to_be_visible()
            expect(_tab(page, "Files")).to_have_count(0)
            expect(_tab(page, "Diff")).to_have_count(0)
            expect(_select(page)).to_have_count(0)
            expect(page.locator('.act-btn[data-mode="files"], .act-btn[data-mode="diff"]')).to_have_count(0)
        finally:
            page.close()


def _seed_finished_node(run_id: str) -> None:
    import time

    from groom import store

    now = time.time()

    def span(span_id: str, parent: str, node: str, name: str, attrs: dict, at: float) -> dict:
        return {
            "span_id": span_id, "trace_id": f"trace-{run_id}", "parent_id": parent,
            "run_id": run_id, "workflow": "coder", "repo": "acme", "branch": "main",
            "node": node, "name": name, "run_dir": "", "start_ts": at, "end_ts": at + 60,
            "status": "OK", "attrs": attrs,
        }

    turn = {"backend": "claude", "duration_ms": 60000, "usage.output_tokens": 1000, "total_cost_usd": 1.0}
    store.insert_spans(
        [
            span(f"{run_id}-s0", "", "work", "work", {"workhorse.span_kind": "state", "workhorse.depth": 0}, now - 300),
            span(f"{run_id}-n1", f"{run_id}-s0", "qa-story", "qa-story", {"workhorse.depth": 1}, now - 290),
            span(f"{run_id}-t1", f"{run_id}-n1", "qa-story", "agent_turn", turn, now - 280),
        ]
    )


def test_a_native_run_shows_its_checkout_path_on_overview_before_and_after_its_first_finished_node():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _container_run("nativenew901", native=True, run_id="native-new"):
        page = _open(live)
        try:
            _pick(page, "nativenew901")
            expect(page.get_by_role("tabpanel")).to_contain_text("Figures appear when the first node finishes")
            expect(page.locator("#detail-facts")).to_contain_text("/nonexistent/acme")
            expect(_tab(page, "Files")).to_have_count(0)
            expect(_tab(page, "Diff")).to_have_count(0)
        finally:
            page.close()
    _seed_finished_node("native-done")
    with _container_run("nativedone902", native=True, run_id="native-done"):
        page = _open(live)
        try:
            _pick(page, "nativedone902")
            expect(page.locator("#detail-cost-tile")).to_be_visible()
            expect(page.locator("#detail-facts")).to_contain_text("/nonexistent/acme")
            expect(_tab(page, "Files")).to_have_count(0)
            expect(_tab(page, "Diff")).to_have_count(0)
        finally:
            page.close()


def test_the_diff_sits_on_the_pane_background_without_a_card_border_and_tints_changed_text():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _show(page, "Diff")
            expect(page.locator("#detail-panel .run-file-diff .d2h-ins")).not_to_have_count(0)
            looks = page.evaluate(
                """() => {
                  const css = (selector, property) => getComputedStyle(document.querySelector(selector))[property];
                  return {
                    card: css("#detail-panel .d2h-file-wrapper", "borderTopWidth"),
                    wrapper: css("#detail-panel .run-file-diff .d2h-wrapper", "backgroundColor"),
                    added: css("#detail-panel .d2h-ins .d2h-code-line-ctn", "color"),
                  };
                }"""
            )
            assert looks["card"] == "0px"
            assert looks["wrapper"] == "rgba(0, 0, 0, 0)"
            assert looks["added"] == "rgb(175, 245, 180)"
        finally:
            page.close()
            sidecar.drop()
