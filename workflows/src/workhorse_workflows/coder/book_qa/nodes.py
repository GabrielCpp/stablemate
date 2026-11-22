"""The book lane's deterministic spine: coverage, the two plays of the book tool, the memory and the commit."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal, cast

from ostler.book.index import FILE as INDEX_FILE
from ostler.book.index import parse as parse_index
from ostler.book.sources import story_commits
from workhorse._vendor.stablemate_core import books
from workhorse_workflows.coder.book_qa.review import by_criterion
from workhorse_workflows.coder.shared import commits, paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.provenance import story_base
from workhorse_workflows.coder.shared.schemas.book_qa import (
    BookPaths,
    BookPlan,
    BookPlay,
    BookQaRecord,
    BookScope,
    CoveredServices,
    ReviewVerdict,
    ServiceCalls,
    StoryBase,
    UnreachedClaims,
)
from workhorse_workflows.coder.shared.schemas.docs import DocumentationGate
from workhorse_workflows.coder.shared.schemas.qa import QaFinding
from workhorse_workflows.coder.shared.schemas.queue import StoryCommitted
from workhorse_workflows.coder.shared.story_commit import uncommitted_paths
from workhorse_workflows.coder.shared.worktree import is_product, not_product_roots, untouched_since
from workhorse_workflows.kit.book_files import (
    BOOK_ENV,
    is_compiled,
    left_behind,
    left_behind_refusal,
    outside_paths,
)
from workhorse_workflows.kit import (
    GitError,
    commit_paths,
    find_book_package,
    find_book_root,
    find_docs_root,
    find_repo_root,
    open_repo,
)
from workhorse_workflows.kit.qa.runner import stack_env
from workhorse_workflows.kit.tools import run_tool

TAIL_LINES = 200
STALE_EXIT = 1
UNVERIFIED_EXIT = 2
DECISIONS_SECTION = "## Decisions touching stale elements"
CHANGE_SECTIONS = frozenset(
    {
        "## Stale elements",
        "## Changed files no element names",
        "## Changed functions no element names",
        "## Changed beside the named symbols, functions not told apart",
    }
)
RECORD_FILE = "book-qa.json"
REVIEW_FILE = "qa-review.md"
BOOK_OUT = Path("qa") / "book"
UNREACHED_FILE = "qa-unreached.json"
PLAN_FILE = "qa-plan.md"
TIMEOUT_EXIT = 3
WHOLE_PLAYS_NEVER_RUN = "whole plays are never run for a story; what the selection could not narrow is listed as owed"
OWED_CAP = 10
REACHED_CAUSE_CAP = 5
PLAN_STRENGTH = ("none", "empty", "partial", "whole")


def book_dir(package: str, service: str) -> str:
    """The folder a service's executable book lives in, relative to the book root."""
    return f"{books.package_folder(package)}/{service}"


def book_modules(root: Path, package: str, service: str) -> tuple[str, ...]:
    """The modules of a service's book: its package when one surface reaches it, one per surface when several do."""
    folder = root / book_dir(package, service)
    base = f"{package}.{service}"
    if (folder / "service.py").is_file():
        return (base,)
    return tuple(sorted(f"{base}.{found.parent.name}" for found in folder.glob("*/service.py")))


def _now() -> float:
    return time.monotonic()


def _surface(module: str, base: str) -> str:
    return module.removeprefix(base + ".") if module.startswith(base + ".") else ""


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _printed(text: str | bytes | None) -> str:
    return text.decode("utf-8", "replace") if isinstance(text, bytes) else text or ""


