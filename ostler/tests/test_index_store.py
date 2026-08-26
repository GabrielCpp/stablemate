"""`ostler.index` — the persistent, content-addressed parse index store.

`model._FEATURE_DOC_CACHE` is already keyed on a file's **content digest** rather than its
mtime, and for the right reason: the writer phases of a workflow edit these files between
loads, so a same-size rewrite inside one filesystem timestamp tick is exactly what a
stat-keyed cache serves stale. What it lacks is survival — every `ostler` invocation is a
fresh process. This module is that cache, persisted and generalised.

Nothing in ostler consults it yet (the last test here holds that line), so what these tests
pin down is the key and the validity rules on their own, before a caller can make either
hard to change.

The seam under test:

* ``index.epoch_inputs(root)`` — the material of every global input, one entry per label in
  ``index.EPOCH_LABELS``: the tool version, the schemas, the dynamic kind registry, the
  config files ostler reads, the waiver file and the freeze manifest.
* ``index.epoch(root)`` — one combined hash over exactly that mapping, and a pure function
  of it. No per-input granularity: a partial invalidation that is subtly wrong costs more
  than a recompute, so any change to any input busts every entry.
* ``index.index_dir(explicit=None)`` — ``explicit`` → ``$OSTLER_INDEX_DIR`` → ostler's own
  config key → the default under the shared stablemate cache.
* ``index.IndexStore(root, directory=..., max_age_s=...)`` with ``get(path)`` / ``put(path,
  value)``. An entry is keyed on the repo-name-qualified repo-relative path plus the
  content sha, so one entry serves every worktree and every container while the same bytes
  at a different path stay distinct. Payloads are pickle stamped with
  ``index.SCHEMA_VERSION``, rejected in both directions. A write prunes past
  ``max_age_s``, at most once per ``index.PRUNE_INTERVAL_S`` per directory. Anything
  unreadable is a miss, never an error the caller has to handle.

``epoch_inputs`` is monkeypatched through the module (``ostler.index.epoch_inputs``) where a
label's material cannot be moved on disk, so the implementation must call it through the
module rather than binding it at import.
"""

from __future__ import annotations

import importlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ostler._vendor.stablemate_core import config as core_config

from conftest import write

if TYPE_CHECKING:  # the seam below resolves at runtime; the annotation need not
    from ostler.index import IndexStore

class _Seam:
    """`ostler.index`, imported on first use.

    Not `from ostler import index`: until the module exists, a top-level import of it is a
    *collection* error, which pytest turns into an interrupted run — every other test in
    the suite stops reporting, and `ty` fails the lint gate before any test runs at all.
    Resolving on attribute access keeps the failure where it belongs, one red per test at
    the seam that is missing.
    """

    def __getattr__(self, name: str):
        return getattr(importlib.import_module("ostler.index"), name)


index = _Seam()

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every global input the epoch is required to cover, in the spelling the store declares.
EXPECTED_EPOCH_LABELS = frozenset(
    {"version", "schemas", "kinds", "config", "waivers", "freeze"}
)

PAYLOAD = {"frontmatter": {"type": "feature"}, "nodes": ["screen/save"]}


def make_repo(root: Path, *, doc: str = "one\n") -> Path:
    """A repo root carrying one document plus every file the epoch reads."""
    write(root / "docs/features/area/rec.md", doc)
    write(root / "ostler.yml", "organization: {}\n")
    write(root / "docs/doctor-waivers.json", '{"waivers": []}\n')
    write(root / ".agents/templates.yml", "{}\n")
    write(root / ".agents/ids.json", '{"frozen": {}}\n')
    return root


def store(root: Path, directory: Path, **kwargs: object) -> IndexStore:
    return index.IndexStore(root, directory=directory, **kwargs)


def entry_files(directory: Path) -> list[Path]:
    return [p for p in directory.rglob("*") if p.is_file()]


def age_everything(directory: Path, seconds: float) -> None:
    """Backdate every file in the index, so the next write has something to prune."""
    when = time.time() - seconds
    for path in entry_files(directory):
        os.utime(path, (when, when))


