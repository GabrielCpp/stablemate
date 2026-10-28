#!/usr/bin/env python3
"""Refuse a commit that adds code which already exists elsewhere in the repository."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatch
from pathlib import Path

CONFIG = ".agent-checks.toml"
TABLE = "check-clones"

JSCPD_VERSION = "5.4.1"
CACHE_ENV = "STABLEMATE_CACHE_DIR"
REGISTRY = "https://registry.npmjs.org"

MIN_TOKENS = 50
MIN_LINES = 5

DEFAULT_IGNORE = (
    "**/node_modules/**", "**/vendor/**", "**/dist/**", "**/build/**", "**/.venv/**",
    "**/__pycache__/**", "**/mocks/**", "**/mock/**", "**/fixtures/**", "**/testdata/**",
    "**/migrations/**", "**/tests/**", "**/test/**", "**/*_test.go", "**/test_*.py",
    "**/*_test.py", "**/*.test.ts", "**/*.spec.ts", "**/*.test.tsx", "**/*.spec.tsx",
    "**/*_test.dart",
)
ALWAYS_IGNORE = (".git/**", ".agents/**", ".claude/**", ".github/**", "**/*.md")

GENERATED_MARKERS = ("Code generated", "DO NOT EDIT", "DO NOT MODIFY", "@generated")
MARKER_LINES = 10


@dataclass(frozen=True)
class Platform:
    package: str
    integrity: str
    binary: str = "jscpd"


PLATFORMS: dict[tuple[str, str, str], Platform] = {
    ("linux", "x64", "gnu"): Platform(
        "jscpd-linux-x64-gnu", "sha512-UiC4YoGAVVLy6hPVz8A6cndo7W5br4FAO2hADnFeinhBPnXPu0QFh1q/s/8B3ldeQHQkpYd/l5cjqNBMrbm78w=="
    ),
    ("linux", "arm64", "gnu"): Platform(
        "jscpd-linux-arm64-gnu", "sha512-XUYZJZVxSY7JIBEoyOOMTgvJwmymkns4wG55tu6I/vRKXnS5QtaTESQfRLt6xj1+62aflAvr01FAhPAy+du6tA=="
    ),
    ("linux", "x64", "musl"): Platform(
        "jscpd-linux-x64-musl", "sha512-toAafl5roqfFotPrDJNMY9noNVZ9dReBqcO/nT5pJ8+7aq+opbscaLUcV4+8jxTq5btUD6CiO72+Fu+TyUZv3Q=="
    ),
    ("linux", "arm64", "musl"): Platform(
        "jscpd-linux-arm64-musl", "sha512-h2sH8Bk++yBxWqq2QAy4fvPzXkw1vecDSyOmzLwPfnRQoQ2Q/EWxCNOrgJSb+SNMLWoHLLzfqx8m9wt2GG6a8w=="
    ),
    ("darwin", "arm64", ""): Platform(
        "jscpd-darwin-arm64", "sha512-LXHVeH60C9BsozcVIMPmXWvj97KqFKbCJYmYG4hDwfwIwS1kz+uF7yiObckP6h2xo12pD88nI4XjWTB5frjZUw=="
    ),
    ("darwin", "x64", ""): Platform(
        "jscpd-darwin-x64", "sha512-Gqck4tcMZjv4IvYHU2Vcikb885zTADo5T/YfEqeu1i5W5tfFpLdViiTYrh5wbrW+uxBqC33gHpG1hy0xbGYknQ=="
    ),
    ("windows", "x64", ""): Platform(
        "jscpd-windows-x64-msvc", "sha512-sN57Y9YP3ijrqc1IsWDceOFHUwbukg9/mU2NSDHTryKKc5CUvWz+o9GId8uKTiJIhkKfR/Ce5GKkCepTwB6kaw==", "jscpd.exe"
    ),
    ("windows", "arm64", ""): Platform(
        "jscpd-windows-arm64-msvc", "sha512-JLMga/NIwv/OPurPsXA2/d5OdWfdwrsBk2D4NhyKnrV/uNjo1BIi2zXztzDyTQVKMK/TEK6GPgLD143GG1fZ0A==", "jscpd.exe"
    ),
}

DEFINITIONS: dict[str, tuple[re.Pattern[str], ...]] = {}
SKIPPED_NAMES = frozenset({"if", "for", "while", "switch", "catch", "return"})


def _patterns(*sources: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(source) for source in sources)


_GO = _patterns(r"^func\s+(?:\([^)]*\)\s*)?(\w+)", r"^type\s+(\w+)")
_PY = _patterns(r"^\s*(?:async\s+)?def\s+(\w+)", r"^\s*class\s+(\w+)")
_TS = _patterns(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)",
    r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)",
    r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>",
    r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(",
)
_DART = _patterns(
    r"^\s*(?:abstract\s+)?class\s+(\w+)",
    r"^\s*(?:static\s+)?(?:[\w<>?,\[\] ]+\s+)?(\w+)\s*\([^;]*\)\s*(?:async\s*)?\{",
)
DEFINITIONS.update({".go": _GO, ".py": _PY, ".dart": _DART})
DEFINITIONS.update({ext: _TS for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs")})


class DetectorMissing(RuntimeError):
    """The clone detector is not installed and could not be fetched."""


@dataclass(frozen=True)
class Side:
    path: str
    start: int
    end: int


@dataclass(frozen=True)
class CopyPair:
    first: Side
    second: Side
    lines: int
    is_new: bool


@dataclass(frozen=True)
class Coincidence:
    files: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Threshold:
    min_tokens: int
    min_lines: int
    ignore: tuple[str, ...]
    markers: tuple[str, ...]
    coincidences: tuple[Coincidence, ...]

    @property
    def ignore_globs(self) -> tuple[str, ...]:
        return (*self.ignore, *ALWAYS_IGNORE)


Span = dict[str, list[tuple[int, int]]]
Runner = Callable[[Path, Threshold, str], Mapping]


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args), cwd=root, capture_output=True, text=True, check=check
    )


def threshold(root: Path) -> Threshold:
    """The `[check-clones]` table, with defaults for whatever it leaves out."""
    config = root / CONFIG
    table: dict = {}
    if config.is_file():
        table = tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})
    entries = tuple(
        Coincidence(
            files=tuple(str(item) for item in entry.get("files", [])),
            reasons=tuple(str(item) for item in entry.get("reasons", [])),
        )
        for entry in table.get("coincidence", [])
    )
    return Threshold(
        min_tokens=int(table.get("min-tokens", MIN_TOKENS)),
        min_lines=int(table.get("min-lines", MIN_LINES)),
        ignore=tuple(table.get("ignore", DEFAULT_IGNORE)),
        markers=tuple(table.get("generated-markers", GENERATED_MARKERS)),
        coincidences=entries,
    )


def coincidence_problems(limits: Threshold) -> list[str]:
    problems = []
    for entry in limits.coincidences:
        reasons = {reason.strip() for reason in entry.reasons if reason.strip()}
        if len(reasons) < 2:
            problems.append(
                f"[[{TABLE}.coincidence]] for {', '.join(entry.files) or '(no files)'}: "
                "a coincidence names two reasons, one per file, and this one does not"
            )
    return problems


def platform_key() -> tuple[str, str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64"}.get(machine, machine)
    libc = ""
    if system == "linux":
        libc = "gnu" if platform.libc_ver()[0] == "glibc" else "musl"
    return system, arch, libc


def detector_path(env: Mapping[str, str] | None = None, binary: str | None = None) -> Path:
    environ = os.environ if env is None else env
    base = environ.get(CACHE_ENV)
    if not base:
        raise DetectorMissing(
            f"${CACHE_ENV} is not set. The runner farrier generates for the pre-commit "
            "hook sets it; run this check through that hook, or export it."
        )
    if binary is None:
        binary = "jscpd.exe" if platform.system().lower() == "windows" else "jscpd"
    return Path(base).expanduser() / "tools" / "jscpd" / JSCPD_VERSION / binary


def _integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def ensure_detector(
    env: Mapping[str, str] | None = None,
    platforms: Mapping[tuple[str, str, str], Platform] = PLATFORMS,
    key: tuple[str, str, str] | None = None,
    registry: str = REGISTRY,
    fetch: Callable[[str], bytes] = _download,
) -> Path:
    """The detector binary, downloaded once into the shared cache and verified."""
    key = key or platform_key()
    spec = platforms.get(key)
    if spec is None:
        raise DetectorMissing(f"no jscpd {JSCPD_VERSION} build for platform {'/'.join(key)}")
    target = detector_path(env, spec.binary)
    if target.is_file():
        return target
    url = f"{registry}/{spec.package}/-/{spec.package}-{JSCPD_VERSION}.tgz"
    where = f"{target} (from {url})"
    try:
        data = fetch(url)
    except (OSError, ValueError) as error:
        raise DetectorMissing(f"cannot download jscpd to {where}: {error}") from error
    if _integrity(data) != spec.integrity:
        raise DetectorMissing(f"jscpd download failed its integrity check, not installed to {where}")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            member = archive.extractfile(f"package/bin/{spec.binary}")
            if member is None:
                raise DetectorMissing(f"jscpd archive has no package/bin/{spec.binary}, {where}")
            payload = member.read()
    except (tarfile.TarError, KeyError, OSError) as error:
        raise DetectorMissing(f"cannot unpack jscpd for {where}: {error}") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".jscpd-")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(payload)
        os.chmod(temp_name, 0o755)
        os.replace(temp_name, target)
    except OSError as error:
        Path(temp_name).unlink(missing_ok=True)
        raise DetectorMissing(f"cannot install jscpd to {where}: {error}") from error
    return target


def staged_paths(root: Path) -> list[str]:
    """Repo-relative POSIX paths the commit would add or change."""
    out = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").stdout
    return [entry for entry in out.split("\0") if entry]


def has_head(root: Path) -> bool:
    return _git(root, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_span(diff: str) -> Span:
    """Added line ranges per path from a zero-context unified diff."""
    span: Span = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = target[2:] if target.startswith("b/") else None
            if current is not None:
                span.setdefault(current, [])
            continue
        match = _HUNK.match(line)
        if match and current is not None:
            first = int(match.group(1))
            count = 1 if match.group(2) is None else int(match.group(2))
            if count > 0:
                span[current].append((first, first + count - 1))
    return span


def change_span(root: Path, paths: Sequence[str]) -> Span:
    diff = _git(root, "diff", "-U0", "HEAD", "--", *paths).stdout
    return parse_span(diff)


def has_marker(path: Path, markers: Sequence[str]) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            head = [handle.readline() for _ in range(MARKER_LINES)]
    except OSError:
        return False
    return any(marker in line for line in head for marker in markers)


def pairs_from_report(report: Mapping, root: Path, limits: Threshold) -> list[CopyPair]:
    """Copy pairs of a detector report, minus Markdown blocks and generated files."""
    pairs = []
    for duplicate in report.get("duplicates", []):
        lines = int(duplicate["lines"])
        sides = []
        for key in ("firstFile", "secondFile"):
            entry = duplicate[key]
            start = int(entry["start"])
            sides.append(Side(str(entry["name"]), start, start + lines - 1))
        if any(
            not (root / side.path).is_file() or has_marker(root / side.path, limits.markers)
            for side in sides
        ):
            continue
        pairs.append(CopyPair(sides[0], sides[1], lines, bool(duplicate.get("isNew"))))
    return pairs


def _added(side: Side, ranges: Sequence[tuple[int, int]]) -> int:
    return sum(max(0, min(side.end, last) - max(side.start, first) + 1) for first, last in ranges)


def _covered(pair: CopyPair, entry: Coincidence) -> bool:
    def matches(path: str) -> bool:
        return any(fnmatch(path, glob) for glob in entry.files)

    return matches(pair.first.path) and matches(pair.second.path)


def copy_pairs(
    pairs: Sequence[CopyPair],
    span: Span,
    coincidences: Sequence[Coincidence] = (),
    min_added: int = MIN_LINES,
) -> list[CopyPair]:
    """New pairs with at least `min_added` added lines on one side, that side first, less the declared coincidences."""
    kept = []
    for pair in pairs:
        if not pair.is_new:
            continue
        first_added = _added(pair.first, span.get(pair.first.path, [])) >= min_added
        if not first_added and _added(pair.second, span.get(pair.second.path, [])) < min_added:
            continue
        if any(_covered(pair, entry) for entry in coincidences):
            continue
        kept.append(pair if first_added else replace(pair, first=pair.second, second=pair.first))
    return kept


def enclosing_unit(path: Path, line: int) -> str | None:
    """Name of the nearest definition at or above `line`, for the report only."""
    patterns = DEFINITIONS.get(path.suffix)
    if patterns is None:
        return None
    try:
        source = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for text in reversed(source[: max(line, 0)]):
        for pattern in patterns:
            match = pattern.match(text)
            if match and match.group(1) not in SKIPPED_NAMES:
                return match.group(1)
    return None


def unit_text(root: Path, side: Side) -> str | None:
    """The unit a side sits in, or "first .. last" when it straddles two."""
    first = enclosing_unit(root / side.path, side.start)
    last = enclosing_unit(root / side.path, side.end)
    if first is None and last is None:
        return None
    if first == last or last is None:
        return first
    if first is None:
        return last
    return f"{first} .. {last}"


def label(root: Path, side: Side) -> str:
    where = f"{side.path}:{side.start}-{side.end}"
    unit = unit_text(root, side)
    return where if unit is None else f"{where} ({unit})"


def run_detector(root: Path, limits: Threshold, base: str = "HEAD") -> Mapping:
    """jscpd's JSON report of clones new against `base`."""
    binary = ensure_detector()
    with tempfile.TemporaryDirectory() as out_dir:
        result = subprocess.run(
            (
                str(binary),
                ".",
                "--baseline-from-ref",
                base,
                "-r",
                "json",
                "-o",
                out_dir,
                "--min-tokens",
                str(limits.min_tokens),
                "--min-lines",
                str(limits.min_lines),
                "--ignore",
                ",".join(limits.ignore_globs),
                "--silent",
                "--no-tips",
                "--no-colors",
            ),
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        report = Path(out_dir) / "jscpd-report.json"
        if result.returncode not in (0, 1) or not report.is_file():
            raise DetectorMissing(
                f"jscpd exited {result.returncode} without a report:\n{result.stderr.strip()}"
            )
        return json.loads(report.read_text(encoding="utf-8"))


def range_span(root: Path, base: str) -> Span:
    return parse_span(_git(root, "diff", "-U0", base).stdout)


def check_clones(
    root: Path, runner: Runner = run_detector, base: str | None = None
) -> tuple[list[str], list[CopyPair]]:
    """Config problems and the copy pairs this commit, or the range since `base`, adds."""
    limits = threshold(root)
    problems = coincidence_problems(limits)
    if base is None:
        paths = staged_paths(root)
        if not paths or not has_head(root):
            return problems, []
        span = change_span(root, paths)
        base = "HEAD"
    else:
        span = range_span(root, base)
        if not any(span.values()):
            return problems, []
    report = runner(root, limits, base)
    pairs = pairs_from_report(report, root, limits)
    return problems, copy_pairs(pairs, span, limits.coincidences, limits.min_lines)


def _renders(root: Path, pairs: Sequence[CopyPair]) -> list[str]:
    lines = []
    for pair in pairs:
        lines.append(f"  {label(root, pair.first)}")
        lines.append(f"    repeats {label(root, pair.second)}, {pair.lines} lines")
    return lines


def _side_json(root: Path, side: Side) -> dict:
    return {"path": side.path, "start": side.start, "end": side.end, "unit": unit_text(root, side)}


def _json_report(root: Path, problems: Sequence[str], pairs: Sequence[CopyPair]) -> str:
    return json.dumps(
        {
            "pairs": [
                {
                    "added": _side_json(root, pair.first),
                    "existing": _side_json(root, pair.second),
                    "lines": pair.lines,
                }
                for pair in pairs
            ],
            "problems": list(problems),
        }
    )


def main(argv: Sequence[str] | None = None, runner: Runner = run_detector) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repo to check (default: cwd)")
    parser.add_argument("--base", help="check every line changed since this ref instead of the staged paths")
    parser.add_argument("--json", action="store_true", help="print the pairs and problems as one JSON object")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    top = _git(root, "rev-parse", "--show-toplevel", check=False)
    if top.returncode == 0 and top.stdout.strip():
        root = Path(top.stdout.strip())
    try:
        problems, pairs = check_clones(root, runner, args.base)
    except DetectorMissing as error:
        print(f"\nFAIL check_clones: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(_json_report(root, problems, pairs))
        return 1 if problems or pairs else 0
    if not problems and not pairs:
        return 0

    if pairs:
        print("\nFAIL check_clones: this commit adds code that already exists elsewhere.", file=sys.stderr)
        for line in _renders(root, pairs):
            print(line, file=sys.stderr)
    for problem in problems:
        print(f"\nFAIL check_clones: {problem}", file=sys.stderr)
    print(
        "\nA second copy changes for the same reason as the first and gets fixed in one\n"
        "place only. Pick one:\n"
        "\n"
        "  extract it            rule 2.12 of the code-structure skill: move one copy to the\n"
        "                        owner rules 2.5 to 2.9 pick and point both callers at it\n"
        "  it must stay          the two change for different reasons: add a\n"
        f"                        [[{TABLE}.coincidence]] entry to {CONFIG} naming both files\n"
        "                        and two reasons, one per file\n"
        "  tune the detector     min-tokens, min-lines and ignore live in "
        f"[{TABLE}] in {CONFIG}\n"
        "\n"
        "`--no-verify` also gets the commit in. It is the one route that leaves no trace\n"
        "for a reviewer, which is why the coincidence list is tracked.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
