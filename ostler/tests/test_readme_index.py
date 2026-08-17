"""`ostler/README.md` — what the reader has to be told about the parse index.

The index is on by default, keyed on content rather than time, shared across worktrees
and allowed to decay. None of that is inferable from `--help`: the help text names the
flags, and the flags are the least surprising half. An operator who does not know the
index is content-keyed cannot tell whether a disagreement between two runs is a stale
entry (impossible) or a real regression (the only remaining option), and one who does
not know where the directory comes from cannot copy it into a container.

So these hold the README to the *claims*, not to a layout. Every assertion is either an
identifier that is part of the public contract — the flags, the command, the environment
variable, the config key, the JSON keys, the make target — or a claim checked as a set of
terms co-occurring inside one passage, so the prose is free to be prose.

The one acceptance criterion with no test here is "no code changes; the public-content
sweep passes": `make check-public` is the packet's own verification command, and a test
asserting it would be green before the README exists, which proves nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ostler import index as index_mod

README = Path(__file__).resolve().parents[1] / "README.md"


def readme() -> str:
    return README.read_text(encoding="utf-8")


def flat() -> str:
    """The README as one whitespace-collapsed line, lowercased.

    Claims are checked against this rather than against the raw text so that a sentence
    the author chose to wrap over three lines, or to put in a table cell, still reads as
    one passage.
    """
    return re.sub(r"\s+", " ", readme()).lower()


def near(text: str, *terms: str, window: int = 400) -> bool:
    """Do all *terms* occur inside one *window*-character stretch of *text*?

    A claim is a sentence, not a bag of words scattered over a 500-line document: the
    README already says "cache" and "correctness" somewhere for unrelated reasons. The
    window is what makes "it says X about Y" different from "it says X, and elsewhere Y".
    """
    lowered = [term.lower() for term in terms]
    anchors = [m.start() for m in re.finditer(re.escape(lowered[0]), text)]
    for start in anchors:
        chunk = text[max(0, start - window) : start + window]
        if all(term in chunk for term in lowered[1:]):
            return True
    return False


def any_near(text: str, *groups: str | tuple[str, ...], window: int = 400) -> bool:
    """`near` where each position accepts any one of several spellings.

    "code grounding" and "code-grounding" are the same claim; which one the prose picks is
    the author's business, and a test that forces one is a test about punctuation.
    """
    normalised = tuple((group,) if isinstance(group, str) else group for group in groups)
    for combination in _product(normalised):
        if near(text, *combination, window=window):
            return True
    return False


def _product(groups: tuple[tuple[str, ...], ...]) -> list[tuple[str, ...]]:
    combos: list[tuple[str, ...]] = [()]
    for group in groups:
        combos = [combo + (option,) for combo in combos for option in group]
    return combos


@pytest.fixture(scope="module")
def text() -> str:
    return flat()


# --- what is cached, and what deliberately is not --------------------------------


def test_readme_names_both_cached_products(text: str) -> None:
    """Two products ship, and a reader who knows only about the markdown one will not
    understand why touching a *source* file slows the next doctor down."""
    assert near(text, "parse products", "index"), "the README never names the parse products"
    assert any_near(
        text,
        ("code grounding", "code-grounding"),
        ("symbol table", "symbol tables"),
        ("sha", "digest", "content"),
    ), "the README never says code-grounding symbol tables are cached too"


def test_readme_states_findings_are_not_cached(text: str) -> None:
    """The layer that was deliberately cut. Left unsaid, the next reader assumes doctor's
    verdicts are cached and distrusts the whole thing the first time one changes."""
    assert any_near(text, "findings", ("not cached", "never cached", "no findings", "not itself cached")), (
        "the README does not say findings are not cached"
    )


def test_readme_states_graph_global_checks_are_always_recomputed(text: str) -> None:
    """Reachability and the cross-file constraints cost 0.06s and are never served from
    the index — the single fact that makes the invalidation story small enough to trust."""
    assert any_near(
        text,
        "recomputed",
        ("global", "graph-global", "graph global"),
        ("always", "every run", "never cached"),
    ), "the README does not say the graph-global checks are always recomputed"


# --- location, resolution order and the controls ---------------------------------


def test_readme_documents_the_index_location_and_its_resolution_order(text: str) -> None:
    """An operator warming a container's cache needs every rung of the ladder, in order:
    `--index-dir`, then the environment, then ostler's config, then the shared cache."""
    raw = readme()
    for token in (index_mod.INDEX_DIR_ENV, index_mod.CONFIG_KEY, index_mod.INDEX_DIR_NAME):
        assert token in raw, f"the README never mentions {token}"
    assert "--index-dir" in raw
    assert near(text, "~/.cache/stablemate") or near(text, "stablemate cache"), (
        "the README does not say the index lives under the shared stablemate cache"
    )

    positions = [
        text.index("--index-dir"),
        text.index(index_mod.INDEX_DIR_ENV.lower()),
        text.index(index_mod.CONFIG_KEY.lower()),
        text.index(index_mod.INDEX_DIR_NAME.lower()),
    ]
    assert positions == sorted(positions), (
        "the README mentions the four sources but not in resolution order "
        "(explicit --index-dir, then the environment, then config, then the default)"
    )


