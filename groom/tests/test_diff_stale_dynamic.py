"""The Diff and Files tabs of a container run whose sidecar dropped, measured on the page the operator gets against a real sidecar socket."""
from __future__ import annotations

import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from _page_settle import advance_until, settle
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _workspace,
    teardown_module,  # noqa: F401
)
from test_diff_since_branch_dynamic import (
    CONTAINER,
    OTHER,
    _connect,
    _pick,
    _run,
    _since,
    _since_view,
    _uncommitted,
    _view,
)
from test_diff_tab_dynamic import (
    DIFF,
    SIZE,
    _dirty_repo,
    _git,
    _open_diff,
    _patch,
    _push_exited,
    _RealSidecar,
    _tab,
    _wait_for,
)

STRIP = "#detail-stale-strip"
STALE = "#detail-diff-stale"
CLOCK = re.compile(r"This is the diff from \d\d:\d\d:\d\d\.")
LONG = _patch("services/api/long.py", [], [f"line {n}" for n in range(400)])


def _drop_and_wait(sidecar) -> None:
    from groom import sidecar_hub

    sidecar.drop()
    _wait_for(lambda: sidecar_hub.get(sidecar.container) is None, "the hub to forget the sidecar")


@contextmanager
def _volume_run(volume: Path):
    from unittest.mock import patch

    from groom import app as app_module
    from groom import localfs, state

    with _run(), patch.object(app_module.docker_io, "read_diff", localfs.read_diff), patch.object(app_module.docker_io, "read_tree", localfs.read_tree):
        state.WORKFLOWS[CONTAINER].workspace_volume = str(volume)
        yield


def _replies(page, route: str) -> list:
    seen: list = []
    page.on("response", lambda response: seen.append(response) if f"/{route}/" in response.url else None)
    return seen


def _diff_reads(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if "/diff/" in request.url else None)
    return seen


def _retry(page):
    return page.get_by_role("button", name="Retry now")


def test_a_drop_keeps_the_diff_tab_marked_stale_in_words_with_a_strip_naming_the_read_time():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            _drop_and_wait(sidecar)
            expect(page.locator(STALE)).to_have_text("stale", timeout=30000)
            expect(_tab(page, "Diff")).to_have_attribute("aria-label", "Diff, stale")
            expect(_tab(page, "Diff")).not_to_contain_text(SIZE)
            expect(page.get_by_role("tab", selected=True)).to_have_text(re.compile(r"^Diff"))
            strip = page.locator(STRIP)
            expect(strip).to_contain_text(re.compile(r"The sidecar stopped answering \d+s ago\."))
            expect(strip).to_contain_text("The run may still be working.")
            expect(strip).to_contain_text(CLOCK)
            expect(page.locator("#detail-panel .fd-split.stale")).to_be_visible()
            expect(page.locator("#run-sidecar-chip")).to_have_text("docker")
        finally:
            page.close()


def test_the_strip_counts_how_long_ago_on_the_shared_clock_without_a_live_region():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _drop_and_wait(sidecar)
            strip = page.locator(STRIP)
            expect(strip).to_be_visible(timeout=30000)
            first = strip.inner_text()
            expect(strip).not_to_have_text(first)
            assert strip.get_attribute("aria-live") is None
            assert page.locator(f"{STRIP} [aria-live]").count() == 0
        finally:
            page.close()


def test_the_diff_selected_file_and_scroll_stay_as_they_were():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live, uncommitted=_uncommitted(DIFF + LONG))
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            long = page.get_by_role("button", name=re.compile("long.py"))
            long.click()
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("line 399")
            page.evaluate("document.querySelector('#detail-panel .fd-view').scrollTop = 300")
            before = page.evaluate("document.querySelector('#detail-panel .fd-view').scrollTop")
            assert before > 100
            tree = page.locator("#detail-panel .fd-tree").inner_text()
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            expect(long).to_have_attribute("aria-current", "true")
            assert page.evaluate("document.querySelector('#detail-panel .fd-view').scrollTop") == before
            assert page.locator("#detail-panel .fd-tree").inner_text() == tree
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("line 399")
        finally:
            page.close()


def test_a_retry_replaces_the_refresh_control_while_the_mark_shows_and_works_from_the_keyboard():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.get_by_role("button", name="Read the diff again")).to_be_visible()
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            expect(page.get_by_role("button", name="Read the diff again")).to_have_count(0)
            expect(page.locator(".dtabs .right")).not_to_contain_text("read ")
            expect(_retry(page)).to_have_count(1)
            _retry(page).focus()
            page.keyboard.press("Enter")
            expect(page.locator(f"{STRIP} b")).to_have_text("The sidecar is still not answering.")
        finally:
            page.close()