def _play(
    argv: list[str],
    cwd: Path,
    timeout: float | None = None,
    held: dict[str, str] | None = None,
    limit_text: str = "",
) -> BookPlay:
    try:
        done = run_tool(argv, cwd=cwd, env={**BOOK_ENV, **(held or {})}, timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        printed = _tail(_printed(expired.stdout) + _printed(expired.stderr))
        minutes = int((timeout or 0) // 60)
        return BookPlay(
            exit_code=TIMEOUT_EXIT,
            output=f"{limit_text or f'the play did not end within {minutes} minutes'}\n{printed}".strip(),
            timed_out=True,
        )
    return BookPlay(exit_code=done.returncode, output=_tail(done.stdout + done.stderr))


def _check_argv(module: str, app: str) -> list[str]:
    return [sys.executable, "-m", "ostler.book", "check", module, "--app", app]


def _stale_argv(module: str, app: str, since: str = "", story: str = "") -> list[str]:
    argv = [sys.executable, "-m", "ostler.book", "stale", module, "--app", app]
    argv = [*argv, "--since", since] if since else argv
    return [*argv, "--story", story] if story else argv


def _verified_argv(module: str, app: str, story: str = "") -> list[str]:
    argv = [sys.executable, "-m", "ostler.book", "verified", module, "--app", app]
    return [*argv, "--story", story] if story else argv


def _bullets(report: str) -> list[tuple[str, str]]:
    section = ""
    found: list[tuple[str, str]] = []
    for line in report.splitlines():
        if line.startswith("## "):
            section = line.strip()
        elif section and section != DECISIONS_SECTION and line.startswith("- "):
            found.append((section, line.partition(" (")[0]))
    return found


def _names_a_change(report: str) -> bool:
    return any(section in CHANGE_SECTIONS for section, _ in _bullets(report))


def _entries(report: str) -> set[str]:
    return {entry for _, entry in _bullets(report)}


def _booked_services(root: Path, package: str) -> list[str]:
    folder = root / books.package_folder(package)
    if not folder.is_dir():
        return []
    return [found.name for found in sorted(folder.iterdir()) if found.is_dir() and book_modules(root, package, found.name)]


@blueprint.node
def touched_services(logger: logging.Logger, base: str, repo_dir: str = "", story: str = "") -> CoveredServices:
    """Every service with a book under the book root whose app source the commits since `base` changed, or added a file no element names."""
    root = find_book_root(repo_dir)
    app = str(find_repo_root(repo_dir))
    package = find_book_package(repo_dir)
    touched: list[str] = []
    for name in _booked_services(root, package):
        for module in book_modules(root, package, name):
            done = run_tool(_stale_argv(module, app, base, story), cwd=root, env=BOOK_ENV)
            if done.returncode == STALE_EXIT and _names_a_change(done.stdout):
                touched.append(name)
                break
            if done.returncode not in (0, STALE_EXIT, 2):
                logger.warning("book stale of %s exited %d: %s", module, done.returncode, _tail(done.stdout + done.stderr))
    if story:
        logger.info("the commits of story %s reach the book of %d service(s): %s", story, len(touched), ", ".join(touched))
    else:
        logger.info("the diff since %s reaches the book of %d service(s): %s", base, len(touched), ", ".join(touched))
    return CoveredServices(services=touched)


def _story_base(logger: logging.Logger, repo_dir: str, story_slug: str, story_id: str) -> str:
    refs = tuple(dict.fromkeys(ref for ref in (story_id, story_slug) if ref))
    if not refs:
        logger.info("no story reference to find a base from")
        return ""
    try:
        return story_base(find_repo_root(repo_dir), refs)
    except (GitError, ValueError) as exc:
        logger.info("no story base: %s", exc)
        return ""


def _story_with_commits(logger: logging.Logger, app: str, story: str, base: str) -> str:
    if _commits_of(logger, app, story, base):
        return story
    logger.info("no commit carries 'Story: %s'; the covered books read the range since %s", story, base)
    return ""


@blueprint.node
def covered_services(
    logger: logging.Logger,
    services: list[str] | None = None,
    repo_dir: str = "",
    story_slug: str = "",
    story_id: str = "",
) -> CoveredServices:
    """The story's services that have an executable book under the book root, then every other service with a book whose app source the story's commits changed."""
    root = find_book_root(repo_dir)
    package = find_book_package(repo_dir)
    covered = [name for name in services or [] if book_modules(root, package, name)]
    declared = len(covered)
    base = _story_base(logger, repo_dir, story_slug, story_id)
    if base:
        story = _story_with_commits(logger, str(find_repo_root(repo_dir)), story_id or story_slug, base)
        covered += [name for name in touched_services(logger, base, repo_dir, story).services if name not in covered]
    logger.info(
        "%d of %d story service(s) have an executable book, %d more reached by the diff",
        declared, len(services or []), len(covered) - declared,
    )
    return CoveredServices(services=covered)


@blueprint.node
def book_check(logger: logging.Logger, service: str, repo_dir: str = "") -> BookPlay:
    """Build everything each module of the service's book declares, with no stack, and return the first red exit code and output tail."""
    root = find_book_root(repo_dir)
    app = str(find_repo_root(repo_dir))
    package = find_book_package(repo_dir)
    play = BookPlay(exit_code=0, output="")
    for module in book_modules(root, package, service):
        play = _play(_check_argv(module, app), root)
        logger.info("book check of %s exited %d", module, play.exit_code)
        if play.exit_code != 0:
            return BookPlay(exit_code=play.exit_code, output=f"{module}:\n{play.output}")
    return play


@blueprint.node
def stamp_books_verified(
    logger: logging.Logger,
    services: list[str],
    story_slug: str = "",
    story_id: str = "",
    repo_dir: str = "",
) -> BookPlay:
    """Record the app's HEAD as the verified commit of each covered service's book that was current when the story started. A book already current, a book with no verified commit and a book behind before the story are left alone. The first refusal comes back with its output."""
    root = find_book_root(repo_dir)
    app = str(find_repo_root(repo_dir))
    package = find_book_package(repo_dir)
    base = _story_base(logger, repo_dir, story_slug, story_id)
    story = story_id or story_slug
    commits = _commits_of(logger, app, story, base)
    if commits:
        logger.info("the stamp reads the %d commit(s) of story %s", len(commits), story)
    else:
        story = ""
        logger.info("no commit carries 'Story: %s'; the stamp reads the range since the verified commit", story_id or story_slug)
    for name in services:
        for module in book_modules(root, package, name):
            pending = run_tool(_stale_argv(module, app), cwd=root, env=BOOK_ENV)
            if pending.returncode == 0:
                logger.info("the book of %s is current, nothing to stamp", module)
                continue
            if pending.returncode == UNVERIFIED_EXIT and pending.stdout.startswith("not verified"):
                logger.info("the book of %s has no verified commit and belongs to the book-writing flow", module)
                continue
            if pending.returncode != STALE_EXIT:
                return BookPlay(exit_code=pending.returncode, output=f"{module}:\n{_tail(pending.stdout + pending.stderr)}")
            if not base:
                logger.info("the book of %s is not stamped: no story base to tell the story's commits from older ones", module)
                continue
            since = run_tool(_stale_argv(module, app, base), cwd=root, env=BOOK_ENV)
            if since.returncode not in (0, STALE_EXIT) or not _entries(pending.stdout) <= _entries(since.stdout):
                logger.info("the book of %s was behind before the story and is left to the catch-up flow", module)
                continue
            play = _play(_verified_argv(module, app, story), root)
            logger.info("book verified of %s exited %d", module, play.exit_code)
            if play.exit_code == 0 and play.output.startswith("not stamped"):
                logger.info("the book of %s is not stamped: %s", module, play.output.splitlines()[0])
                continue
            if play.exit_code != 0:
                return BookPlay(exit_code=play.exit_code, output=f"{module}:\n{play.output}")
    return BookPlay(exit_code=0, output="")


@blueprint.node
def verify_book_spec(
    logger: logging.Logger,
    services: list[str],
    author_status: str = "blocked",
    repo_dir: str = "",
) -> DocumentationGate:
    """Gate the spec pass of covered services: it ends when `ostler book check` exits 0 for each. A claim red against the app is expected before the build and is not read here."""
    root = find_book_root(repo_dir)
    app = str(find_repo_root(repo_dir))
    package = find_book_package(repo_dir)
    problems: list[str] = []
    failures: list[str] = []
    if author_status not in {"documented", "not_required"}:
        problems.append(f"the spec turn's status is {author_status!r}")
        failures.append("S:author-status")
    for name in services:
        for module in book_modules(root, package, name):
            play = _play(_check_argv(module, app), root)
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
    root = find_book_root(repo_dir)
    excused = untouched_since(root, tuple(preexisting or ()))
    package = find_book_package(repo_dir)
    prefixes = tuple(book_dir(package, name) + "/" for name in services)
    found = [
        rel for rel in uncommitted_paths(root) if rel.startswith(prefixes) and rel not in excused
    ]
    logger.info("the spec pass changed %d book path(s)", len(found))
    return BookPaths(paths=found)


SHARED_EXEMPT_FILES = frozenset({"index.tsv", "DISAGREEMENTS.md", "WALLS.md", "UNDERSPECIFIED.md", "VERIFIED"})


def shared_book_paths(folder: str, changed: dict[str, bool], surfaces: frozenset[str] = frozenset()) -> list[str]:
    """The changed paths under a service's book that other claims depend on, from `{path: added in this pass}`.

    A new journey file states one more claim and no other journey reads it, so a targeted play of
    the named calls judges it. An edit to an existing journey, to the model, the fixtures, the
    backstage or any other file of the book can move the answer of a call this pass never named,
    so only a play of the whole book judges it. The index, the disagreement and wall notes, the
    register of underspecified fields, the verified stamp and the decisions are records about the
    book that no play reads. In a book with several surfaces, each surface folder in `surfaces`
    holds the same kinds of file, and the shared model beside them is shared.
    """
    prefix = folder + "/"
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
    root = find_book_root(repo_dir)
    excused = untouched_since(root, tuple(preexisting or ()))
    package = find_book_package(repo_dir)
    folder = book_dir(package, service)
    prefix = folder + "/"
    changed = {
        rel: _added_in_pass(root, rel)
        for rel in uncommitted_paths(root)
        if rel.startswith(prefix) and rel not in excused
    }
    base = f"{package}.{service}"
    surfaces = frozenset(_surface(module, base) for module in book_modules(root, package, service)) - {""}
    shared = shared_book_paths(folder, changed, surfaces)
    logger.info(
        "the pass changed %d path(s) of %s, %d of them shared: %s book",
        len(changed), service, len(shared), "whole" if shared else "named-call",
    )
    return BookScope(whole=bool(shared), shared=shared, changed=len(changed))


@blueprint.node
def story_base_of(logger: logging.Logger, story_slug: str = "", story_id: str = "", repo_dir: str = "") -> StoryBase:
    """The commit the story's own work started from, or an empty base when none is found."""
    return StoryBase(base=_story_base(logger, repo_dir, story_slug, story_id))


def _affected_argv(module: str, app: str, since: str, out: str, story: str = "") -> list[str]:
    argv = [sys.executable, "-m", "ostler.book", "affected", module, "--app", app]
    if since:
        argv += ["--since", since]
    if story:
        argv += ["--story", story]
    return argv + ["--out", out]


def _commits_of(logger: logging.Logger, app: str, story: str, since: str) -> list[str]:
    if not story:
        return []
    try:
        return story_commits(app, story, since or None)
    except subprocess.CalledProcessError as exc:
        logger.info("the commits of story %s could not be read: %s", story, exc)
        return []


def owed_summary(reasons: list[str], cap: int = OWED_CAP) -> str:
    kept = "; ".join(reasons[:cap])
    return f"{kept}; and {len(reasons) - cap} more" if len(reasons) > cap else kept


def _affected_report(folder: Path, service: str, multi: bool) -> dict[str, Any] | None:
    found = sorted(folder.glob("*-affected.json")) if multi else [folder / f"{service}-affected.json"]
    for path in found:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _uncovered_entry(item: dict[str, str]) -> str:
    return f"{item['path']}::{item['function']}" if item.get("function") else item["path"]


@blueprint.node
def book_plan(
    logger: logging.Logger,
    service: str,
    spec_dir: str,
    story_slug: str = "",
    story_id: str = "",
    repo_dir: str = "",
) -> BookPlan:
    """Select what to play for one service from the story's diff of the code and of the book with `ostler book affected`, merged over the modules of the book. Nothing needs a running app."""
    root = find_book_root(repo_dir)
    app = str(find_repo_root(repo_dir))
    since = _story_base(logger, repo_dir, story_slug, story_id)
    story = story_id or story_slug
    commits = _commits_of(logger, app, story, since)
    if commits:
        logger.info("the selection of %s reads the %d commit(s) of story %s", service, len(commits), story)
    else:
        story = ""
        logger.info(
            "no commit carries 'Story: %s'; the selection of %s reads the range since %s",
            story_id or story_slug, service, since or "the verified commit",
        )
    package = find_book_package(repo_dir)
    modules = book_modules(root, package, service) or (f"{package}.{service}",)
    multi = len(modules) > 1
    out = Path(spec_dir) / BOOK_OUT
    kind: Literal["none", "empty", "partial", "whole"] = "none"
    only: list[str] = []
    by_journey: list[str] = []
    direct = True
    direct_journeys: list[str] = []
    direct_only: list[str] = []
    reached_calls = reached_journeys = 0
    causes: dict[str, list[int]] = {}
    read_any = False
    reasons: list[str] = []
    owed_reasons: list[str] = []
    reads: list[str] = []
    uncovered: list[str] = []
    changed = not_judged = exit_code = 0
    outputs: list[str] = []
    for module in modules:
        folder = out / module if multi else out
        for stale in folder.glob("*-affected.json") if multi else [folder / f"{service}-affected.json"]:
            stale.unlink(missing_ok=True)
        play = _play(_affected_argv(module, app, since, str(folder), story), root)
        logger.info("book affected of %s exited %d", module, play.exit_code)
        outputs.append(f"{module}:\n{play.output}" if multi else play.output)
        if play.exit_code == 2:
            exit_code = 2
            continue
        report = _affected_report(folder, service, multi)
        if report is None:
            exit_code = 2
            continue
        module_kind = cast(Literal["none", "empty", "partial", "whole"], str(report.get("plan", "none")))
        if PLAN_STRENGTH.index(module_kind) > PLAN_STRENGTH.index(kind):
            kind = module_kind
        only += [call for call in report.get("only", []) if call not in only]
        by_journey += [title for title in report.get("by_journey", []) if title not in by_journey]
        read_any = True
        direct = direct and "direct_journeys" in report
        direct_journeys += [title for title in report.get("direct_journeys", []) if title not in direct_journeys]
        direct_only += [call for call in report.get("direct_only", []) if call not in direct_only]
        reached = report.get("reached") or {}
        reached_calls += int(reached.get("calls", 0))
        reached_journeys += int(reached.get("journeys", 0))
        for cause in reached.get("causes", []):
            total = causes.setdefault(str(cause["cause"]), [0, 0])
            total[0] += int(cause["calls"])
            total[1] += int(cause["journeys"])
        if report.get("reason") and report["reason"] not in reasons:
            reasons.append(str(report["reason"]))
        owed_reasons += [
            str(why)
            for why in report.get("owed") or ([report["reason"]] if report.get("reason") else [])
        ]
        seen = report.get("commits") or [commit[:7] for commit in commits]
        read = (
            f"story {story}: {len(seen)} commit(s), {seen[0]} to {seen[-1]}"
            if story and seen
            else f"the range since {since or 'the verified commit'}"
        )
        if read not in reads:
            reads.append(read)
        uncovered += [_uncovered_entry(item) for item in report.get("uncovered", [])]
        diff = report.get("diff", {})
        unjudged = int(diff.get("not_computed", {}).get("count", 0))
        not_judged += unjudged
        changed += int(diff.get("app_files", 0)) + int(diff.get("book_files", 0)) + unjudged
    direct = direct and read_any
    top = sorted(causes.items(), key=lambda item: (-item[1][0], -item[1][1], item[0]))[:REACHED_CAUSE_CAP]
    logger.info(
        "book plan of %s: %s, %d call(s), %d journey(s), %d direct call(s), %d direct journey(s), %d uncovered",
        service, kind, len(only), len(by_journey), len(direct_only), len(direct_journeys), len(uncovered),
    )
    return BookPlan(
        service=service,
        plan=kind,
        only=only,
        by_journey=by_journey,
        direct=direct,
        direct_journeys=direct_journeys,
        direct_only=direct_only,
        reached_calls=reached_calls,
        reached_journeys=reached_journeys,
        reached_causes=[f"{cause} ({c} calls, {j} journeys)" for cause, (c, j) in top],
        whole=kind == "whole",
        reason="; ".join(reasons),
        owed_reasons=list(dict.fromkeys(owed_reasons)),
        read="; ".join(reads),
        uncovered=uncovered,
        changed=changed,
        not_judged=not_judged,
        exit_code=exit_code,
        output=_tail("\n".join(outputs)),
    )


@blueprint.node
def write_qa_plan(
    logger: logging.Logger,
    spec_dir: str,
    plans: list[BookPlan],
    exits: dict[str, int] | None = None,
) -> BookPlay:
    """Write `qa-plan.md` in the spec dir from the plans the book selected and the exit of each play, with no agent involved."""
    exits = exits or {}
    lines = ["# QA plan", "", WHOLE_PLAYS_NEVER_RUN, ""]
    for plan in plans:
        lines += [f"## {plan.service}", "", f"- plan: {plan.plan}"]
        if plan.read:
            lines.append(f"- change read: {plan.read}")
        lines += [
            f"- calls: {', '.join(plan.direct_only if plan.direct else plan.only) or 'none'}",
            f"- journeys: {', '.join(plan.direct_journeys if plan.direct else plan.by_journey) or 'none'}",
            f"- uncovered: {', '.join(plan.uncovered) or 'none'}",
            f"- changed files: {plan.changed}",
            f"- files not judged: {plan.not_judged}",
            f"- play exit: {exits[plan.service] if plan.service in exits else 'not played'}",
        ]
        if plan.direct:
            if plan.cut:
                lines.append(f"- owed: {plan.cut}")
            if plan.reached_calls or plan.reached_journeys:
                reached = f"- reached beyond the direct selection, owed to the scheduled whole play: {plan.reached_calls} calls, {plan.reached_journeys} journeys"
                if plan.reached_causes:
                    reached += "; top causes: " + ", ".join(plan.reached_causes)
                lines.append(reached)
        if plan.owed:
            lines.append(f"- owed to the scheduled whole play: {plan.owed}")
        lines.append("")
    target = Path(spec_dir) / PLAN_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote the QA plan of %d service(s) to %s", len(plans), target)
    return BookPlay(exit_code=0, output=str(target))


@blueprint.node
def book_run(
    logger: logging.Logger,
    service: str,
    only: list[str],
    copy: str,
    out_dir: str,
    limit_minutes: int,
    journeys: list[str] | None = None,
    fresh: bool = False,
    repo_dir: str = "",
    direct: bool = False,
) -> BookPlay:
    """Play the named calls of the service's book against the run's copy of the stack. Named journeys are a separate play, because `--only` and `--journey` combine as AND in one run: after the calls, or before them when `direct`. One budget of `limit_minutes` minutes covers every play of the service, and a play still running when it is spent is killed and exits 3. The first play of the service reloads the data when `fresh`. A direct calls play cut at the limit after green journeys comes back green with the cut in `owed`."""
    root = find_book_root(repo_dir)
    package = find_book_package(repo_dir)
    modules = book_modules(root, package, service) or (f"{package}.{service}",)
    wanted = list(journeys or [])
    if not only and not wanted:
        return BookPlay(exit_code=0, output="nothing selected to play")
    laps = [([], wanted), (only, [])] if direct else [(only, []), ([], wanted)]
    laps = [(calls, titles) for calls, titles in laps if calls or titles]
    budget = limit_minutes * 60
    spent = 0.0
    journeys_green = False
    limit_text = (
        f"the play of {service} did not end within {limit_minutes} minutes: "
        f"the story's plays are limited to {limit_minutes} minutes (book_play_minutes)"
    )
    reload = fresh
    outputs: list[str] = []
    for named_calls, titles in laps:
        for module in modules:
            if len(modules) == 1:
                named, target = named_calls, out_dir
            else:
                claims = _calls_by_module(root, modules)
                named = [call for call in named_calls if call in claims[module] or (module == modules[0] and not any(call in held for held in claims.values()))]
                if named_calls and not named:
                    continue
                target = str(Path(out_dir) / module)
            if titles:
                target = str(Path(target) / "journeys")
            argv = _run_argv(module, named, copy, target, journeys=titles, fresh=reload)
            reload = False
            left = budget - spent
            if left <= 0:
                play = BookPlay(exit_code=TIMEOUT_EXIT, output=limit_text, timed_out=True)
            else:
                began = _now()
                play = _play(argv, find_repo_root(repo_dir), left, stack_env(root, lease=copy, repo_dir=repo_dir), limit_text)
                spent += _now() - began
            what = f"{len(named)} call(s)" if named else f"{len(titles)} journey(s)"
            logger.info("book run of %s over %s exited %d", module, what, play.exit_code)
            if play.exit_code != 0:
                if direct and named_calls and journeys_green and play.timed_out:
                    logger.warning("the direct calls of %s did not finish within %d minutes after green journeys", service, limit_minutes)
                    return BookPlay(
                        exit_code=0,
                        output=_tail("\n".join([*outputs, play.output])),
                        owed=f"the direct calls did not finish within {limit_minutes} min",
                    )
                return play if len(modules) == 1 else BookPlay(exit_code=play.exit_code, output=f"{module}:\n{play.output}")
            outputs.append(play.output if len(modules) == 1 else f"{module}:\n{play.output}")
        if titles:
            journeys_green = True
    return BookPlay(exit_code=0, output=_tail("\n".join(outputs)))


def _run_argv(
    module: str,
    only: list[str],
    copy: str,
    out_dir: str,
    journeys: list[str] | None = None,
    fresh: bool = False,
) -> list[str]:
    argv = [sys.executable, "-m", "ostler.book", "run", module]
    if fresh:
        argv += ["--fresh-data"]
    if only:
        argv += ["--only", ",".join(only)]
    elif journeys:
        argv += ["--partial"]
        for title in journeys:
            argv += ["--journey", title]
    return argv + ["--copy", copy, "--out", out_dir]


def _calls_by_module(root: Path, modules: tuple[str, ...]) -> dict[str, frozenset[str]]:
    held: dict[str, frozenset[str]] = {}
    for module in modules:
        index = root / Path(*module.split(".")) / INDEX_FILE
        text = index.read_text(encoding="utf-8") if index.is_file() else ""
        held[module] = frozenset(entry.name for entry in parse_index(text) if entry.kind in ("endpoint", "interaction"))
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
    unobserved: list[ReviewVerdict] | None = None,
) -> BookQaRecord:
    """Record the calls a passed check played, the findings it stood on and the claims the book could not state, so a second visit for the story replays them. A green replay means a declared defect still holds, so its finding still stands."""
    record = BookQaRecord(services=services, findings=findings or [], unreached=unreached or [], unobserved=unobserved or [])
    target = Path(spec_dir) / RECORD_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.model_dump(exclude_defaults=True), indent=2) + "\n", encoding="utf-8")
    logger.info("recorded the calls of %d service(s) in %s", len(services), target)
    return record


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


