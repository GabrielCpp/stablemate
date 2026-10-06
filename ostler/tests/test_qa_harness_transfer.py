"""What a page's own paste and drop handlers receive when a scenario performs those triggers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

transfer = load_harness_module("ostler_qa_transfer")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = """
<div id="body" contenteditable="true"></div>
<div id="zone">drop here</div>
<script>
  window.got = {};
  document.getElementById("body").addEventListener("paste", (event) => {
    event.preventDefault();
    window.got.html = event.clipboardData.getData("text/html");
    window.got.text = event.clipboardData.getData("text/plain");
  });
  const zone = document.getElementById("zone");
  zone.addEventListener("dragover", (event) => event.preventDefault());
  zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    const [file] = event.dataTransfer.files;
    window.got.file = {name: file.name, type: file.type, text: await file.text()};
  });
</script>
"""


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium to drive: {exc}")
        yield launched
        launched.close()


@pytest.fixture
def page(browser: Any) -> Iterator[Any]:
    opened = browser.new_page()
    opened.set_content(_PAGE)
    yield opened
    opened.close()


def test_a_paste_hands_the_page_the_clipboard_types_it_names(page: Any) -> None:
    transfer.paste(page.locator("#body"), html='<span style="color:#f00">red</span>', text="red")
    assert page.evaluate("window.got") == {"html": '<span style="color:#f00">red</span>', "text": "red"}


def test_a_drop_hands_the_page_the_file_with_its_name_type_and_bytes(page: Any, tmp_path: Path) -> None:
    dropped = tmp_path / "notes.txt"
    dropped.write_text("été", encoding="utf-8")
    transfer.drop(page.locator("#zone"), dropped)
    page.wait_for_function("window.got.file !== undefined")
    assert page.evaluate("window.got.file") == {"name": "notes.txt", "type": "text/plain", "text": "été"}


def test_a_paste_with_nothing_on_the_clipboard_is_refused() -> None:
    with pytest.raises(ValueError, match="text or the html"):
        transfer.paste(object())


def test_a_drop_of_a_missing_file_names_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing.docx"):
        transfer.drop(object(), tmp_path / "missing.docx")