def test_a_retry_that_finds_no_sidecar_leaves_the_diff_and_its_time_alone_and_says_so():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        seen = _diff_reads(page)
        try:
            _pick(page)
            _open_diff(page)
            page.get_by_role("button", name=re.compile("lockout.py")).click()
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_contain_text(CLOCK, timeout=30000)
            clock = CLOCK.search(page.locator(STRIP).inner_text())
            assert clock is not None
            tree = page.locator("#detail-panel .fd-tree").inner_text()
            reads = len(seen)
            _retry(page).click()
            expect(page.locator(f"{STRIP} b")).to_have_text("The sidecar is still not answering.")
            assert len(seen) == reads + 1
            text = page.locator(STRIP).inner_text()
            assert clock.group(0) in text
            assert re.search(r"It stopped answering \d+s ago\.", text)
            assert page.locator("#detail-panel .fd-tree").inner_text() == tree
            expect(page.locator("#detail-panel .fd-view")).to_contain_text("lock one")
            expect(page.locator(STALE)).to_have_text("stale")
            expect(page.locator("#detail-panel [role=status]")).to_contain_text("still not answering")
        finally:
            page.close()


def test_a_reconnect_reads_again_clears_the_mark_and_keeps_the_selected_file():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            lockout = page.get_by_role("button", name=re.compile("lockout.py"))
            lockout.click()
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            again = _connect(live, uncommitted=_uncommitted(DIFF + _patch("services/api/extra.py", [], ["x"])))
            try:
                expect(page.locator(STRIP)).to_have_count(0, timeout=30000)
                expect(page.locator(STALE)).to_have_count(0)
                expect(_tab(page, "Diff")).to_contain_text("+6 −2")
                expect(lockout).to_have_attribute("aria-current", "true")
                expect(page.get_by_role("button", name=re.compile("extra.py"))).to_be_visible()
                expect(page.get_by_role("button", name="Read the diff again")).to_be_visible()
                assert len(again.reads("")) == 1
                expect(page.locator("#run-sidecar-chip")).to_have_text("docker · sidecar")
            finally:
                again.drop()
        finally:
            page.close()


def test_the_kept_diff_is_per_checkout_and_per_view_and_a_view_not_read_says_so():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    replies = {
        ("api-service", ""): _uncommitted(),
        ("api-service", "branch"): _since(),
        ("web-app", ""): _uncommitted(_patch("src/app.tsx", ["gone x", "gone y"], ["new z"])),
        ("web-app", "branch"): _since(_patch("src/app.tsx", ["gone x"], ["new z", "new y"]), base="b" * 40, branch="trunk", ref="trunk"),
    }
    with _run():
        sidecar = _connect(live, replies=replies, names=["api-service", "web-app"])
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            page.get_by_label("Checkout").select_option("web-app")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("app.tsx")
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("app.tsx")
            _since_view(page)
            unread = page.locator("#detail-diff-unread")
            expect(unread).to_contain_text("This view was not read before the sidecar stopped answering")
            expect(unread).to_contain_text("The run may still be working.")
            expect(_retry(page)).to_have_count(1)
            _view(page, "Uncommitted").click()
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("app.tsx")
            expect(unread).to_have_count(0)
            page.get_by_label("Checkout").select_option("api-service")
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("sign_in.py")
            expect(page.locator(STRIP)).to_be_visible()
            _since_view(page)
            expect(unread).to_have_count(1)
            _view(page, "Uncommitted").click()
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("sign_in.py")
        finally:
            page.close()


def test_a_run_selected_here_whose_sidecar_drops_before_a_diff_was_read_says_none_was_read_and_offers_a_retry():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        sidecar.hold.clear()
        page = _open(live)
        try:
            _pick(page)
            _wait_for(lambda: len(sidecar.reads("")) == 1, "the first read to reach the sidecar")
            _drop_and_wait(sidecar)
            sidecar.hold.set()
            _tab(page, "Diff").click()
            unread = page.locator("#detail-diff-unread")
            expect(unread).to_contain_text("The sidecar stopped answering before a diff was read", timeout=30000)
            expect(unread).to_contain_text("The run may still be working.")
            expect(page.locator(STRIP)).to_have_count(0)
            expect(_retry(page)).to_have_count(1)
            again = _connect(live)
            try:
                expect(page.locator("#detail-panel .fd-split")).to_be_visible(timeout=30000)
                expect(unread).to_have_count(0)
            finally:
                again.drop()
        finally:
            page.close()


