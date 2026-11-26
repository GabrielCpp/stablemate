"""The `groom` console script's output encoding when stdout is a pipe."""
from __future__ import annotations

import io
import sys

import pytest

from groom import cli


def _cp1252_pipe(sink: io.BytesIO | None = None) -> io.TextIOWrapper:
    return io.TextIOWrapper(sink or io.BytesIO(), encoding="cp1252")


def test_help_prints_non_ascii_through_a_cp1252_pipe_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = io.BytesIO()
    pipe = _cp1252_pipe(sink)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdout", pipe)
    monkeypatch.setattr(sys, "stderr", _cp1252_pipe())

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])

    assert exit_info.value.code == 0
    pipe.flush()
    assert "→" in sink.getvalue().decode("utf-8")


def test_posix_stdout_encoding_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    pipe = _cp1252_pipe()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "stdout", pipe)

    cli._utf8_stdio()

    assert pipe.encoding == "cp1252"
