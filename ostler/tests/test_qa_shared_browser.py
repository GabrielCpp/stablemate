"""Runs on one machine share one headless Chromium, each in a context of its own."""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import pytest
from ostler.qa.harness_host import load_harness_module

shared = load_harness_module("ostler_qa_shared_browser")


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(shared, "home", lambda: tmp_path / "shared-browser")
    monkeypatch.setenv("OSTLER_SHARED_BROWSER", "1")
    yield tmp_path
    endpoint = shared.home() / "endpoint"
    if endpoint.is_file():
        os.kill(json.loads(endpoint.read_text())["pid"], signal.SIGTERM)


def test_two_runs_reach_one_browser_and_each_films_its_own_page(cache: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        one = shared.connect(playwright)
        two = shared.connect(playwright)
        assert one is not None and two is not None
        server = json.loads((shared.home() / "endpoint").read_text())
        videos = []
        for browser, text in ((one, "one"), (two, "two")):
            context = browser.new_context(record_video_dir=str(cache / "videos"))
            page = context.new_page()
            page.set_content(f"<h1>{text}</h1>")
            assert page.inner_text("h1") == text
            assert len(context.pages) == 1
            video = page.video
            context.close()
            videos.append(Path(video.path()))
        one.close()
        two.close()
        assert json.loads((shared.home() / "endpoint").read_text()) == server
        assert all(video.stat().st_size > 0 for video in videos)
        assert shared.connect(playwright) is not None
        assert json.loads((shared.home() / "endpoint").read_text()) == server


def test_a_run_with_sharing_off_gets_no_shared_browser(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("OSTLER_SHARED_BROWSER", "0")
    with sync_playwright() as playwright:
        assert shared.connect(playwright) is None
    assert not shared.home().exists()