def test_a_run_first_selected_after_the_drop_shows_no_files_or_diff_tab():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        _drop_and_wait(sidecar)
        page = _open(live)
        try:
            _pick(page)
            expect(_tab(page, "Files")).to_have_count(0)
            expect(_tab(page, "Diff")).to_have_count(0)
            expect(page.get_by_role("tab", selected=True)).to_have_text("Overview")
            expect(page.locator("#run-sidecar-chip")).to_have_count(0)
        finally:
            page.close()


def test_files_says_the_sidecar_stopped_answering_offers_a_retry_and_clears_on_reconnect():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _tab(page, "Files").click()
            _drop_and_wait(sidecar)
            stale = page.locator("#detail-files-stale")
            expect(stale).to_contain_text(re.compile(r"The sidecar stopped answering \d+s ago"), timeout=30000)
            expect(stale).to_contain_text("The run may still be working.")
            _retry(page).click()
            expect(stale).to_contain_text("The sidecar is still not answering.")
            expect(page.get_by_role("tab", selected=True)).to_have_text("Files")
            again = _connect(live)
            try:
                expect(stale).to_have_count(0, timeout=30000)
                expect(page.get_by_role("tab", selected=True)).to_have_text("Files")
            finally:
                again.drop()
        finally:
            page.close()


def test_selecting_another_run_and_coming_back_shows_the_same_kept_diff_and_mark():
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
            page.get_by_role("button", name=re.compile("lockout.py")).click()
            _drop_and_wait(first)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            kept = CLOCK.search(page.locator(STRIP).inner_text())
            assert kept is not None
            _pick(page, OTHER)
            expect(page.locator(STALE)).to_have_count(0)
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            _pick(page, CONTAINER)
            expect(page.locator(STALE)).to_have_text("stale")
            _open_diff(page)
            expect(page.locator(STRIP)).to_contain_text(kept.group(0))
            expect(page.get_by_role("button", name=re.compile("lockout.py"))).to_have_attribute("aria-current", "true")
        finally:
            page.close()
            second.drop()


def test_the_tabs_go_and_overview_shows_when_the_run_ends_during_the_mark():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            _push_exited(live, CONTAINER)
            expect(_tab(page, "Diff")).to_have_count(0, timeout=30000)
            expect(_tab(page, "Files")).to_have_count(0)
            expect(page.get_by_role("tab", selected=True)).to_have_text("Overview")
            expect(page.locator(STRIP)).to_have_count(0)
        finally:
            page.close()


def test_a_reload_during_the_drop_shows_no_tabs():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            page.reload(wait_until="load")
            page.wait_for_selector("#runs-list .row", timeout=30000)
            _pick(page)
            expect(_tab(page, "Diff")).to_have_count(0)
            expect(_tab(page, "Files")).to_have_count(0)
            expect(page.locator(STRIP)).to_have_count(0)
        finally:
            page.close()


def test_a_volume_reply_never_replaces_the_kept_diff():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            before = page.locator("#detail-panel .fd-tree").inner_text()
            view = "docs/README.md"
            for _ in range(2):
                _retry(page).click()
                expect(page.locator(f"{STRIP} b")).to_have_text("The sidecar is still not answering.")
            assert page.locator("#detail-panel .fd-tree").inner_text() == before
            expect(page.locator("#detail-panel .fd-view")).to_contain_text(view)
        finally:
            page.close()


def test_a_volume_reply_carrying_a_real_diff_never_replaces_the_kept_diff():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with tempfile.TemporaryDirectory() as tmp, _volume_run(_workspace(Path(tmp))):
        sidecar = _connect(live, names=["acme"])
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            tree = page.locator("#detail-panel .fd-tree")
            expect(tree).to_contain_text("lockout.py")
            lockout = page.get_by_role("button", name=re.compile("lockout.py"))
            lockout.click()
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=5000)
            found = CLOCK.search(page.locator(STRIP).inner_text())
            assert found is not None
            clock = found.group(0)
            before = tree.inner_text()
            replies = _replies(page, "diff")
            _retry(page).click()
            expect(page.locator(f"{STRIP} b")).to_have_text("The sidecar is still not answering.")
            body = replies[-1].json()
            assert body["served"] == "volume"
            assert "src/app.py" in body["diff"]
            assert tree.inner_text() == before
            assert "app.py" not in before
            expect(lockout).to_have_attribute("aria-current", "true")
            expect(page.locator(STRIP)).to_contain_text(clock)
            expect(page.locator(STALE)).to_have_text("stale")
        finally:
            page.close()


