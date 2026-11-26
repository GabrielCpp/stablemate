"""What `check_portability.py` lets an allow entry excuse, and what it never does."""

from __future__ import annotations

from pathlib import Path

import check_portability

EXCUSE = "supervises a process group on POSIX"


def _repo(root: Path, source: str) -> Path:
    (root / "pkg").mkdir()
    (root / "pkg" / "runner.py").write_text(source, encoding="utf-8")
    (root / ".agent-checks.toml").write_text(
        '[check-portability]\ntier1 = ["pkg"]\n\n'
        f'[check-portability.allow]\n"pkg/runner.py" = "{EXCUSE}"\n',
        encoding="utf-8",
    )
    return root


def test_an_excused_module_reading_sigkill_as_a_default_argument_fails(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        "import os\nimport signal\n\n"
        "def kill(pid: int, sig: int = signal.SIGKILL) -> None:\n"
        "    os.killpg(pid, sig)\n",
    )

    problems = check_portability.check_portability(repo)

    assert len(problems) == 1
    assert problems[0].startswith("pkg/runner.py:4 signal.SIGKILL does not exist on Windows")


def test_an_excused_module_importing_fcntl_at_module_level_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "import fcntl\n")

    problems = check_portability.check_portability(repo)

    assert [problem.split(" (")[0] for problem in problems] == [
        "pkg/runner.py:1 fcntl does not exist on Windows"
    ]


def test_an_excused_module_using_posix_names_only_at_call_time_passes(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        "import os\nimport signal\nimport sys\n\n"
        "if sys.platform != 'win32':\n    import fcntl\n\n"
        "try:\n    HANGUP = signal.SIGHUP\nexcept AttributeError:\n    HANGUP = None\n\n"
        "def kill(pid: int) -> None:\n    os.killpg(pid, signal.SIGKILL)\n",
    )

    assert check_portability.check_portability(repo) == []


def test_a_module_without_an_excuse_fails_on_a_call_time_use(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "import os\n\ndef kill(pid: int) -> None:\n    os.killpg(pid, 9)\n")
    (repo / ".agent-checks.toml").write_text(
        '[check-portability]\ntier1 = ["pkg"]\n', encoding="utf-8"
    )

    assert check_portability.check_portability(repo) == [
        "pkg/runner.py:4 os.killpg() does not exist on Windows"
    ]
