"""The doctor-gated in-process stamp step (`main/nodes/finalize.py::stamp_turn`)."""
from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from ostler import Ostler
from ostler import doctor as doctor_mod
from ostler import stamp as stamp_mod
from workhorse_workflows.kit import head_sha
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.main.nodes.finalize import stamp_turn

from okf_builder.conftest import CONCEPT, SERVICE

CHARGE_PAGE = f"docs/features/{SERVICE}/concepts/charge.md"
DIGEST_RE = re.compile(r"@[0-9a-f]{12}\b")


def _features_root(book: Path) -> str:
    return str(paths.features_root(book, SERVICE))


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "commit", "-qm", message], cwd=repo, check=True, stdout=subprocess.DEVNULL
    )


def test_a_node_the_turn_touched_gets_its_unstamped_target_stamped(
    booked: Path, logger: logging.Logger
) -> None:
    pre_turn_sha = head_sha(booked)
    page = booked / CHARGE_PAGE
    page.write_text(page.read_text().replace("Charging.", "Charging, in cents."))

    result = stamp_turn(logger, str(booked), _features_root(booked), pre_turn_sha)

    assert result.stamped == 1
    assert not result.skipped_nodes
    assert DIGEST_RE.search(page.read_text())


def test_only_the_edited_node_on_a_shared_page_gets_stamped(
    booked: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    """Two nodes share a page; only the one the turn actually edited earns a stamp."""
    source = booked / "acme/service.py"
    source.write_text(
        source.read_text() + "\n\ndef refund(amount):\n    \"\"\"Refund an amount.\"\"\"\n    return -amount\n"
    )
    two_node_page = write(
        booked / f"docs/features/{SERVICE}/concepts/two.md",
        "---\ntype: format\nslug: two\ntitle: Two\n---\n"
        "# Two\n\n"
        "## Methods\n\n"
        "### alpha does something\n"
        "- code: `acme/service.py::charge`\n\n"
        "Alpha prose.\n\n"
        "### beta does something else\n"
        "- code: `acme/service.py::refund`\n\n"
        "Beta prose.\n",
    )
    _commit(booked, "a page with two nodes, both unstamped")
    pre_turn_sha = head_sha(booked)
    two_node_page.write_text(
        two_node_page.read_text().replace("Alpha prose.", "Alpha prose, in cents.")
    )

    result = stamp_turn(logger, str(booked), _features_root(booked), pre_turn_sha)

    assert result.stamped == 1
    assert not result.skipped_nodes
    lines = two_node_page.read_text().splitlines()
    beta_index = next(i for i, line in enumerate(lines) if line.startswith("### beta"))
    alpha_bullet = next(line for line in lines[:beta_index] if "code:" in line)
    beta_bullet = next(line for line in lines[beta_index:] if "code:" in line)
    assert DIGEST_RE.search(alpha_bullet)
    assert "@" not in beta_bullet


def test_an_untouched_page_earns_no_stamp(booked: Path, logger: logging.Logger) -> None:
    """A page the turn never edited never appears in the book-pathspec diff."""
    pre_turn_sha = head_sha(booked)

    result = stamp_turn(logger, str(booked), _features_root(booked), pre_turn_sha)

    assert result.stamped == 0
    assert not result.skipped_nodes
    assert "@" not in (booked / CHARGE_PAGE).read_text()


def test_restamp_row_stamps_only_its_own_pair(
    booked: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    """A `fix:stale-citation` row names exactly the `(node, file)` pairs it was assigned."""
    write(
        booked / f"docs/features/{SERVICE}/concepts/other.md",
        CONCEPT.format(slug="other", title="Other", symbol="charge", prose="Also charging."),
    )
    _commit(booked, "a second node citing the same symbol")
    pre_turn_sha = head_sha(booked)

    context = json.dumps({"file": "acme/service.py", "nodes": [CHARGE_PAGE]})
    result = stamp_turn(
        logger, str(booked), _features_root(booked), pre_turn_sha,
        "fix:stale-citation", context,
    )

    assert result.stamped == 1
    assert DIGEST_RE.search((booked / CHARGE_PAGE).read_text())
    other_page = booked / f"docs/features/{SERVICE}/concepts/other.md"
    assert "@" not in other_page.read_text()


def test_restamp_row_clears_its_own_stale_citation(
    booked: Path, logger: logging.Logger
) -> None:
    """The stale-citation error a row exists to fix must not block that row's own restamp."""
    features_root = Path(_features_root(booked))
    graph = Ostler(booked).graph
    stamp_mod.stamp_targets(graph, features_root, [(CHARGE_PAGE, "acme/service.py")])
    _commit(booked, "stamp the citation")

    source = booked / "acme/service.py"
    source.write_text(source.read_text().replace("return amount", "return amount * 100"))
    _commit(booked, "change the cited file")

    before = (booked / CHARGE_PAGE).read_text()
    stale_digest = DIGEST_RE.search(before)
    assert stale_digest is not None

    pre_turn_sha = head_sha(booked)
    context = json.dumps({"file": "acme/service.py", "nodes": [CHARGE_PAGE]})

    result = stamp_turn(
        logger, str(booked), _features_root(booked), pre_turn_sha,
        "fix:stale-citation", context,
    )

    assert result.stamped == 1
    assert not result.skipped_nodes
    after = (booked / CHARGE_PAGE).read_text()
    assert DIGEST_RE.search(after)
    assert stale_digest.group() not in after

    report = doctor_mod.run(Ostler(booked).graph)
    assert not any(f.code == "stale-citation" for f in report.findings)


def test_a_partial_turn_does_not_restamp_its_regrounding_row(
    booked: Path, logger: logging.Logger
) -> None:
    """A `partial` turn never re-read the citation; marking it fresh would hide that gap."""
    pre_turn_sha = head_sha(booked)
    context = json.dumps({"file": "acme/service.py", "nodes": [CHARGE_PAGE]})

    result = stamp_turn(
        logger, str(booked), _features_root(booked), pre_turn_sha,
        "fix:stale-citation", context, "partial",
    )

    assert result.stamped == 0
    assert "@" not in (booked / CHARGE_PAGE).read_text()


def test_a_node_with_its_own_error_is_withheld(
    booked: Path, logger: logging.Logger, write: Callable[[Path, str], Path]
) -> None:
    """A node `doctor` already flags as broken cannot also be asserted current."""
    write(
        booked / f"docs/features/{SERVICE}/concepts/refund.md",
        CONCEPT.format(slug="refund", title="Refund", symbol="refund", prose="Refunding."),
    )
    _commit(booked, "a doc citing a symbol nothing declares")
    pre_turn_sha = head_sha(booked)
    page = booked / f"docs/features/{SERVICE}/concepts/refund.md"
    page.write_text(page.read_text().replace("Refunding.", "Refunding, in cents."))

    result = stamp_turn(logger, str(booked), _features_root(booked), pre_turn_sha)

    assert result.stamped == 0
    assert result.skipped_nodes == [f"docs/features/{SERVICE}/concepts/refund.md"]
    assert "@" not in page.read_text()


def test_nothing_to_stamp_is_a_quiet_no_op(booked: Path, logger: logging.Logger) -> None:
    result = stamp_turn(logger, str(booked), _features_root(booked), "")

    assert result.stamped == 0
    assert result.skipped_nodes == []
