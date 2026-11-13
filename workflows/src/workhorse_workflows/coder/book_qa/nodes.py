"""The book lane's deterministic spine: coverage, the two plays of the book tool, the memory and the commit."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from ostler.book.index import FILE as INDEX_FILE
from ostler.book.index import parse as parse_index
from workhorse_workflows.coder.shared import commits, paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.book_qa import (
    BookPaths,
    BookPlay,
    BookQaRecord,
    BookScope,
    CoveredServices,
    ServiceCalls,
    UnreachedClaims,
)
from workhorse_workflows.coder.shared.schemas.docs import DocumentationGate
from workhorse_workflows.coder.shared.schemas.qa import QaFinding
from workhorse_workflows.coder.shared.schemas.queue import StoryCommitted
from workhorse_workflows.coder.shared.story_commit import uncommitted_paths
from workhorse_workflows.coder.shared.worktree import is_product, not_product_roots, untouched_since
from workhorse_workflows.kit import GitError, commit_paths, find_docs_root, find_repo_root, open_repo
from workhorse_workflows.kit.tools import run_tool

TAIL_LINES = 200
RECORD_FILE = "book-qa.json"
BOOK_OUT = Path("qa") / "book"
UNREACHED_FILE = "qa-unreached.json"


def book_dir(service: str) -> str:
    """The folder a service's executable book lives in, relative to the repo root."""
    return f"services/{service}"


def book_modules(root: Path, service: str) -> tuple[str, ...]:
    """The modules of a service's book: its package when one surface reaches it, one per surface when several do."""
    package = root / book_dir(service)
    if (package / "service.py").is_file():
        return (f"services.{service}",)
    return tuple(sorted(f"services.{service}.{found.parent.name}" for found in package.glob("*/service.py")))


def _surface(module: str) -> str:
    parts = module.split(".")
    return parts[2] if len(parts) > 2 else ""


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _play(argv: list[str], cwd: Path) -> BookPlay:
    done = run_tool(argv, cwd=cwd)
    return BookPlay(exit_code=done.returncode, output=_tail(done.stdout + done.stderr))


@blueprint.node
def covered_services(
    logger: logging.Logger, services: list[str] | None = None, repo_dir: str = ""
) -> CoveredServices:
    """The story's services that have an executable book under the repo root."""
    root = find_repo_root(repo_dir)
    covered = [name for name in services or [] if book_modules(root, name)]
    logger.info("%d of %d story service(s) have an executable book", len(covered), len(services or []))
    return CoveredServices(services=covered)


@blueprint.node
def book_check(logger: logging.Logger, service: str, repo_dir: str = "") -> BookPlay:
    """Build everything each module of the service's book declares, with no stack, and return the first red exit code and output tail."""
    root = find_repo_root(repo_dir)
    play = BookPlay(exit_code=0, output="")
    for module in book_modules(root, service):
        play = _play([sys.executable, "-m", "ostler.book", "check", module], root)
        logger.info("book check of %s exited %d", module, play.exit_code)
        if play.exit_code != 0:
            return BookPlay(exit_code=play.exit_code, output=f"{module}:\n{play.output}")
    return play


@blueprint.node
def verify_book_spec(
    logger: logging.Logger,
    services: list[str],
    author_status: str = "blocked",
    repo_dir: str = "",
) -> DocumentationGate:
    """Gate the spec pass of covered services: it ends when `ostler book check` exits 0 for each. A claim red against the app is expected before the build and is not read here."""
    root = find_repo_root(repo_dir)
    problems: list[str] = []
    failures: list[str] = []
    if author_status not in {"documented", "not_required"}:
        problems.append(f"the spec turn's status is {author_status!r}")
        failures.append("S:author-status")
    for name in services:
        for module in book_modules(root, name):
            play = _play([sys.executable, "-m", "ostler.book", "check", module], root)
            logger.info("book check of %s exited %d", module, play.exit_code)
            if play.exit_code != 0:
                problems.append(f"`ostler book check {module}` exited {play.exit_code}:\n{play.output}")
                failures.append(f"B:{name}")
                break
    return DocumentationGate(
        status="invalid" if failures else "passed",
        notes="\n\n".join(problems),
        failures=failures,
    )


@blueprint.node
def changed_book_paths(
    logger: logging.Logger,
    services: list[str],
    preexisting: list[str] | None = None,
    repo_dir: str = "",
) -> BookPaths:
    """The uncommitted paths under each covered service's book folder, less what was dirty before the story."""
    root = find_repo_root(repo_dir)
    excused = untouched_since(root, tuple(preexisting or ()))
    prefixes = tuple(book_dir(name) + "/" for name in services)
    found = [
        rel for rel in uncommitted_paths(root) if rel.startswith(prefixes) and rel not in excused
    ]
    logger.info("the spec pass changed %d book path(s)", len(found))
    return BookPaths(paths=found)