def test_readme_documents_the_disable_flag_and_that_the_index_is_on_by_default(text: str) -> None:
    assert "--no-index" in readme(), "the README never mentions --no-index"
    assert any_near(text, "--no-index", ("default", "on by default", "escape hatch")), (
        "the README does not say the index is on by default and --no-index turns it off"
    )


def test_readme_documents_cache_clean_including_removing_everything(text: str) -> None:
    """Both eviction paths — the explicit clean, and `--all` for the whole directory."""
    assert "cache clean" in text, "the README never documents `ostler cache clean`"
    assert near(text, "cache clean", "--all"), (
        "the README does not document `--all` (remove every entry, not only aged-out ones)"
    )


def test_readme_documents_the_verify_mode(text: str) -> None:
    """The mechanism that makes "cached and uncached agree" a command and not a promise."""
    assert "--verify-index" in readme(), "the README never mentions --verify-index"
    assert any_near(
        text,
        "--verify-index",
        ("uncached", "without the index", "both paths"),
        ("agree", "identical", "diff", "compare"),
    ), "the README does not say --verify-index runs both paths and compares the reports"


def test_readme_documents_the_hit_miss_reporting_in_json_output(text: str) -> None:
    """The line a disagreement between two runs is diagnosed from, without instrumenting
    anything — so its shape (`index` carrying hits and misses) belongs in the README."""
    assert near(text, "--json", "index", "hits", "misses"), (
        "the README does not document the index hit/miss line in --json output"
    )


# --- content-keyed, therefore allowed to decay -----------------------------------


def test_readme_states_a_stale_index_costs_time_and_never_correctness(text: str) -> None:
    """The operational consequence of Q24. Without it, "the host cache is allowed to
    decay" reads as an admitted correctness risk instead of a scheduling decision."""
    assert any_near(
        text,
        "correctness",
        ("content-keyed", "content-addressed", "keyed on", "content key"),
        ("time", "speed", "slow"),
        ("stale", "decay", "out of date"),
        window=500,
    ), "the README does not say a stale index costs time and never correctness"


def test_readme_states_read_only_commands_populate_the_index_too(text: str) -> None:
    """Incidental use is the only thing keeping a host cache warm between refreshes, so
    "graph/list/trace write it too" is operational advice, not trivia."""
    assert any_near(
        text,
        ("read-only", "read only"),
        ("populate", "write", "warm", "fill"),
        ("index", "cache"),
    ), "the README does not say read-only commands populate the index too"


# --- reproducing the timings -----------------------------------------------------


def test_readme_points_at_the_benchmark_harness_and_its_required_book(text: str) -> None:
    """A speed claim nobody can re-derive is not evidence — and the harness stops rather
    than measure a default book, so the required argument has to be documented with it."""
    assert "bench-doctor" in text, "the README never points at `make bench-doctor`"
    assert near(text, "bench-doctor", "docs="), (
        "the README does not show the required DOCS= book argument"
    )
    assert any_near(text, "bench-doctor", ("required", "no default", "has no default")), (
        "the README does not say the book argument is required with no default"
    )
