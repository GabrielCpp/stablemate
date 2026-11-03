"""The Diff tab's switch between the uncommitted change and the change since the branch started, measured on the page the operator gets against a real sidecar socket."""
from __future__ import annotations

import json
import re
import threading

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_diff_tab_dynamic import (
    DIFF,
    LOCKOUT,
    SIGN_IN,
    SIZE,
    _container_run,
    _open_diff,
    _patch,
    _pick as _pick_run,
    _settle,
    _tab,
    _wait_for,
)
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

CONTAINER = "branchbox123"
OTHER = "branchbox456"
START = "4f1c9ab0d3e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9"
CODES = _patch("services/api/codes.py", ["old one", "old two"], ["new one", "new two", "new three", "new four"])
WHOLE = DIFF + CODES
WHOLE_SIZE = "+9 −4"
WEB_WHOLE = _patch("src/app.tsx", ["gone x"], ["new z", "new y"])
WEB_WHOLE_SIZE = "+2 −1"


def _uncommitted(diff: str = DIFF, untracked: tuple[str, ...] = (), failed: bool = False) -> dict:
    return {"diff": diff, "untracked": list(untracked), "failed": failed}


def _since(diff: str = WHOLE, untracked: tuple[str, ...] = (), *, failed: bool = False, base: str = START, ref: str = "origin/main", branch: str = "main", reason: str = "") -> dict:
    return {**_uncommitted(diff, untracked, failed), "base": base, "base_ref": ref, "base_branch": branch, "base_reason": reason}


class _Sidecar:
    """A sidecar over a real socket that answers getDiff per checkout and view, and records the parameters of every read."""

    def __init__(self, live, container: str, replies: dict[tuple[str, str], dict], names: list[str] | None = None) -> None:
        self.container = container
        self.replies = replies
        self.names = names or []
        self.lock = threading.Lock()
        self.params: list[dict] = []
        self.fail = False
        self.hold = threading.Event()
        self.hold.set()
        self.socket = connect(f"ws://127.0.0.1:{live.port}/sidecar")
        hello = {
            "type": "hello",
            "identity": {"container_id": container, "name": "coder-acme", "run_id": f"run-{container}", "workflow": "coder"},
            "snapshot": {"current_node": "build", "terminal": "", "gates": []},
        }
        self.socket.send(json.dumps(hello))
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def reads(self, view: str = "") -> list[dict]:
        with self.lock:
            return [p for p in self.params if p.get("view", "") == view]

    def _answer(self, message: dict) -> dict:
        params = message["params"]
        if message["method"] != "getDiff":
            return {"ok": True, "data": {"paths": [], "failed": False, "repos": self.names}}
        with self.lock:
            self.params.append(dict(params))
        self.hold.wait(10)
        if self.fail:
            return {"ok": False, "error": "git blew up"}
        repo = params.get("repo", "") or (self.names[0] if self.names else "")
        reply = self.replies.get((repo, params.get("view", "")))
        if reply is None:
            reply = self.replies[("", params.get("view", ""))]
        extra = {"repos": self.names} if self.names else {}
        return {"ok": True, "data": {**reply, **extra}}

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


def _connect(live, container: str = CONTAINER, *, uncommitted: dict | None = None, since: dict | None = None, names: list[str] | None = None, replies: dict | None = None) -> _Sidecar:
    from groom import sidecar_hub

    table = replies if replies is not None else {
        ("", ""): uncommitted if uncommitted is not None else _uncommitted(),
        ("", "branch"): since if since is not None else _since(),
    }
    sidecar = _Sidecar(live, container, table, names)
    _wait_for(lambda: sidecar_hub.get(container) is not None, "the sidecar to register")
    return sidecar


def _pick(page, container: str = CONTAINER) -> None:
    _pick_run(page, container)


def _run(container: str = CONTAINER):
    return _container_run(container, run_id=f"run-{container}")


def _switch(page):
    return page.get_by_role("group", name="Diff view")


def _view(page, name: str):
    return _switch(page).get_by_role("button", name=name)


def _since_view(page) -> None:
    _view(page, "Since branch start").click()


def _panel(page):
    return page.locator("#detail-panel")


def test_the_diff_tab_opens_on_uncommitted_with_a_switch_that_sends_the_sidecar_no_new_parameter():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            _open_diff(page)
            expect(_view(page, "Uncommitted")).to_have_attribute("aria-pressed", "true")
            expect(_view(page, "Since branch start")).to_have_attribute("aria-pressed", "false")
            expect(page.locator("#detail-diff-file-head")).to_contain_text("uncommitted")
            assert sidecar.params == [{"repo": ""}]
        finally:
            page.close()
            sidecar.drop()


