"""What a page's own paste, drop and upload handlers receive when a scenario performs those triggers, and what a download reads back as."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

transfer = load_harness_module("ostler_qa_transfer")
browser_module = load_harness_module("ostler_qa_browser")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = """
<div id="body" contenteditable="true"></div>
<div id="zone">drop here</div>
<input id="file" type="file">
<input id="hidden-file" type="file" style="display: none">
<button id="export" onclick="const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob(['<rule/>'], {type: 'application/xml'})); a.download = 'rules.xml'; document.body.append(a); a.click()">Export</button>
<button id="pick" onclick="document.getElementById('hidden-file').click()">Import</button>
<script>
  for (const id of ["file", "hidden-file"]) {
    document.getElementById(id).addEventListener("change", async (event) => {
      const [file] = event.target.files;
      window.got.upload = {name: file.name, text: await file.text()};
    });
  }
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


@pytest.mark.parametrize("control", ["#file", "#pick"])
def test_an_upload_hands_the_page_the_file_through_its_input_or_the_picker_its_control_opens(
    page: Any, tmp_path: Path, control: str,
) -> None:
    picked = tmp_path / "rules.xml"
    picked.write_text("<rule/>", encoding="utf-8")
    transfer.upload(page, page.locator(control), picked)
    page.wait_for_function("window.got.upload !== undefined")
    assert page.evaluate("window.got.upload") == {"name": "rules.xml", "text": "<rule/>"}


def test_a_download_reads_back_by_the_name_the_page_suggested_and_its_content(page: Any) -> None:
    with page.expect_download() as downloaded:
        page.locator("#export").click()
    assert browser_module.Browser._downloaded(downloaded.value) == {"name": "rules.xml", "text": "<rule/>"}


def test_a_download_the_page_hands_over_reaches_the_browser_listening_on_it(page: Any, tmp_path: Path) -> None:
    listening = browser_module.Browser(
        SimpleNamespace(recording=None, viewport=None),
        qa_dir=tmp_path, scenario_id="export", clock=lambda: 0, emit=lambda *_: None,
    )
    listening._listen(page)
    with page.expect_download():
        page.locator("#export").click()
    assert listening.downloads() == [{"name": "rules.xml", "text": "<rule/>"}]


def test_an_upload_of_a_missing_file_names_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing.xml"):
        transfer.upload(object(), object(), tmp_path / "missing.xml")


def test_a_paste_with_nothing_on_the_clipboard_is_refused() -> None:
    with pytest.raises(ValueError, match="text or the html"):
        transfer.paste(object())


def test_a_drop_of_a_missing_file_names_it(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing.docx"):
        transfer.drop(object(), tmp_path / "missing.docx")