@blueprint.node
def write_qa_review(
    logger: logging.Logger, spec_dir: str, criteria: list[str], verdicts: list[ReviewVerdict]
) -> BookPlay:
    """Write `qa-review.md` in the spec dir from the end review's verdicts, one row per acceptance criterion, with no agent involved."""
    held = by_criterion(verdicts, len(criteria))
    rows = [
        f"| {n}. {_cell(text)} | {held[n].verdict if n in held else 'none'} | {_cell(held[n].evidence) if n in held else ''} |"
        for n, text in enumerate(criteria, 1)
    ]
    lines = ["# QA review", "", "| criterion | verdict | evidence |", "| --- | --- | --- |", *rows]
    target = Path(spec_dir) / REVIEW_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("wrote the end review of %d criteria to %s", len(criteria), target)
    return BookPlay(exit_code=0, output=str(target))


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
    book = find_book_root(repo_dir)
    code = find_repo_root(repo_dir)
    package = find_book_package(repo_dir)
    folders = [(book / book_dir(package, name)).resolve() for name in services]
    imported = {path for name in services for path in outside_paths(book, f"{package}.{name}")}
    excluded = not_product_roots(repo_dir)
    inside: list[str] = []
    stray: list[str] = []
    for root in dict.fromkeys((book, code)):
        excused = untouched_since(root, tuple(preexisting or ()))
        for rel in uncommitted_paths(root):
            if rel in excused or paths.is_gate_context(rel) or is_compiled(rel):
                continue
            if root == book and (rel in imported or any((root / rel).resolve().is_relative_to(folder) for folder in folders)):
                inside.append(rel)
            elif is_product(root, rel, excluded):
                stray.append(rel)
    if stray:
        listing = "\n".join(f"- `{rel}`" for rel in stray)
        return StoryCommitted(
            refused=(
                "These paths changed outside the covered services' books, and the book pass may "
                f"edit only under {', '.join(book_dir(package, n) + '/' for n in services)}:\n\n{listing}\n\n"
                "Restore each one."
            )
        )
    if not inside:
        logger.info("the book pass left no uncommitted book path for %s", slug)
        return StoryCommitted()
    if not (book / ".git").exists():
        logger.info("no .git at %s, nothing to commit", book)
        return StoryCommitted()
    message = commits.message(
        "test",
        commits.scope(find_docs_root(repo_dir).name),
        f"play {slug} in the service book",
        epic=epic,
        story=story_id or slug,
    )
    try:
        landed = commit_paths(book, message, *inside, verify=False)
    except GitError as exc:
        listing = ", ".join(f"`{rel}`" for rel in inside)
        return StoryCommitted(refused=f"git refused the commit for {slug} in {book} of {listing}: {exc}")
    left = left_behind_refusal(left_behind(book, sorted(imported)))
    if left:
        return StoryCommitted(committed=landed, refused=left)
    logger.info("committed %d service book path(s) for %s", len(inside), slug)
    return StoryCommitted(committed=landed)


__all__ = [
    "BOOK_OUT",
    "RECORD_FILE",
    "REVIEW_FILE",
    "UNREACHED_FILE",
    "PLAN_FILE",
    "book_check",
    "book_dir",
    "book_plan",
    "changed_book_paths",
    "verify_book_spec",
    "book_modules",
    "book_run",
    "book_scope",
    "commit_service_book",
    "covered_services",
    "read_book_record",
    "shared_book_paths",
    "stamp_books_verified",
    "story_base_of",
    "touched_services",
    "write_book_record",
    "write_qa_plan",
    "write_qa_review",
    "write_unreached_claims",
]