def test_the_switch_is_on_the_diff_tab_only():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            expect(_switch(page)).to_have_count(0)
            _open_diff(page)
            expect(_switch(page)).to_have_count(1)
            page.get_by_role("tab", name="Files").click()
            expect(_switch(page)).to_have_count(0)
        finally:
            page.close()
            sidecar.drop()


def test_since_branch_start_shows_the_whole_change_names_its_base_and_the_size_and_tree_follow():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel .fd-tree .tree-file")).to_have_count(3)
            _since_view(page)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            expect(_tab(page, "Diff")).to_have_accessible_name("Diff, 9 lines added, 4 lines removed")
            expect(page.locator("#detail-panel .fd-tree .tree-file")).to_have_count(4)
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("codes.py")
            head = page.locator("#detail-diff-file-head")
            expect(head).to_contain_text("since 4f1c9ab on main")
            expect(head.locator(".diff-scope")).to_have_attribute("title", f"against {START} from origin/main")
            assert sidecar.reads("branch") == [{"repo": "", "view": "branch"}]
            _view(page, "Uncommitted").click()
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            expect(page.locator("#detail-panel .fd-tree .tree-file")).to_have_count(3)
            expect(page.locator("#detail-diff-file-head")).to_contain_text("uncommitted")
        finally:
            page.close()
            sidecar.drop()


def test_untracked_files_sit_in_their_own_group_in_this_view_and_are_not_counted():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, since=_since(untracked=("notes.md",)))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            group = page.locator("#detail-panel .fd-tree .tree-dir", has_text="Not tracked by git yet")
            expect(group.locator(".tree-file")).to_have_text([re.compile("notes.md")])
            expect(group.locator(".tree-file .fstat")).to_have_count(0)
            group.get_by_role("button", name=re.compile("notes.md")).click()
            expect(page.locator("#detail-panel .fd-view")).to_have_text("notes.md has no diff because git does not track it yet.")
        finally:
            page.close()
            sidecar.drop()


def test_a_branch_with_no_change_says_so_and_the_tab_shows_no_count():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, since=_since(""))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_panel(page)).to_contain_text("This branch has no change since it started at 4f1c9ab on main.")
            expect(_tab(page, "Diff")).to_have_text("Diff")
            expect(_panel(page).get_by_role("alert")).to_have_count(0)
        finally:
            page.close()
            sidecar.drop()


def test_a_branch_with_only_untracked_files_lists_them_and_says_no_tracked_file_changed_since_the_start():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, since=_since("", ("notes.md",)))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_panel(page).locator(".fd-tree .tree-file")).to_have_text([re.compile("notes.md")])
            expect(_panel(page).locator(".fd-view")).to_contain_text("No tracked file has changed since this branch started at 4f1c9ab on main.")
            expect(_tab(page, "Diff")).to_have_text("Diff")
        finally:
            page.close()
            sidecar.drop()


def test_while_the_view_is_read_the_tab_says_so_and_the_state_clears_when_it_arrives():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            sidecar.hold.clear()
            _since_view(page)
            loading = _panel(page).get_by_role("status")
            expect(loading).to_have_text("Reading the change since the branch started…")
            expect(loading).to_have_attribute("aria-busy", "true")
            expect(_tab(page, "Diff")).to_have_text("Diff")
            sidecar.hold.set()
            expect(_panel(page).get_by_role("status")).to_have_count(0)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
        finally:
            sidecar.hold.set()
            page.close()
            sidecar.drop()


def test_a_view_that_cannot_be_read_says_so_offers_a_retry_and_clears_when_a_read_succeeds():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, since=_since("", failed=True))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            alert = _panel(page).get_by_role("alert")
            expect(alert).to_contain_text("This view could not be read")
            expect(alert).to_contain_text("This does not mean there is no change.")
            expect(_panel(page)).not_to_contain_text("no change since")
            expect(_tab(page, "Diff")).to_have_text("Diff")
            sidecar.replies[("", "branch")] = _since()
            alert.get_by_role("button", name="Retry now").click()
            expect(_panel(page).get_by_role("alert")).to_have_count(0)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            assert len(sidecar.reads("branch")) == 2
        finally:
            page.close()
            sidecar.drop()


def test_a_read_the_sidecar_errors_on_is_an_unreadable_view_never_an_empty_one():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            sidecar.fail = True
            _since_view(page)
            expect(_panel(page).get_by_role("alert")).to_contain_text("This view could not be read")
            expect(_panel(page)).not_to_contain_text("no change since")
        finally:
            page.close()
            sidecar.drop()


