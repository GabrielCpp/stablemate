"""`ostler book move`: books that sit flat under `services/` go into `services/<repo>/`, and every module name that points at them follows."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ostler._vendor.stablemate_core import books, config

DOTTED = (".py", ".md", ".tsv", ".yml", ".yaml", ".j2", ".toml")
LEFTOVER = "index.tsv"
CHECKS_FILE = ".agent-checks.toml"


class Refused(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    root: Path
    repo: str
    source: Path
    names: tuple[str, ...]
    rewritten: tuple[str, ...]
    dirs: tuple[str, ...]

    @property
    def services(self) -> Path:
        return self.root / "services"

    def target(self, name: str) -> Path:
        return self.services / self.repo / name


def cmd_move(args: argparse.Namespace, start: Path) -> int:
    try:
        plan = _plan(args, start)
        _refuse(plan)
    except (Refused, config.ConfigError) as refused:
        print(f"error: {refused}", file=sys.stderr)
        return 2
    moves = _moves(plan)
    dry = args.dry_run
    if not dry:
        _carry_out(plan, moves)
    for src, dest in moves:
        print(f"{'would move' if dry else 'moved'} {_shown(plan, src)} to {dest.relative_to(plan.root).as_posix()}")
    hand: list[str] = []
    for current, shown, text in _documents(plan, [] if not dry else moves):
        new, count = _rewrite(plan, shown, text)
        if count:
            print(f"{'would rewrite' if dry else 'rewrote'} {count} reference(s) in {shown.relative_to(plan.root).as_posix()}")
            if not dry:
                current.write_text(new, encoding="utf-8")
        hand += _by_hand(plan, shown, new)
    for line in hand:
        print(line)
    return 0


def _plan(args: argparse.Namespace, start: Path) -> Plan:
    if args.to:
        root = Path(args.to).resolve()
    elif books.namespaced(start):
        root = books.book_home(start)
    else:
        root = config.resolve_artifacts_dir()
    inside = books.namespaced(start) or start.resolve().is_relative_to(root)
    repo = args.repo or (None if inside else config.repository_name(start))
    if not repo:
        raise Refused("name the repository with --repo")
    if "." in repo or "/" in repo:
        raise Refused(f"--repo {repo!r} must not hold a '.' or a '/'")
    source = Path(args.source).resolve() if args.source else root / "services"
    if args.names:
        names = tuple(args.names)
    elif args.source:
        names = tuple(sorted(p.name for p in source.iterdir() if p.name != "__pycache__" and not p.name.startswith(".")))
    else:
        raise Refused("name the books to move")
    dirs = tuple(n for n in names if (source / n).is_dir())
    stems = tuple(Path(n).stem for n in names if n.endswith(".py") and (source / n).is_file() and n != "__init__.py")
    return Plan(root, repo, source, names, tuple(dict.fromkeys((*dirs, *stems))), dirs)


def _refuse(plan: Plan) -> None:
    for name in plan.names:
        if not (plan.source / name).exists():
            raise Refused(f"{plan.source / name} does not exist: nothing to move as {name!r}")
    for name in plan.names:
        if plan.target(name).exists():
            raise Refused(f"{plan.target(name)} exists already")
    if plan.repo.isidentifier() or not plan.rewritten:
        return
    pattern = re.compile(rf"^\s*(from|import)\s+services\.({_alternation(plan.rewritten)})\b")
    found: list[str] = []
    scanned: set[Path] = set()
    for folder in (plan.services, *(plan.source / n for n in plan.names)):
        for path in _files(folder):
            if path.suffix != ".py" or path in scanned:
                continue
            scanned.add(path)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.match(line):
                    found.append(f"{_relative(plan, path)}:{number}: {line.strip()}")
    if found:
        raise Refused(
            "\n".join(found) + f"\nwrite it as a relative import first: no import statement can spell services.{plan.repo}"
        )


def _moves(plan: Plan) -> list[tuple[Path, Path]]:
    return [(plan.source / name, plan.target(name)) for name in plan.names]


def _carry_out(plan: Plan, moves: list[tuple[Path, Path]]) -> None:
    held = plan.services / f".{plan.repo}.moving"
    if plan.source == plan.services and plan.repo in plan.names:
        plan.services.joinpath(plan.repo).rename(held)
        moves = [(held if src == plan.services / plan.repo else src, dest) for src, dest in moves]
    plan.services.mkdir(parents=True, exist_ok=True)
    for src, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    for _, dest in moves:
        for cache in dest.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        for leftover in dest.rglob(LEFTOVER):
            leftover.unlink()
    init = plan.services / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")


def _shown(plan: Plan, src: Path) -> str:
    return src.relative_to(plan.root).as_posix() if src.is_relative_to(plan.services) else str(src)


def _relative(plan: Plan, path: Path) -> str:
    return path.relative_to(plan.root).as_posix() if path.is_relative_to(plan.root) else str(path)


def _files(folder: Path) -> list[Path]:
    if folder.is_file():
        return [folder]
    if not folder.is_dir():
        return []
    return [p for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]


def _documents(plan: Plan, moves: list[tuple[Path, Path]]) -> list[tuple[Path, Path, str]]:
    """Each file to read, the path it has once moved, and its text."""
    found: dict[Path, Path] = {}
    folders = [plan.services, *(src for src, _ in moves if not src.is_relative_to(plan.services))]
    for folder in folders:
        for current in _files(folder):
            if current.name == LEFTOVER:
                continue
            shown = current
            for src, dest in moves:
                if current == src or current.is_relative_to(src):
                    shown = dest / current.relative_to(src) if current != src else dest
                    break
            found[current] = shown
    checks = plan.root / CHECKS_FILE
    if checks.is_file():
        found[checks] = checks
    out: list[tuple[Path, Path, str]] = []
    for current, shown in sorted(found.items(), key=lambda item: str(item[1])):
        if shown.suffix not in DOTTED:
            continue
        try:
            out.append((current, shown, current.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue
    return out


def _alternation(names: tuple[str, ...]) -> str:
    return "|".join(re.escape(n) for n in sorted(names, key=lambda n: (-len(n), n)))


def _rewrite(plan: Plan, shown: Path, text: str) -> tuple[str, int]:
    if not plan.rewritten:
        return text, 0
    dotted = re.compile(rf"(?<![\w.:/-])services\.({_alternation(plan.rewritten)})(?![\w-])")
    new, count = dotted.subn(rf"services.{plan.repo}.\1", text)
    if shown.name == CHECKS_FILE and plan.dirs:
        slash = re.compile(rf"(?<![\w.-])services/({_alternation(plan.dirs)})/")
        new, more = slash.subn(rf"services/{plan.repo}/\1/", new)
        count += more
    return new, count


def _by_hand(plan: Plan, shown: Path, text: str) -> list[str]:
    if not plan.rewritten:
        return []
    pattern = re.compile(rf"(?<![\w.-])services/({_alternation(plan.rewritten)})/")
    return [
        f"check by hand: {_relative(plan, shown)}:{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), 1)
        if pattern.search(line)
    ]
