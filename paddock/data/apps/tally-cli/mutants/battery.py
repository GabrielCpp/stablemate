"""The differential battery the mutant corpus was gated on, frozen beside it.

Not a test suite: it asserts nothing and knows nothing about any mutant. It drives
`python3 -m tally` through the app's happy paths and its edges and prints one canonical
transcript — every exit code, both streams, and a census of every file each scenario left
behind, byte for byte. Two trees behave identically exactly when their transcripts are
equal, and that equality is the corpus's equivalence gate: a candidate whose transcript
matches its story image's is indistinguishable by observation, so it goes into
`mutants.yml` under `discards:` with its reason, never into the pool — a mutant nothing
can see would sit in the denominator as a survivor no triage could ever retire.

One battery serves all three story images. A scenario that names a command an earlier
image does not have yet degrades identically on both sides of the gate — argparse refuses
it the same way in the candidate and in the control — so the scenarios below are written
against the finished app and compare soundly against any image.

Everything here is deterministic on purpose: scenarios run in a throwaway directory and
speak only in relative paths, so no absolute path, timestamp or hostname reaches the
transcript. Stdlib only, like the app it drives.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

Step = tuple[str, ...]

CSV_HEADER = "who,what,amount_cents,spent_on"

#: Deliberately not in alphabetical order by payer: an ordering change in the report is
#: only visible when insertion order and sorted order disagree.
TRIP_CSV = "\n".join((
    CSV_HEADER,
    "bob,taxi,900,2026-03-01",
    "alice,lunch,1200,2026-03-01",
    "bob,museum,700,2026-03-02",
)) + "\n"

#: The same file with its first row repeated — within one import, not across two.
DOUBLED_CSV = "\n".join((
    CSV_HEADER,
    "bob,taxi,900,2026-03-01",
    "bob,taxi,900,2026-03-01",
    "alice,lunch,1200,2026-03-01",
)) + "\n"

#: A good row, then a row with too few fields — so the refusal has a line number to name
#: and the good row has a chance to leak into the ledger.
MALFORMED_CSV = "\n".join((
    CSV_HEADER,
    "bob,taxi,900,2026-03-01",
    "carol,ferry,650",
)) + "\n"

_ADD_LUNCH: Step = ("add", "alice", "lunch", "1200", "2026-03-01")

#: `(name, files seeded before the first step, the invocations)` — each scenario starts
#: in a fresh empty directory and its census is read after the last step.
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