def test_a_checkout_whose_branch_start_cannot_be_found_says_so_keeps_uncommitted_and_clears_when_found():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    missing = _since("", base="", ref="", branch="", reason="not-found")
    with _run():
        sidecar = _connect(live, since=missing)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            notice = _panel(page).get_by_role("status")
            expect(notice).to_contain_text("Where this branch started could not be found")
            expect(notice).to_contain_text("The checkout has no default branch to compare with. Uncommitted still works.")
            expect(_tab(page, "Diff")).to_have_text("Diff")
            expect(page.locator("#detail-diff-read")).to_have_count(0)
            expect(page.get_by_role("button", name="Read the diff again")).to_have_count(0)
            shape = page.evaluate(
                """() => {
                  const box = (el) => el.getBoundingClientRect();
                  const panel = box(document.querySelector("#detail-panel"));
                  const notice = document.querySelector("#detail-diff-branch-missing");
                  return {
                    gap: panel.width - box(notice).width,
                    height: box(notice).height,
                  };
                }"""
            )
            assert shape["gap"] <= 40
            assert shape["height"] < 95
            sidecar.replies[("", "branch")] = _since()
            notice.get_by_role("button", name="Retry now").click()
            expect(_panel(page).get_by_role("status")).to_have_count(0)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            _view(page, "Uncommitted").click()
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
        finally:
            page.close()
            sidecar.drop()


def test_a_branch_that_shares_no_history_with_the_default_branch_names_that_branch():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    island = _since("", base="", ref="main", branch="main", reason="not-found")
    with _run():
        sidecar = _connect(live, since=island)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_panel(page).get_by_role("status")).to_contain_text("This branch shares no history with main. Uncommitted still works.")
        finally:
            page.close()
            sidecar.drop()


def test_a_checkout_on_its_default_branch_says_it_has_no_branch_of_its_own():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    default = _since("", base="", ref="main", branch="main", reason="default-branch")
    with _run():
        sidecar = _connect(live, since=default)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_panel(page)).to_contain_text("This checkout is on main, its default branch, so it has no branch of its own to compare.")
            expect(_tab(page, "Diff")).to_have_text("Diff")
            expect(_panel(page).get_by_role("alert")).to_have_count(0)
            _view(page, "Uncommitted").click()
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
        finally:
            page.close()
            sidecar.drop()


def test_a_sidecar_too_old_to_report_a_branch_start_says_so_and_never_shows_its_uncommitted_diff_as_the_view():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, since=_uncommitted())
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_panel(page)).to_contain_text("This view needs a newer sidecar. Uncommitted still works.")
            expect(_panel(page).locator(".fd-tree")).to_have_count(0)
            expect(_tab(page, "Diff")).to_have_text("Diff")
            _view(page, "Uncommitted").click()
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            expect(_panel(page).locator(".fd-tree .tree-file")).to_have_count(3)
        finally:
            page.close()
            sidecar.drop()


def test_the_switch_keeps_its_position_when_the_diff_is_refreshed():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            sidecar.replies[("", "branch")] = _since(SIGN_IN + LOCKOUT)
            page.get_by_role("button", name="Read the diff again").click()
            expect(_tab(page, "Diff")).to_contain_text("+5 −1")
            expect(_view(page, "Since branch start")).to_have_attribute("aria-pressed", "true")
            assert len(sidecar.reads("branch")) == 2
            assert len(sidecar.reads("")) == 1
        finally:
            page.close()
            sidecar.drop()


def test_the_switch_keeps_its_position_across_tabs_and_the_view_is_not_read_again():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            for name in ("Files", "Activity", "Overview"):
                page.get_by_role("tab", name=name).click()
            _tab(page, "Diff").click()
            expect(_view(page, "Since branch start")).to_have_attribute("aria-pressed", "true")
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            _settle(page)
            assert len(sidecar.reads("branch")) == 1
            assert len(sidecar.reads("")) == 1
        finally:
            page.close()
            sidecar.drop()


def test_the_switch_keeps_its_position_when_another_checkout_is_selected():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    replies = {
        ("api-service", ""): _uncommitted(),
        ("api-service", "branch"): _since(),
        ("web-app", ""): _uncommitted(_patch("src/app.tsx", ["gone x", "gone y"], ["new z"])),
        ("web-app", "branch"): _since(WEB_WHOLE, base="b" * 40, branch="trunk", ref="trunk"),
    }
    with _run():
        sidecar = _connect(live, replies=replies, names=["api-service", "web-app"])
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            page.get_by_label("Checkout").select_option("web-app")
            expect(_tab(page, "Diff")).to_contain_text(WEB_WHOLE_SIZE)
            expect(_view(page, "Since branch start")).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#detail-diff-file-head")).to_contain_text("since bbbbbbb on trunk")
            assert sidecar.reads("branch")[-1] == {"repo": "web-app", "view": "branch"}
        finally:
            page.close()
            sidecar.drop()