# ---------------------------------------------------------------------------
# The round trip it all rests on
# ---------------------------------------------------------------------------
def test_a_stored_payload_survives_a_new_store_over_the_same_directory(tmp_path):
    """Persistence is the whole point: the second store is the next process."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"

    store(root, directory).put(doc, PAYLOAD)

    assert store(root, directory).get(doc) == PAYLOAD


def test_editing_the_file_misses_even_when_its_size_and_mtime_do_not_move(tmp_path):
    """The key is the content sha, not a stat — the case the in-process cache was built for."""
    root = make_repo(tmp_path / "acme", doc="one\n")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)

    stat = doc.stat()
    doc.write_text("two\n", encoding="utf-8")
    os.utime(doc, (stat.st_atime, stat.st_mtime))

    assert store(root, directory).get(doc) is None


# ---------------------------------------------------------------------------
# One epoch hash over every global input
# ---------------------------------------------------------------------------
def test_the_epoch_covers_every_declared_global_input(tmp_path):
    root = make_repo(tmp_path / "acme")

    assert set(index.EPOCH_LABELS) == EXPECTED_EPOCH_LABELS
    assert set(index.epoch_inputs(root)) == EXPECTED_EPOCH_LABELS


@pytest.mark.parametrize("label", sorted(EXPECTED_EPOCH_LABELS))
def test_changing_any_single_epoch_input_invalidates_every_entry(tmp_path, monkeypatch, label):
    """One combined hash, so a change to *any* input busts *everything*, not a partition."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)
    before = index.epoch(root)

    real = index.epoch_inputs

    def moved(target: Path) -> dict[str, str]:
        inputs = dict(real(target))
        inputs[label] = f"{inputs[label]}-moved"
        return inputs

    monkeypatch.setattr("ostler.index.epoch_inputs", moved)

    assert index.epoch(root) != before
    assert store(root, directory).get(doc) is None


@pytest.mark.parametrize(
    ("label", "relpath", "text"),
    [
        ("config", "ostler.yml", "organization: {docRoots: {features: docs/f}}\n"),
        ("waivers", "docs/doctor-waivers.json", '{"waivers": [{"code": "x"}]}\n'),
        ("kinds", ".agents/templates.yml", "spike:\n  doc_root: docs/spikes\n"),
        ("freeze", ".agents/ids.json", '{"frozen": {"01-foo": {"hash": "abc"}}}\n'),
    ],
)
def test_editing_a_global_input_on_disk_invalidates_every_entry(tmp_path, label, relpath, text):
    """The four inputs that live in the repo, moved the way a run actually moves them."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)
    before = index.epoch(root)

    write(root / relpath, text)

    assert index.epoch(root) != before, f"the {label} input is not in the epoch"
    assert store(root, directory).get(doc) is None


# ---------------------------------------------------------------------------
# The entry key: repo-name-qualified repo-relative path + content sha
# ---------------------------------------------------------------------------
def test_two_worktrees_of_one_repo_resolve_to_one_entry(tmp_path):
    """Repo-relative, not absolute — so one entry serves every worktree and container."""
    first = make_repo(tmp_path / "worktrees/a/acme")
    second = make_repo(tmp_path / "worktrees/b/acme")
    directory = tmp_path / "index"

    store(first, directory).put(first / "docs/features/area/rec.md", PAYLOAD)

    assert store(second, directory).get(second / "docs/features/area/rec.md") == PAYLOAD


def test_the_same_bytes_at_a_different_path_do_not_collide(tmp_path):
    root = make_repo(tmp_path / "acme")
    original = root / "docs/features/area/rec.md"
    twin = root / "docs/features/area/rec2.md"
    twin.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    directory = tmp_path / "index"

    store(root, directory).put(original, PAYLOAD)

    assert store(root, directory).get(twin) is None


def test_the_same_relative_path_in_a_different_repo_does_not_collide(tmp_path):
    """The key carries the repo name, so two repos' `docs/features/area/rec.md` differ."""
    acme = make_repo(tmp_path / "checkouts/acme")
    globex = make_repo(tmp_path / "checkouts/globex")
    directory = tmp_path / "index"

    store(acme, directory).put(acme / "docs/features/area/rec.md", PAYLOAD)

    assert store(globex, directory).get(globex / "docs/features/area/rec.md") is None