SHARED_EXEMPT_FILES = frozenset({"index.tsv", "DISAGREEMENTS.md", "WALLS.md", "UNDERSPECIFIED.md", "VERIFIED"})


def shared_book_paths(service: str, changed: dict[str, bool], surfaces: frozenset[str] = frozenset()) -> list[str]:
    """The changed paths under a service's book that other claims depend on, from `{path: added in this pass}`.

    A new journey file states one more claim and no other journey reads it, so a targeted play of
    the named calls judges it. An edit to an existing journey, to the model, the fixtures, the
    backstage or any other file of the book can move the answer of a call this pass never named,
    so only a play of the whole book judges it. The index, the disagreement and wall notes, the
    register of underspecified fields, the verified stamp and the decisions are records about the
    book that no play reads. In a book with several surfaces, each surface folder in `surfaces`
    holds the same kinds of file, and the shared model beside them is shared.
    """
    prefix = book_dir(service) + "/"
    shared: list[str] = []
    for rel, added in sorted(changed.items()):
        if not rel.startswith(prefix):
            continue
        inner = rel[len(prefix):]
        head, _, rest = inner.partition("/")
        if rest and head in surfaces:
            inner = rest
        if inner in SHARED_EXEMPT_FILES or inner.startswith("decisions/"):
            continue
        if added and inner.startswith("journeys/"):
            continue
        shared.append(rel)
    return shared


def _added_in_pass(root: Path, rel: str) -> bool:
    try:
        repo = open_repo(root)
        _ = repo.head.commit.tree / rel
    except KeyError:
        return True
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        return False
    return False


@blueprint.node
def book_scope(
    logger: logging.Logger,
    service: str,
    preexisting: list[str] | None = None,
    repo_dir: str = "",
) -> BookScope:
    """Decide whether the play of a service's book is the whole book: it is when this pass changed a shared part of it."""
    root = find_repo_root(repo_dir)
    excused = untouched_since(root, tuple(preexisting or ()))
    prefix = book_dir(service) + "/"
    changed = {
        rel: _added_in_pass(root, rel)
        for rel in uncommitted_paths(root)
        if rel.startswith(prefix) and rel not in excused
    }
    surfaces = frozenset(_surface(module) for module in book_modules(root, service)) - {""}
    shared = shared_book_paths(service, changed, surfaces)
    logger.info(
        "the pass changed %d path(s) of %s, %d of them shared: %s book",
        len(changed), service, len(shared), "whole" if shared else "named-call",
    )
    return BookScope(whole=bool(shared), shared=shared, changed=len(changed))


@blueprint.node
def book_run(
    logger: logging.Logger,
    service: str,
    only: list[str],
    copy: str,
    out_dir: str,
    outside: list[str] | None = None,
    repo_dir: str = "",
) -> BookPlay:
    """Play the named calls of the service's book against the run's copy of the stack, or the whole book when `only` is empty. A finding of an endpoint outside `outside` goes to the book's register of underspecified fields. The play has no time bound."""
    root = find_repo_root(repo_dir)
    modules = book_modules(root, service) or (f"services.{service}",)
    if len(modules) == 1:
        play = _play(_run_argv(modules[0], only, outside, copy, out_dir), root)
        logger.info("book run of %s over %s exited %d", service, f"{len(only)} call(s)" if only else "the whole book", play.exit_code)
        return play
    claims = _endpoints_by_module(root, modules)
    outputs: list[str] = []
    for module in modules:
        named = [call for call in only if call in claims[module] or (module == modules[0] and not any(call in held for held in claims.values()))]
        if only and not named:
            continue
        kept = [call for call in outside or () if call in claims[module]]
        module_outside = kept if kept or not outside else None
        play = _play(_run_argv(module, named, module_outside, copy, str(Path(out_dir) / module), register=bool(outside) and not kept), root)
        logger.info("book run of %s over %s exited %d", module, f"{len(named)} call(s)" if named else "the whole module", play.exit_code)
        if play.exit_code != 0:
            return BookPlay(exit_code=play.exit_code, output=f"{module}:\n{play.output}")
        outputs.append(f"{module}:\n{play.output}")
    return BookPlay(exit_code=0, output=_tail("\n".join(outputs)))


def _run_argv(module: str, only: list[str], outside: list[str] | None, copy: str, out_dir: str, register: bool = False) -> list[str]:
    argv = [sys.executable, "-m", "ostler.book", "run", module]
    if only:
        argv += ["--only", ",".join(only)]
    if outside:
        argv += ["--register-outside", ",".join(outside)]
    elif register:
        argv += ["--register"]
    return argv + ["--copy", copy, "--out", out_dir]


