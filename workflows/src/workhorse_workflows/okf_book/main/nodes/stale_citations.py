"""The citations of a book whose cited file changed since its stamp, grouped by the file and the version each was stamped on, and what one reading of the change settles for them.

A stamp is the digest of the whole cited file, because a change anywhere in a file can change
what a cited symbol means. So a changed file is read once, as the diff from the version the
citations were stamped on, and the reading names the nodes whose claims the change bears on.
Those go to a page repair with what it said. The rest still hold, and are stamped on the file
as it is now.
"""
from __future__ import annotations

import difflib
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from ostler import doctor, index
from ostler.model import load
from ostler.refs import parse_code_ref
from ostler.stamp import digest_file, stamp_targets
from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.source_view import turn_folder
from workhorse_workflows.okf_book.shared.citations import book_pages
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.page_check import PageProblem

STALE_CODE = "stale-citation"
OLD_VERSIONS = "reground"
DIFF_LINES_SHOWN = 400
HISTORY_DEPTH = 200
_GIT_TIMEOUT = 60
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

type Failures = dict[str, tuple[PageProblem, ...]]


class StaleNode(BaseModel):
    """One node that cites a changed file, the page it sits on and the symbol it cites, if any."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node: str
    page: str
    symbol: str = ""


class StaleFile(BaseModel):
    """One cited file that changed, the digest its citations carry, and every node that cites it on that digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    digest: str
    nodes: tuple[StaleNode, ...] = ()


class AffectedNode(BaseModel):
    """One numbered node the change bears on, and what its page repair must check or correct."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    node: int
    instruction: str = ""


class RegroundVerdict(BaseModel):
    """The reading's reply: the nodes the change bears on. A node it leaves out still holds."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    affected: tuple[AffectedNode, ...] = ()


class Regrounded(BaseModel):
    """What regrounding a book left: the page problems of the nodes a change bears on, and how many citations were stamped again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    failures: Failures = {}
    stamped: int = 0


def stale_files(root: Path, service: str) -> tuple[StaleFile, ...]:
    """Every changed file the service's book cites, with the nodes citing it, in the order of the file's path."""
    pages = [page.relative_to(root).as_posix() for page in book_pages(root, service)]
    if not pages:
        return ()
    with index.session(root):
        report = doctor.scope_to_paths(doctor.run(load(root)), pages)
    grouped: dict[tuple[str, str], list[StaleNode]] = {}
    for finding in report.findings:
        if finding.code != STALE_CODE or not finding.node:
            continue
        try:
            ref = parse_code_ref(finding.ref)
        except ValueError:
            continue
        if ref.digest is None or ref.repository:
            continue
        cited = StaleNode(node=finding.node, page=finding.path, symbol=ref.symbol)
        nodes = grouped.setdefault((ref.path, ref.digest), [])
        if cited not in nodes:
            nodes.append(cited)
    return tuple(StaleFile(path=path, digest=digest, nodes=tuple(nodes)) for (path, digest), nodes in sorted(grouped.items()))


def _git_bytes(root: Path, *args: str) -> bytes | None:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=_GIT_TIMEOUT, check=False)
    return done.stdout if done.returncode == 0 else None


def stamped_text(root: Path, path: str, digest: str) -> str | None:
    """The text of *path* as its history last held it on *digest*, or nothing when no commit of the last ones holds that version."""
    log = _git_bytes(root, "log", f"--max-count={HISTORY_DEPTH}", "--format=%H", "--", path)
    for commit in (log or b"").decode().split():
        blob = _git_bytes(root, "show", f"{commit}:{path}")
        if blob is not None and digest_file(blob) == digest:
            return blob.decode("utf-8", errors="replace")
    return None


def keep_old_version(root: Path, stale: StaleFile, old: str) -> Path:
    """Write the stamped version in the working tree, where a confined reading turn can open it whole."""
    kept = turn_folder(root, OLD_VERSIONS) / f"{_UNSAFE.sub('-', stale.path)}@{stale.digest}"
    _ = kept.write_text(old, encoding="utf-8")
    return kept


def reground_template_args(root: Path, stale: StaleFile, old: str, kept: Path) -> dict[str, object]:
    """What the reading turn is shown: the file, the head of its diff from the stamped version, where that version is kept, and each citing node with its number."""
    current = (root / stale.path).read_text(encoding="utf-8", errors="replace")
    diff = list(difflib.unified_diff(old.splitlines(), current.splitlines(), "stamped", "now", lineterm=""))
    return {
        "path": stale.path,
        "diff": "\n".join(diff[:DIFF_LINES_SHOWN]),
        "diff_left": max(0, len(diff) - DIFF_LINES_SHOWN),
        "old_version": str(kept),
        "nodes": [{"number": number, "node": cited.node, "symbol": cited.symbol} for number, cited in enumerate(stale.nodes, start=1)],
    }


def _problem(stale: StaleFile, cited: StaleNode, instruction: str) -> PageProblem:
    told = instruction or "read the file again and correct what this node claims of it"
    return PageProblem(cited.page, f"{cited.node}: `{stale.path}` changed since this node cited it, and the change bears on the node: {told}")


def unread_problems(stale: StaleFile) -> tuple[PageProblem, ...]:
    """Every node of a file whose stamped version no commit holds, so no diff says which the change spares."""
    return tuple(_problem(stale, cited, "") for cited in stale.nodes)


def affected_problems(stale: StaleFile, verdict: RegroundVerdict) -> tuple[PageProblem, ...]:
    """One problem per node the verdict names. A number the file has no node for is dropped, and a node named twice keeps its last instruction."""
    named = {affected.node: affected.instruction for affected in verdict.affected if 1 <= affected.node <= len(stale.nodes)}
    return tuple(_problem(stale, stale.nodes[number - 1], instruction) for number, instruction in sorted(named.items()))


def spared_pairs(stale: StaleFile, verdict: RegroundVerdict) -> tuple[tuple[str, str], ...]:
    """Each node the verdict leaves out, with the file, as the pair its stamp is written by."""
    named = {affected.node for affected in verdict.affected}
    return tuple((cited.node, stale.path) for number, cited in enumerate(stale.nodes, start=1) if number not in named)


def with_problems(failures: Failures, problems: Iterable[PageProblem]) -> Failures:
    """*failures* with each of *problems* added under its page."""
    merged = dict(failures)
    for problem in problems:
        merged[problem.page] = (*merged.get(problem.page, ()), problem)
    return merged


def stamp_spared(root: Path, pairs: Iterable[tuple[str, str]]) -> tuple[tuple[str, ...], int]:
    """Stamp each spared citation on its file as it is now. Returns the pages that changed and how many citations were stamped."""
    wanted = list(pairs)
    if not wanted:
        return (), 0
    with index.session(root):
        results = stamp_targets(load(root), root / FEATURES_DIR, wanted)
    pages = tuple(sorted(result.page for result in results if result.page and result.changed))
    return pages, sum(result.stamped for result in results)
