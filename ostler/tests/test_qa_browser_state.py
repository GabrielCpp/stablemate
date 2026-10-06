"""What `url`, `stored` and `clipboard` read off the browser, and when each passes."""

from __future__ import annotations

from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
state = load_harness_module("ostler_qa_browser_state")


class _Moving:
    """A page whose address moves through *urls* one read at a time, then stays."""

    def __init__(self, *urls: str) -> None:
        self._urls = list(urls)

    @property
    def url(self) -> str:
        return self._urls.pop(0) if len(self._urls) > 1 else self._urls[0]


def test_url_reads_the_address_without_its_origin() -> None:
    verify = harness.VERIFIERS["url"]
    page = _Moving("http://localhost:5173/fr/guide?tab=2#install")
    assert verify(page, {"equals": "/fr/guide?tab=2#install"}).passed is True
    assert verify(page, {"matches": r"\?tab=2#install$"}).passed is True


def test_url_waits_for_a_screen_that_moves_late() -> None:
    page = _Moving("http://localhost/", "http://localhost/", "http://localhost/fr/guide")
    assert harness.VERIFIERS["url"](page, {"equals": "/fr/guide"}).passed is True


def test_url_fails_on_a_link_that_dropped_its_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "STATE_WAIT_S", 0.0)
    verdict = harness.VERIFIERS["url"](_Moving("http://localhost/fr/guide"), {"equals": "/fr/guide?tab=2"})
    assert verdict.passed is False
    assert verdict.actual == "/fr/guide" and verdict.expected == {"equals": "/fr/guide?tab=2"}


class _Stored:
    """A page that answers a storage read with *values*, and records what it was asked for."""

    def __init__(self, values: list[str]) -> None:
        self.values = values
        self.asked: list[Any] = []

    def evaluate(self, _script: str, location: Any = None) -> list[str]:
        self.asked.append(location)
        return self.values


_DRAFTS = ['{"pageId":"p1","locale":"fr"}', '{"pageId":"p1","locale":"en"}']


def test_stored_counts_the_records_that_carry_the_text() -> None:
    verify = harness.VERIFIERS["stored"]
    page = _Stored(_DRAFTS)
    assert verify(page, {"records": "docs-drafts/drafts", "text": '"pageId":"p1"', "count": 2}).passed is True
    assert page.asked[-1] == {"key": None, "database": "docs-drafts", "store": "drafts"}
    assert verify(page, {"records": "docs-drafts/drafts", "text": '"locale":"de"'}).passed is False


def test_stored_with_a_count_of_zero_claims_the_page_kept_nothing() -> None:
    verify = harness.VERIFIERS["stored"]
    assert verify(_Stored([]), {"key": "theme", "count": 0}).passed is True
    assert verify(_Stored(["dark"]), {"key": "theme", "count": 0}).passed is False


def test_stored_refuses_records_that_name_no_store() -> None:
    with pytest.raises(ValueError, match="<database>/<store>"):
        harness.VERIFIERS["stored"](_Stored([]), {"records": "docs-drafts"})


def test_clipboard_judges_the_last_text_the_page_copied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "STATE_WAIT_S", 0.0)
    verify = harness.VERIFIERS["clipboard"]
    assert verify(["/fr/guide?tab=2"], {"text": "tab=2"}).passed is True
    assert verify(["/fr/guide?tab=2", "/fr/guide"], {"text": "tab=2"}).passed is False
    nothing = verify([], {"matches": "."})
    assert nothing.passed is False and nothing.actual is None


_PAGE = """<!doctype html><title>t</title><script>
async function draft() {
  const db = await new Promise((ok) => {
    const opening = indexedDB.open("docs-drafts", 2);
    opening.onupgradeneeded = () => opening.result.createObjectStore("drafts", {keyPath: ["pageId", "locale"]});
    opening.onsuccess = () => ok(opening.result);
  });
  const tx = db.transaction("drafts", "readwrite");
  tx.objectStore("drafts").put({pageId: "p1", locale: "fr"});
  tx.objectStore("drafts").put({pageId: "p1", locale: "en"});
  await new Promise((ok) => { tx.oncomplete = ok; });
  db.close();
}
</script>"""


def test_the_readers_see_what_a_real_page_stored_and_copied() -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
            context.add_init_script(state.CLIPBOARD_JS)
            page = context.new_page()
            page.route("http://localhost:9/**", lambda route: route.fulfill(body=_PAGE, content_type="text/html"))
            page.goto("http://localhost:9/fr/guide?tab=2#install")
            verify = harness.VERIFIERS
            assert verify["stored"](page, {"records": "docs-drafts/drafts", "count": 0}).passed is True
            page.evaluate("draft()")
            page.evaluate("localStorage.setItem('theme', 'dark')")
            page.evaluate("navigator.clipboard.writeText(location.pathname + location.search)")
            assert verify["url"](page, {"equals": "/fr/guide?tab=2#install"}).passed is True
            assert verify["stored"](page, {"records": "docs-drafts/drafts", "text": "fr", "count": 1}).passed is True
            assert verify["stored"](page, {"key": "theme", "text": "dark"}).passed is True
            assert verify["clipboard"](page, {"text": "/fr/guide?tab=2"}).passed is True
        finally:
            browser.close()
