from __future__ import annotations

import pytest

from groom import cli
from groom.tui import app as tui_app


def test_tui_hands_the_url_flag_to_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(tui_app, "run", seen.append)
    cli.main(["tui", "--url", "http://127.0.0.1:9999"])
    assert seen == ["http://127.0.0.1:9999"]


def test_tui_falls_back_to_groom_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(tui_app, "run", seen.append)
    monkeypatch.setenv("GROOM_URL", "https://groom.example.com")
    cli.main(["tui"])
    assert seen == ["https://groom.example.com"]


@pytest.mark.parametrize("url", ["ftp://127.0.0.1:8787", "127.0.0.1:8787", "http://"])
def test_tui_rejects_a_url_that_is_not_http_as_a_usage_error(
    url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    started: list[str] = []
    monkeypatch.setattr(tui_app, "run", started.append)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["tui", "--url", url])
    assert exit_info.value.code == 2
    assert "must be an http:// or https:// URL" in capsys.readouterr().err
    assert started == []