def _endpoints_by_module(root: Path, modules: tuple[str, ...]) -> dict[str, frozenset[str]]:
    held: dict[str, frozenset[str]] = {}
    for module in modules:
        index = root / Path(*module.split(".")) / INDEX_FILE
        text = index.read_text(encoding="utf-8") if index.is_file() else ""
        held[module] = frozenset(entry.name for entry in parse_index(text) if entry.kind == "endpoint")
    return held


@blueprint.node
def read_book_record(logger: logging.Logger, spec_dir: str) -> BookQaRecord:
    """The calls a passed check of this story played, or an empty record when none did."""
    return _load_record(Path(spec_dir))


def _load_record(spec: Path) -> BookQaRecord:
    record = spec / RECORD_FILE
    if not record.is_file():
        return BookQaRecord()
    return BookQaRecord.model_validate(json.loads(record.read_text(encoding="utf-8")))


@blueprint.node
def write_book_record(
    logger: logging.Logger,
    spec_dir: str,
    services: list[ServiceCalls],
    findings: list[QaFinding] | None = None,
    unreached: list[str] | None = None,
) -> BookQaRecord:
    """Record the calls a passed check played, the findings it stood on and the claims the book could not state, so a second visit for the story replays them. A green replay means a declared defect still holds, so its finding still stands."""
    record = BookQaRecord(services=services, findings=findings or [], unreached=unreached or [])
    target = Path(spec_dir) / RECORD_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.model_dump(exclude_defaults=True), indent=2) + "\n", encoding="utf-8")
    logger.info("recorded the calls of %d service(s) in %s", len(services), target)
    return record


@blueprint.node
def write_unreached_claims(
    logger: logging.Logger, spec_dir: str, repo_dir: str = ""
) -> UnreachedClaims:
    """Write `qa-unreached.json` in the spec dir: the claims a clean book record could not state, which are all the scenario seat owes."""
    root = find_docs_root(repo_dir)
    spec = root / spec_dir
    target = spec / UNREACHED_FILE
    record = _load_record(spec)
    claims = [] if record.findings else list(record.unreached)
    spec.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(claims, indent=2) + "\n", encoding="utf-8")
    logger.info("the scenario seat owes %d unreached claim(s)", len(claims))
    return UnreachedClaims(claims=claims)


@blueprint.node
def commit_service_book(
    logger: logging.Logger,
    services: list[str],
    story_slug: str = "",
    story_id: str = "",
    epic: str = "",
    preexisting: list[str] | None = None,
    repo_dir: str = "",
) -> StoryCommitted:
    """Commit the changed paths under each covered service's book. A product path the seat changed outside those folders is returned in `refused`, and nothing is committed."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    folders = [(root / book_dir(name)).resolve() for name in services]
    excused = untouched_since(root, tuple(preexisting or ()))
    excluded = not_product_roots(repo_dir)
    inside: list[str] = []
    stray: list[str] = []
    for rel in uncommitted_paths(root):
        if rel in excused or paths.is_gate_context(rel):
            continue
        if any((root / rel).resolve().is_relative_to(folder) for folder in folders):
            inside.append(rel)
        elif is_product(root, rel, excluded):
            stray.append(rel)
    if stray:
        listing = "\n".join(f"- `{rel}`" for rel in stray)
        return StoryCommitted(
            refused=(
                "These paths changed outside the covered services' books, and the book pass may "
                f"edit only under {', '.join(book_dir(n) + '/' for n in services)}:\n\n{listing}\n\n"
                "Restore each one."
            )
        )
    if not inside:
        logger.info("the book pass left no uncommitted book path for %s", slug)
        return StoryCommitted()
    message = commits.message(
        "test",
        commits.scope(root.name),
        f"play {slug} in the service book",
        epic=epic,
        story=story_id or slug,
    )
    try:
        landed = commit_paths(root, message, *inside, verify=False)
    except GitError as exc:
        return StoryCommitted(refused=f"git refused the commit for {slug} in {root}: {exc}")
    logger.info("committed %d service book path(s) for %s", len(inside), slug)
    return StoryCommitted(committed=landed)


__all__ = [
    "BOOK_OUT",
    "RECORD_FILE",
    "UNREACHED_FILE",
    "book_check",
    "book_dir",
    "changed_book_paths",
    "verify_book_spec",
    "book_modules",
    "book_run",
    "book_scope",
    "commit_service_book",
    "covered_services",
    "read_book_record",
    "shared_book_paths",
    "write_book_record",
    "write_unreached_claims",
]
