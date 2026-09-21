"""`ostler.index` — the persistent, content-addressed parse index store."""

from __future__ import annotations

import dataclasses
import importlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ostler._vendor.stablemate_core import config as core_config

from conftest import write

if TYPE_CHECKING:
    from ostler.index import IndexStore

class _Seam:
    """`ostler.index`, imported on first use."""

    def __getattr__(self, name: str):
        return getattr(importlib.import_module("ostler.index"), name)


index = _Seam()

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_EPOCH_LABELS = frozenset(
    {"version", "schemas", "kinds", "config", "freeze", "shape"}
)

PAYLOAD = {"frontmatter": {"type": "feature"}, "nodes": ["screen/save"]}


def make_repo(root: Path, *, doc: str = "one\n") -> Path:
    """A repo root carrying one document plus every file the epoch reads."""
    write(root / "docs/features/area/rec.md", doc)
    write(root / "ostler.yml", "organization: {}\n")
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
        ("kinds", ".agents/templates.yml", "spike:\n  doc_root: docs/spikes\n"),
        ("freeze", ".agents/ids.json", '{"frozen": {"01-foo": {"hash": "abc"}}}\n'),
    ],
)
def test_editing_a_global_input_on_disk_invalidates_every_entry(tmp_path, label, relpath, text):
    """The three inputs that live in the repo, moved the way a run actually moves them."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"
    store(root, directory).put(doc, PAYLOAD)
    before = index.epoch(root)

    write(root / relpath, text)

    assert index.epoch(root) != before, f"the {label} input is not in the epoch"
    assert store(root, directory).get(doc) is None


@dataclasses.dataclass
class _ShapeItemBefore:
    """A nested stored class, before a field lands on it."""

    headline: str


@dataclasses.dataclass
class _ShapeItemAfter:
    headline: str
    note: str


@dataclasses.dataclass
class _ShapeContainerBefore:
    items: dict[str, list[_ShapeItemBefore]]


@dataclasses.dataclass
class _ShapeContainerAfter:
    items: dict[str, list[_ShapeItemAfter]]


def test_adding_a_field_to_a_stored_dataclass_moves_the_shape_digest():
    """The failure this digest exists to prevent, reproduced on a throwaway pair of classes."""

    @dataclasses.dataclass
    class Before:
        headline: str
        properties: dict

    @dataclasses.dataclass
    class After:
        headline: str
        properties: dict
        records: dict

    assert index.dataclass_shape_digest(Before) != index.dataclass_shape_digest(After)


def test_widening_a_fields_annotation_moves_the_shape_digest():
    """Incident 10, reproduced on a throwaway pair of classes."""

    @dataclasses.dataclass
    class Before:
        headline: str
        links: tuple[str, str]

    @dataclasses.dataclass
    class After:
        headline: str
        links: tuple[str, str, int]

    assert index.dataclass_shape_digest(Before) != index.dataclass_shape_digest(After)


def test_the_shape_digest_reaches_a_dataclass_nested_inside_a_container_field():
    """A field added several containers deep must still move the digest."""
    assert index.dataclass_shape_digest(
        _ShapeContainerBefore
    ) != index.dataclass_shape_digest(_ShapeContainerAfter)


def test_the_shape_digest_is_a_pure_function_of_the_classes_it_is_given():
    """Deterministic and salt-free, unlike ``hash()`` on a string, which is salted per run."""

    @dataclasses.dataclass
    class Shape:
        a: str
        b: int

    assert index.dataclass_shape_digest(Shape) == index.dataclass_shape_digest(Shape)


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


@pytest.fixture
def isolated_resolution(tmp_path, monkeypatch) -> Path:
    """No config and a cache root that is not the operator's."""
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
    """The bound is an age, and an age does not need checking once per written entry."""
    root = make_repo(tmp_path / "acme")
    stale = root / "docs/features/area/rec.md"
    fresh = root / "docs/features/area/rec2.md"
    write(fresh, "two\n")
    directory = tmp_path / "index"
    bound = 3600.0

    store(root, directory, max_age_s=bound).put(stale, PAYLOAD)
    for path in entry_files(directory):
        if path.name != index.PRUNE_STAMP_NAME:
            os.utime(path, (time.time() - bound * 2, time.time() - bound * 2))
    store(root, directory, max_age_s=bound).put(fresh, PAYLOAD)

    assert store(root, directory, max_age_s=bound).get(stale) == PAYLOAD, (
        "a sweep ran on a write minutes after the last one")


