"""The differential battery the mutant corpus was gated on, frozen beside it."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

Step = tuple[str, ...]

CSV_HEADER = "who,what,amount_cents,spent_on"

TRIP_CSV = "\n".join((
    CSV_HEADER,
    "bob,taxi,900,2026-03-01",
    "alice,lunch,1200,2026-03-01",
    "bob,museum,700,2026-03-02",
)) + "\n"

DOUBLED_CSV = "\n".join((
    CSV_HEADER,
    "bob,taxi,900,2026-03-01",
    "bob,taxi,900,2026-03-01",
    "alice,lunch,1200,2026-03-01",
)) + "\n"

MALFORMED_CSV = "\n".join((
    CSV_HEADER,
    "bob,taxi,900,2026-03-01",
    "carol,ferry,650",
)) + "\n"

_ADD_LUNCH: Step = ("add", "alice", "lunch", "1200", "2026-03-01")

SCENARIOS: tuple[tuple[str, dict[str, str], tuple[Step, ...]], ...] = (
    ("init-fresh", {}, (("init",),)),
    ("init-twice", {}, (("init",), ("init",))),
    ("init-named-currency", {}, (("--file", "trip.json", "init", "--currency", "USD"),)),
    ("add-happy", {}, (("init",), _ADD_LUNCH)),
    ("add-zero-refused", {}, (("init",), ("add", "alice", "lunch", "0", "2026-03-01"))),
    ("add-not-a-number", {}, (("init",), ("add", "alice", "lunch", "brunch", "2026-03-01"))),
    ("add-dry-run", {}, (("init",), ("add", "--dry-run", "alice", "lunch", "1200", "2026-03-01"))),
    ("import-happy", {"trip.csv": TRIP_CSV}, (("init",), ("import", "trip.csv"))),
    (
        "import-idempotent",
        {"trip.csv": TRIP_CSV},
        (("init",), ("import", "trip.csv"), ("import", "trip.csv")),
    ),
    ("import-in-file-duplicate", {"twice.csv": DOUBLED_CSV}, (("init",), ("import", "twice.csv"))),
    (
        "import-tail-after-known",
        {"trip.csv": TRIP_CSV},
        (("init",), _ADD_LUNCH, ("import", "trip.csv")),
    ),
    ("import-malformed-line-3", {"bad.csv": MALFORMED_CSV}, (("init",), ("import", "bad.csv"))),
    ("import-dry-run", {"trip.csv": TRIP_CSV}, (("init",), ("import", "--dry-run", "trip.csv"))),
    ("import-no-ledger", {"trip.csv": TRIP_CSV}, (("import", "trip.csv"),)),
    (
        "report-text",
        {},
        (
            ("init",),
            ("add", "bob", "taxi", "900", "2026-03-01"),
            _ADD_LUNCH,
            ("add", "alice", "coffee", "300", "2026-03-02"),
            ("report",),
        ),
    ),
    (
        "report-json",
        {},
        (
            ("init",),
            ("add", "bob", "taxi", "900", "2026-03-01"),
            _ADD_LUNCH,
            ("report", "--json"),
        ),
    ),
    ("report-no-ledger", {}, (("report",),)),
    ("export-with-duplicates", {}, (("init",), _ADD_LUNCH, _ADD_LUNCH, ("export", "out.csv"))),
    ("export-empty", {}, (("init",), ("export", "out.csv"))),
    (
        "file-isolation",
        {},
        (("init",), ("--file", "other.json", "init", "--currency", "USD"), _ADD_LUNCH),
    ),
)


def _tally(tree: Path, workdir: Path, argv: Step) -> tuple[int, str, str]:
    done = subprocess.run(
        [sys.executable, "-m", "tally", *argv],
        cwd=workdir,
        env={**os.environ, "PYTHONPATH": str(tree), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return done.returncode, done.stdout, done.stderr


def _quoted(label: str, text: str) -> list[str]:
    if not text:
        return []
    return [f"{label}:"] + [f"  |{line}" for line in text.splitlines()]


def transcript(tree: Path) -> str:
    """Run every scenario against the `tally` package under `tree`, canonically."""
    lines: list[str] = []
    for name, seeds, steps in SCENARIOS:
        with tempfile.TemporaryDirectory() as scratch:
            workdir = Path(scratch)
            for relative, content in sorted(seeds.items()):
                (workdir / relative).write_text(content, encoding="utf-8")
            lines.append(f"== {name}")
            for argv in steps:
                code, out, err = _tally(tree, workdir, argv)
                lines.append(f"$ tally {' '.join(argv)}")
                lines.append(f"rc {code}")
                lines.extend(_quoted("stdout", out))
                lines.extend(_quoted("stderr", err))
            lines.append("files:")
            for path in sorted(workdir.rglob("*")):
                if path.is_file():
                    lines.append(f"  {path.relative_to(workdir)}: {path.read_bytes()!r}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: battery.py <tree with a tally/ package>", file=sys.stderr)
        return 2
    sys.stdout.write(transcript(Path(arguments[0])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