def test_selecting_another_run_and_coming_back_keeps_each_runs_own_position():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run(), _run(OTHER):
        first = _connect(live)
        second = _connect(live, OTHER)
        page = _open(live)
        try:
            _pick(page, CONTAINER)
            _open_diff(page)
            _since_view(page)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            _pick(page, OTHER)
            _open_diff(page)
            expect(_view(page, "Uncommitted")).to_have_attribute("aria-pressed", "true")
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            _pick(page, CONTAINER)
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            _open_diff(page)
            expect(_view(page, "Since branch start")).to_have_attribute("aria-pressed", "true")
            assert first.reads("branch") == [{"repo": "", "view": "branch"}] * 2
            assert first.reads("") == [{"repo": ""}]
            assert second.reads("branch") == []
        finally:
            page.close()
            first.drop()
            second.drop()


def test_the_switch_has_a_role_a_name_keyboard_operation_and_shows_its_position_by_more_than_color():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, since=_since(untracked=("scratch.py",)))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(_switch(page)).to_have_count(1)
            buttons = _switch(page).get_by_role("button")
            expect(buttons).to_have_text(["Uncommitted", "Since branch start"])
            _view(page, "Uncommitted").focus()
            page.keyboard.press("Tab")
            expect(_view(page, "Since branch start")).to_be_focused()
            page.keyboard.press("Enter")
            expect(_view(page, "Since branch start")).to_have_attribute("aria-pressed", "true")
            expect(_tab(page, "Diff")).to_contain_text(WHOLE_SIZE)
            _view(page, "Uncommitted").focus()
            page.keyboard.press("Space")
            expect(_view(page, "Uncommitted")).to_have_attribute("aria-pressed", "true")
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            marks = page.evaluate(
                """() => [...document.querySelectorAll('[aria-label="Diff view"] button')].map((b) => {
                  const s = getComputedStyle(b);
                  return [b.getAttribute('aria-pressed'), s.fontWeight, s.boxShadow];
                })"""
            )
            pressed = next(m for m in marks if m[0] == "true")
            plain = next(m for m in marks if m[0] == "false")
            assert (pressed[1], pressed[2]) != (plain[1], plain[2])
            assert pressed[1] != plain[1] or "inset" in pressed[2]
            assert plain[2] == "none"
            assert not _scan(page)
        finally:
            page.close()
            sidecar.drop()



def test_a_removed_line_paired_with_an_added_one_is_as_red_as_a_removed_line_alone_with_no_inner_highlight():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    paired = _patch("services/api/pair.py", ["a2"], ["A2"])
    with _run():
        sidecar = _connect(live, since=_since(paired))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _since_view(page)
            expect(page.locator("#detail-panel .run-file-diff .d2h-change")).not_to_have_count(0)
            looks = page.evaluate(
                """() => {
                  const css = (el, property) => getComputedStyle(el)[property];
                  const rows = [...document.querySelectorAll("#detail-panel .run-file-diff tr")].filter((tr) => tr.querySelector(".d2h-change"));
                  const out = {};
                  for (const tr of rows) {
                    const text = tr.textContent;
                    const kind = text.includes("a2") ? "removed" : "added";
                    const number = tr.querySelector(".d2h-code-linenumber");
                    const line = tr.querySelector("td.d2h-change:not(.d2h-code-linenumber)");
                    const inner = tr.querySelector(".d2h-code-line-ctn del, .d2h-code-line-ctn ins");
                    if (!line) continue;
                    out[kind] = {
                      line: css(line, "backgroundColor"),
                      number: css(number, "backgroundColor"),
                      inner: inner ? css(inner, "backgroundColor") : "none",
                    };
                  }
                  return out;
                }"""
            )
            assert looks["removed"]["line"] == "rgba(248, 81, 73, 0.13)"
            assert looks["removed"]["number"] == "rgba(248, 81, 73, 0.13)"
            assert looks["added"]["line"] == "rgba(46, 160, 67, 0.14)"
            assert looks["added"]["number"] == "rgba(46, 160, 67, 0.14)"
            assert looks["removed"]["inner"] in ("none", "rgba(0, 0, 0, 0)")
            assert looks["added"]["inner"] in ("none", "rgba(0, 0, 0, 0)")
        finally:
            page.close()
            sidecar.drop()