# ---------------------------------------------------------------------------
# The payload's schema version, checked in both directions
# ---------------------------------------------------------------------------
def test_a_payload_stamped_older_than_the_running_version_is_rejected(tmp_path, monkeypatch):
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)

    monkeypatch.setattr("ostler.index.SCHEMA_VERSION", index.SCHEMA_VERSION + 1)

    assert store(root, directory).get(doc) is None


def test_a_payload_stamped_newer_than_the_running_version_is_rejected(tmp_path, monkeypatch):
    """The half a plain `>=` check misses: a newer writer's layout must not be misread."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"

    monkeypatch.setattr("ostler.index.SCHEMA_VERSION", index.SCHEMA_VERSION + 1)
    store(root, directory).put(doc, PAYLOAD)
    monkeypatch.undo()

    assert store(root, directory).get(doc) is None


# ---------------------------------------------------------------------------
# Where the index lives
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_resolution(tmp_path, monkeypatch) -> Path:
    """No config and a cache root that is not the operator's.

    The env override is cleared by each test rather than here, so that a missing seam is a
    failure inside the test and never an error raised out of a fixture.
    """
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config/config.toml"))
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


def test_the_index_dir_defaults_under_the_shared_stablemate_cache(isolated_resolution, monkeypatch):
    cache = isolated_resolution / "cache"
    monkeypatch.delenv(index.INDEX_DIR_ENV, raising=False)

    resolved = index.index_dir()

    assert cache in resolved.parents or resolved == cache, f"{resolved} is outside {cache}"


def test_the_environment_beats_the_default(isolated_resolution, monkeypatch):
    chosen = isolated_resolution / "from-env"
    monkeypatch.setenv(index.INDEX_DIR_ENV, str(chosen))

    assert index.index_dir() == chosen


def test_ostlers_own_config_beats_the_default_and_loses_to_the_environment(
    isolated_resolution, monkeypatch
):
    monkeypatch.delenv(index.INDEX_DIR_ENV, raising=False)
    configured = isolated_resolution / "from-config"
    core_config.write_config_key(index.CONFIG_KEY, str(configured))

    assert index.index_dir() == configured

    from_env = isolated_resolution / "from-env"
    monkeypatch.setenv(index.INDEX_DIR_ENV, str(from_env))
    assert index.index_dir() == from_env


def test_an_explicit_directory_overrides_all_three(isolated_resolution, monkeypatch):
    core_config.write_config_key(index.CONFIG_KEY, str(isolated_resolution / "from-config"))
    monkeypatch.setenv(index.INDEX_DIR_ENV, str(isolated_resolution / "from-env"))
    explicit = isolated_resolution / "from-argument"

    assert index.index_dir(explicit) == explicit


def test_a_store_given_no_directory_writes_where_the_resolution_says(isolated_resolution, monkeypatch):
    chosen = isolated_resolution / "from-env"
    monkeypatch.setenv(index.INDEX_DIR_ENV, str(chosen))
    root = make_repo(isolated_resolution / "acme")
    doc = root / "docs/features/area/rec.md"

    index.IndexStore(root).put(doc, PAYLOAD)

    assert entry_files(chosen), f"nothing written under {chosen}"
    assert index.IndexStore(root).get(doc) == PAYLOAD


# ---------------------------------------------------------------------------
# Self-bounding: a write prunes
# ---------------------------------------------------------------------------
def test_a_write_prunes_entries_past_the_age_bound(tmp_path):
    """An unattended machine must not grow the cache without limit."""
    root = make_repo(tmp_path / "acme")
    stale = root / "docs/features/area/rec.md"
    fresh = root / "docs/features/area/rec2.md"
    write(fresh, "two\n")
    directory = tmp_path / "index"
    bound = 3600.0

    store(root, directory, max_age_s=bound).put(stale, PAYLOAD)
    age_everything(directory, bound * 2)
    store(root, directory, max_age_s=bound).put(fresh, PAYLOAD)

    assert store(root, directory, max_age_s=bound).get(fresh) == PAYLOAD
    assert store(root, directory, max_age_s=bound).get(stale) is None


def test_a_write_keeps_entries_inside_the_age_bound(tmp_path):
    """The bound is a bound, not a sweep — pruning everything on every write is not this."""
    root = make_repo(tmp_path / "acme")
    kept = root / "docs/features/area/rec.md"
    other = root / "docs/features/area/rec2.md"
    write(other, "two\n")
    directory = tmp_path / "index"
    bound = 3600.0

    store(root, directory, max_age_s=bound).put(kept, PAYLOAD)
    age_everything(directory, bound / 2)
    store(root, directory, max_age_s=bound).put(other, PAYLOAD)

    assert store(root, directory, max_age_s=bound).get(kept) == PAYLOAD


def test_a_write_sweeps_at_most_once_per_interval(tmp_path):
    """The bound is an age, and an age does not need checking once per written entry.

    The sweep is a full ``rglob`` plus a ``stat`` per file, so running it on every ``put``
    made storing a book cost time quadratic in the size of the cache — the thing that made
    a cold fill against the index nine times slower than no index at all. What is asserted
    here is the throttle itself: with the stamp fresh, a second write past the bound leaves
    a stale entry alone.
    """
    root = make_repo(tmp_path / "acme")
    stale = root / "docs/features/area/rec.md"
    fresh = root / "docs/features/area/rec2.md"
    write(fresh, "two\n")
    directory = tmp_path / "index"
    bound = 3600.0

    store(root, directory, max_age_s=bound).put(stale, PAYLOAD)  # stamps the directory
    for path in entry_files(directory):
        if path.name != index.PRUNE_STAMP_NAME:
            os.utime(path, (time.time() - bound * 2, time.time() - bound * 2))
    store(root, directory, max_age_s=bound).put(fresh, PAYLOAD)

    assert store(root, directory, max_age_s=bound).get(stale) == PAYLOAD, (
        "a sweep ran on a write minutes after the last one")


def test_a_stale_stamp_lets_the_next_write_sweep_again(tmp_path):
    """The throttle defers a sweep; it does not cancel it. The other half of the bound."""
    root = make_repo(tmp_path / "acme")
    stale = root / "docs/features/area/rec.md"
    fresh = root / "docs/features/area/rec2.md"
    write(fresh, "two\n")
    directory = tmp_path / "index"
    bound = 3600.0

    store(root, directory, max_age_s=bound).put(stale, PAYLOAD)
    age_everything(directory, index.PRUNE_INTERVAL_S + bound * 2)  # entries and stamp alike
    store(root, directory, max_age_s=bound).put(fresh, PAYLOAD)

    assert store(root, directory, max_age_s=bound).get(stale) is None
    assert store(root, directory, max_age_s=bound).get(fresh) == PAYLOAD


def test_the_stamp_is_not_an_entry(tmp_path):
    """Neither mode of `clean` counts or removes it.

    Reporting it to an operator would overstate what was evicted by one, and removing it
    under ``--all`` would hand the next writer a directory that looks never swept — which
    is the one state that makes a sweep run on the very next write.
    """
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"

    store(root, directory).put(doc, PAYLOAD)
    stamp = directory / index.PRUNE_STAMP_NAME
    assert stamp.is_file(), "a write that pruned never recorded that it had"

    assert index.clean(directory, everything=True) == 1, "the stamp was counted as an entry"
    assert stamp.is_file(), "--all removed the sweep's own bookkeeping"


def test_a_directory_that_cannot_be_stamped_does_not_sweep_on_every_write(tmp_path):
    """No stamp means no throttle, and a store with no throttle is the quadratic one.

    A read-only cache directory is the realistic way to get there. Reporting not-due is the
    safe answer: the entries still age out under ``ostler cache clean``, and no write pays
    for a directory walk it cannot record having done.
    """
    root = make_repo(tmp_path / "acme")
    directory = tmp_path / "index"
    directory.mkdir()
    store_ = store(root, directory, max_age_s=3600.0)

    def refuse(*_args, **_kwargs):
        raise OSError("read-only file system")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "touch", refuse)
        assert store_.prune() == 0
        assert store_.prune() == 0


def test_the_age_bound_has_a_default_a_caller_need_not_supply(tmp_path):
    assert index.DEFAULT_MAX_AGE_S > 0
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"

    store(root, directory).put(doc, PAYLOAD)

    assert store(root, directory).get(doc) == PAYLOAD


# ---------------------------------------------------------------------------
# Damage is a miss, never an error
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("label", "damage"),
    [
        ("truncated", lambda data: data[: len(data) // 2]),
        ("garbage", lambda data: b"not a pickle at all"),
        ("empty", lambda data: b""),
    ],
)
def test_a_damaged_entry_reads_as_a_miss(tmp_path, label, damage):
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)

    for path in entry_files(directory):
        path.write_bytes(damage(path.read_bytes()))

    assert store(root, directory).get(doc) is None, f"a {label} entry must not be served"


def test_a_damaged_entry_does_not_stop_the_next_write_from_serving(tmp_path):
    """Recovery, not just tolerance: a corrupt entry is overwritten by the next put."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)
    for path in entry_files(directory):
        path.write_bytes(b"\x00\x01\x02")

    store(root, directory).put(doc, PAYLOAD)

    assert store(root, directory).get(doc) == PAYLOAD