def test_a_stale_stamp_lets_the_next_write_sweep_again(tmp_path):
    """The throttle defers a sweep; it does not cancel it."""
    root = make_repo(tmp_path / "acme")
    stale = root / "docs/features/area/rec.md"
    fresh = root / "docs/features/area/rec2.md"
    write(fresh, "two\n")
    directory = tmp_path / "index"
    bound = 3600.0

    store(root, directory, max_age_s=bound).put(stale, PAYLOAD)
    age_everything(directory, index.PRUNE_INTERVAL_S + bound * 2)
    store(root, directory, max_age_s=bound).put(fresh, PAYLOAD)

    assert store(root, directory, max_age_s=bound).get(stale) is None
    assert store(root, directory, max_age_s=bound).get(fresh) == PAYLOAD


def test_the_stamp_is_not_an_entry(tmp_path):
    """Neither mode of `clean` counts or removes it."""
    root = make_repo(tmp_path / "acme")
    doc = root / "docs/features/area/rec.md"
    directory = tmp_path / "index"

    store(root, directory).put(doc, PAYLOAD)
    stamp = directory / index.PRUNE_STAMP_NAME
    assert stamp.is_file(), "a write that pruned never recorded that it had"

    assert index.clean(directory, everything=True) == 1, "the stamp was counted as an entry"
    assert stamp.is_file(), "--all removed the sweep's own bookkeeping"


def test_a_directory_that_cannot_be_stamped_does_not_sweep_on_every_write(tmp_path):
    """No stamp means no throttle, and a store with no throttle is the quadratic one."""
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


PRODUCT_MODULES = ("model.py", "links.py")


def test_every_parse_product_is_served_from_the_store():
    """The store shipped ahead of its consumers; this is the increment that connects them."""
    package = REPO_ROOT / "ostler" / "ostler"
    served = ("from ostler import index", "from ostler.index", "ostler.index", "IndexStore",
              "read_doc")
    sources = {path.name: path.read_text(encoding="utf-8")
               for path in package.rglob("*.py") if path.name in PRODUCT_MODULES}

    unserved = [name for name, text in sources.items()
                if not any(marker in text for marker in served)]

    assert not unserved, f"still parsing without the store: {unserved}"
    assert "markdown.split" not in sources["links.py"], (
        "links.py splits markdown for itself again instead of going through the accessor")


def test_the_shape_digest_reaches_every_dataclass_a_production_caller_stores():
    """The roots are a list, and a list left behind is the failure the digest was built to end."""
    from ostler import api, index, inventory, model

    reached = index._reachable_dataclasses(
        (model.UINode, model._DocProducts, api.Snapshot, inventory._SymbolTable))

    assert {api.Snapshot, inventory._SymbolTable, model.Graph, model.Entry} <= reached
    assert index._shape_material() == index.dataclass_shape_digest(*reached)


def test_every_module_that_stores_a_payload_is_a_shape_root():
    """A new storing module is the one change the digest cannot notice for itself."""
    package = REPO_ROOT / "ostler" / "ostler"
    storing = {path.stem for path in package.rglob("*.py")
               if path.stem != "index"
               and any(call in path.read_text(encoding="utf-8")
                       for call in (".put_key(", ".put("))}
    rooted = (REPO_ROOT / "ostler" / "ostler" / "index.py").read_text(encoding="utf-8")
    material = rooted.split("def _shape_material()")[1].split("\ndef ")[0]

    missing = sorted(name for name in storing if name not in material)

    assert not missing, (
        f"these modules store a payload but are not named in _shape_material: {missing} — "
        "either add the dataclass they store to the roots, or say in the docstring why the "
        "payload has no field names to hash")