def test_a_volume_reply_carrying_a_real_tree_never_replaces_the_stale_files_notice():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    paths = ["services/api/lockout.py", "services/api/kept.py"]
    with tempfile.TemporaryDirectory() as tmp, _volume_run(_workspace(Path(tmp))):
        sidecar = _connect(live, names=["acme"])
        sidecar.tree = paths
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _tab(page, "Files").click()
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("kept.py")
            _drop_and_wait(sidecar)
            stale = page.locator("#detail-files-stale")
            expect(stale).to_be_visible(timeout=5000)
            replies = _replies(page, "files")
            _retry(page).click()
            expect(stale).to_contain_text("The sidecar is still not answering.")
            body = replies[-1].json()
            assert body["served"] == "volume"
            assert "src/app.py" in body["paths"]
            expect(page.locator("#detail-panel .fd-tree")).to_have_count(0)
            expect(page.locator("#detail-panel")).not_to_contain_text("app.py")
            expect(page.get_by_role("tab", selected=True)).to_have_text("Files")
        finally:
            page.close()


def test_the_strip_and_marks_pass_the_accessibility_scan():
    from test_a11y_dynamic import _scan

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _drop_and_wait(sidecar)
            page.wait_for_selector(STRIP, timeout=30000)
            assert _scan(page) == []
            _tab(page, "Files").click()
            page.wait_for_selector("#detail-files-stale", timeout=30000)
            assert [found for found in _scan(page) if found["id"] != "heading-order"] == []
        finally:
            page.close()


def test_the_kept_diff_after_a_real_drop_is_the_diff_git_reports_for_the_checkout():
    from playwright.sync_api import expect

    from groom import sidecar_hub

    live = _live()
    assert live is not None, _UNAVAILABLE
    with tempfile.TemporaryDirectory() as tmp, _run():
        repo = _dirty_repo(Path(tmp))
        expected = _git(repo, "diff", "HEAD")
        sidecar = _RealSidecar(live, CONTAINER, Path(tmp))
        _wait_for(lambda: sidecar_hub.get(CONTAINER) is not None, "the sidecar to register")
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(page.locator("#detail-panel .fd-tree")).to_contain_text("alpha.txt")
            _drop_and_wait(sidecar)
            expect(page.locator(STRIP)).to_be_visible(timeout=30000)
            expect(page.locator(STALE)).to_have_text("stale")
            for line in _git(repo, "diff", "--numstat", "HEAD").splitlines():
                added, removed, name = line.split("\t")
                row = page.get_by_role("button", name=re.compile(re.escape(name)))
                expect(row).to_contain_text(f"+{added} −{removed}")
            for block in expected.split("diff --git ")[1:]:
                name = block.split(" b/")[0].removeprefix("a/")
                page.get_by_role("button", name=re.compile(re.escape(name))).click()
                for line in block.splitlines():
                    if line[:1] in "+-" and line[:3] not in ("+++", "---"):
                        expect(page.locator("#detail-panel .fd-view")).to_contain_text(line[1:])
        finally:
            page.close()


def _push_workspace(sidecar) -> None:
    sidecar.socket.send(json.dumps({"type": "workspace"}))


def test_a_workspace_frame_refreshes_the_open_diff_within_a_second_and_a_half_with_no_retry():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            expect(_tab(page, "Diff")).to_contain_text(SIZE)
            _wait_for(lambda: len(sidecar.reads()) >= 1, "the first diff read")
            settle(page)
            seen = _diff_reads(page)
            before = len(sidecar.reads())
            page.clock.install()
            _push_workspace(sidecar)
            advance_until(page, lambda: len(seen) == 1, "the diff refresh request", 1500)
            _wait_for(lambda: len(sidecar.reads()) == before + 1, "one more diff read")
            page.clock.run_for(1500)
            settle(page)
            assert len(sidecar.reads()) == before + 1
            assert len(seen) == 1
        finally:
            page.close()
            sidecar.drop()


def test_a_workspace_change_seen_while_files_is_open_reads_the_diff_again_when_diff_opens():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run():
        sidecar = _connect(live)
        page = _open(live)
        try:
            _pick(page)
            _open_diff(page)
            _wait_for(lambda: len(sidecar.reads()) >= 1, "the first diff read")
            files_seen: list[str] = []
            page.on("request", lambda request: files_seen.append(request.url) if "/files/" in request.url else None)
            _tab(page, "Files").click()
            expect(page.get_by_role("tabpanel", name="Files")).to_contain_text("This checkout has no files")
            settle(page)
            before = len(sidecar.reads())
            opened = len(files_seen)
            page.clock.install()
            _push_workspace(sidecar)
            advance_until(page, lambda: len(files_seen) > opened, "the files refresh request", 3000)
            settle(page)
            assert len(sidecar.reads()) == before
            _tab(page, "Diff").click()
            _wait_for(lambda: len(sidecar.reads()) == before + 1, "a diff read on opening Diff")
        finally:
            page.close()
            sidecar.drop()