def test_an_unreadable_index_directory_is_a_miss_not_a_failure(tmp_path):
    """The store is an optimisation — it may never be the reason a command fails."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("in the way\n", encoding="utf-8")

    assert store(root, blocked).get(doc) is None
    store(root, blocked).put(doc, PAYLOAD)


def test_a_missing_file_is_a_miss(tmp_path):
    root = make_repo(tmp_path / "acme")
    directory = tmp_path / "index"

    assert store(root, directory).get(root / "docs/features/area/gone.md") is None


# ---------------------------------------------------------------------------
# The parse products are served from it
# ---------------------------------------------------------------------------
#: The two modules that own a read-only parse product: the document accessor every reader goes
#: through, and the anchor computation — the single largest consumer of it. `markdown.py` and
#: `graph.py` stay out on purpose. The parser is the thing being cached, not a caller of the
#: cache, and the graph build reaches its documents through the accessor.
PRODUCT_MODULES = ("model.py", "links.py")


def test_every_parse_product_is_served_from_the_store():
    """The store shipped ahead of its consumers; this is the increment that connects them.

    A file-level check rather than a behavioural one, because it is the *converse* that the
    behavioural tests cannot state: `test_index_parse_products.py` shows the accessor is warm,
    but only reading the modules shows that the anchor computation goes through the same store
    rather than growing a memo of its own.
    """
    package = REPO_ROOT / "ostler" / "ostler"
    # Reaching the store means either owning the connection to it or going through `read_doc`,
    # the one accessor that owns it. `links.py` does the latter — it names no store at all now,
    # which is the shape the increment was after, so the second half of the check is what keeps
    # that from being indistinguishable from a module that quietly went back to parsing: a
    # consumer may not call the splitter for itself.
    served = ("from ostler import index", "from ostler.index", "ostler.index", "IndexStore",
              "read_doc")
    sources = {path.name: path.read_text(encoding="utf-8")
               for path in package.rglob("*.py") if path.name in PRODUCT_MODULES}

    unserved = [name for name, text in sources.items()
                if not any(marker in text for marker in served)]

    assert not unserved, f"still parsing without the store: {unserved}"
    # `model.py` is exempt: its call to the splitter *is* the cache fill.
    assert "markdown.split" not in sources["links.py"], (
        "links.py splits markdown for itself again instead of going through the accessor")
