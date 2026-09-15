"""`ostler.stamp` — writing per-citation content-hash digests onto `code:` bullets."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ostler import source_snapshots, stamp
from ostler.cli import main
from ostler.model import load

SERVICE = "def charge(amount):\n    return amount\n"


def test_digest_file_hashes_raw_bytes():
    """Raw bytes, truncated to 12 hex chars — no decoding, so a non-UTF-8 file still hashes."""
    assert stamp.digest_file(SERVICE.encode()) == hashlib.sha256(SERVICE.encode()).hexdigest()[:12]


def test_digest_file_hashes_non_utf8_bytes_without_crashing():
    data = b"\xff\xfe\x00binary"
    assert stamp.digest_file(data) == hashlib.sha256(data).hexdigest()[:12]


def test_restamp_stamps_a_single_target():
    out = stamp.restamp_leading_code_spans("`api/a.py`", lambda _: "3f9a1c07b2e4")
    assert out == "`api/a.py` @3f9a1c07b2e4"


def test_restamp_stamps_every_target_in_a_multi_target_bullet():
    digests = {"api/a.py": "3f9a1c07b2e4", "api/b.py": "abcdef012345"}
    out = stamp.restamp_leading_code_spans(
        "`api/a.py`, `api/b.py`", lambda target: digests[target],
    )
    assert out == "`api/a.py` @3f9a1c07b2e4, `api/b.py` @abcdef012345"


def test_restamp_leaves_a_target_unstamped_when_digest_for_returns_none():
    out = stamp.restamp_leading_code_spans("`api/a.py`", lambda _: None)
    assert out == "`api/a.py`"


def test_restamp_leaves_an_existing_digest_standing_when_digest_for_returns_none():
    # None from digest_for means "this span was not observed just now", not "clear it" — a
    # target left alone must keep whatever digest it already carried.
    out = stamp.restamp_leading_code_spans("`api/a.py` @000000000000", lambda _: None)
    assert out == "`api/a.py` @000000000000"


def test_restamp_a_multi_target_bullet_leaves_the_unassigned_spans_digest_standing():
    digests = {"api/a.py": "3f9a1c07b2e4"}
    out = stamp.restamp_leading_code_spans(
        "`api/a.py` @000000000000, `api/b.py` @111111111111",
        lambda target: digests.get(target),
    )
    assert out == "`api/a.py` @3f9a1c07b2e4, `api/b.py` @111111111111"


def test_restamp_overwrites_an_existing_digest():
    out = stamp.restamp_leading_code_spans(
        "`api/a.py` @000000000000", lambda _: "3f9a1c07b2e4",
    )
    assert out == "`api/a.py` @3f9a1c07b2e4"


def test_restamp_leaves_a_trailing_gloss_untouched():
    out = stamp.restamp_leading_code_spans(
        "`api/a.py` (inline JSX, not a named export)", lambda _: "3f9a1c07b2e4",
    )
    assert out == "`api/a.py` @3f9a1c07b2e4 (inline JSX, not a named export)"


def test_restamp_leaves_a_value_with_no_leading_span_unchanged():
    assert stamp.restamp_leading_code_spans(
        "see `api/a.py` for the handler", lambda _: "3f9a1c07b2e4",
    ) == "see `api/a.py` for the handler"


def test_restamp_stamps_a_bare_target_directly_abutting_the_digest():
    # No space before `@`: `refs.parse_code_ref`'s digest suffix is anchored at the string's
    # end with no whitespace tolerance, so a space here would leak into the parsed path.
    out = stamp.restamp_leading_code_spans("api/a.py", lambda _: "3f9a1c07b2e4")
    assert out == "api/a.py@3f9a1c07b2e4"


def test_restamp_stamps_every_target_in_a_bare_multi_target_list():
    digests = {"api/a.py": "3f9a1c07b2e4", "api/b.py": "abcdef012345"}
    out = stamp.restamp_leading_code_spans(
        "api/a.py, api/b.py", lambda target: digests[target],
    )
    assert out == "api/a.py@3f9a1c07b2e4, api/b.py@abcdef012345"


def test_restamp_leaves_a_bare_target_unstamped_when_digest_for_returns_none():
    out = stamp.restamp_leading_code_spans("api/a.py", lambda _: None)
    assert out == "api/a.py"


def test_restamp_leaves_a_bare_targets_existing_digest_standing_when_unassigned():
    out = stamp.restamp_leading_code_spans("api/a.py@000000000000", lambda _: None)
    assert out == "api/a.py@000000000000"


def test_restamp_overwrites_a_bare_targets_existing_digest():
    out = stamp.restamp_leading_code_spans("api/a.py@000000000000", lambda _: "3f9a1c07b2e4")
    assert out == "api/a.py@3f9a1c07b2e4"


def test_restamp_leaves_an_empty_token_bullet_unchanged():
    # `code: none` is the package's sentinel vocabulary (`registry.EMPTY_TOKENS`), not a
    # citation — a naive bare-target split would otherwise treat "none" as an unresolvable
    # target and report it, a false positive that did not exist before this fallback existed.
    assert stamp.restamp_leading_code_spans("none", lambda _: "3f9a1c07b2e4") == "none"


def _book(root: Path, code: str) -> Path:
    feature = root / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        f"# Charge\n\n- code: {code}\n",
        encoding="utf-8",
    )
    return feature


def _service(root: Path, text: str = SERVICE) -> Path:
    target = root / "src/service.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_stamp_page_writes_a_digest_onto_the_cited_file(tmp_path: Path):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    expected = stamp.digest_file(SERVICE.encode())
    assert result.stamped == 1
    assert result.unresolved == []
    assert result.changed is True
    assert f"`src/service.py::charge` @{expected}" in feature.read_text(encoding="utf-8")


def test_stamp_page_reports_a_missing_file_as_unresolved(tmp_path: Path):
    _book(tmp_path, "`src/missing.py::charge`")
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.stamped == 0
    assert result.unresolved == ["src/missing.py::charge"]
    assert result.changed is False


def test_stamp_page_reports_a_bare_missing_target_as_unresolved(tmp_path: Path):
    # A bare (non-backticked) target that genuinely cannot be resolved must surface exactly
    # like a backticked one does — invisible to neither `doctor` nor `stamp`.
    _book(tmp_path, "src/missing.py::charge")
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.stamped == 0
    assert result.unresolved == ["src/missing.py::charge"]
    assert result.changed is False


def test_stamp_page_stamps_both_a_backticked_and_a_bare_code_bullet(tmp_path: Path):
    # One node citing a file through a backtick-quoted `code:` bullet and a sibling bullet
    # citing another file bare (no backticks at all) — the bug this fixes: the bare bullet
    # used to come back completely unchanged, neither stamped nor reported unresolved.
    feature = tmp_path / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        "- code: `src/service.py::charge`\n"
        "- code: src/other.py::other\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    (tmp_path / "src/other.py").write_text("def other():\n    pass\n", encoding="utf-8")

    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")

    expected = stamp.digest_file(SERVICE.encode())
    other_digest = stamp.digest_file(b"def other():\n    pass\n")
    assert result.stamped == 2
    assert result.unresolved == []
    text = feature.read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{expected}" in text
    assert f"src/other.py::other@{other_digest}" in text


def test_stamp_page_leaves_a_ref_to_a_different_repository_unresolved(tmp_path: Path):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    _book(tmp_path, "`repo://globex/src/service.py::charge`")
    _service(tmp_path)
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.stamped == 0
    assert result.unresolved == ["repo://globex/src/service.py::charge"]
    assert result.changed is False


def test_stamp_page_resolves_a_foreign_repository_ref_through_a_supplied_checkout(
    tmp_path: Path,
):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    feature = _book(tmp_path, "`repo://globex/src/service.py::charge`")
    checkout = tmp_path / "checkouts" / "globex"
    _service(checkout)
    result = stamp.stamp_page(
        tmp_path, tmp_path, "docs/features/billing/charge.md",
        checkouts={"globex": checkout},
    )
    expected = stamp.digest_file(SERVICE.encode())
    assert result.stamped == 1
    assert result.unresolved == []
    assert f"`repo://globex/src/service.py::charge` @{expected}" in feature.read_text(
        encoding="utf-8",
    )


def test_stamp_page_leaves_an_unmapped_foreign_repository_ref_unreachable(tmp_path: Path):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    _book(tmp_path, "`repo://globex/src/service.py::charge`")
    checkout = tmp_path / "checkouts" / "other-repo"
    _service(checkout)
    result = stamp.stamp_page(
        tmp_path, tmp_path, "docs/features/billing/charge.md",
        checkouts={"other-repo": checkout},
    )
    assert result.stamped == 0
    assert result.unresolved == ["repo://globex/src/service.py::charge"]
    assert result.changed is False


def test_stamp_page_resolves_a_ref_qualified_with_the_books_own_repository(tmp_path: Path):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    feature = _book(tmp_path, "`repo://acme/src/service.py::charge`")
    _service(tmp_path)
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    expected = stamp.digest_file(SERVICE.encode())
    assert result.stamped == 1
    assert f"@{expected}" in feature.read_text(encoding="utf-8")


def test_restamping_an_unchanged_file_is_a_noop_write(tmp_path: Path):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    before = feature.read_text(encoding="utf-8")
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.changed is False
    assert feature.read_text(encoding="utf-8") == before


def _two_node_book(root: Path, code: str) -> Path:
    feature = root / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        "## Alpha\n\n"
        f"- code: {code}\n\n"
        "## Beta\n\n"
        f"- code: {code}\n",
        encoding="utf-8",
    )
    return feature


def test_stamp_page_scoped_to_a_line_range_leaves_the_other_nodes_bullet_stale(tmp_path: Path):
    # Two nodes on one page cite the same changed file. Stamping only "Alpha"'s line range
    # must not touch "Beta"'s bullet — the whole point of node-scoped stamping.
    feature = _two_node_book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    lines = feature.read_text(encoding="utf-8").splitlines()
    alpha_line = next(i for i, line in enumerate(lines, start=1) if line == "## Alpha")
    beta_line = next(i for i, line in enumerate(lines, start=1) if line == "## Beta")

    result = stamp.stamp_page(
        tmp_path, tmp_path, "docs/features/billing/charge.md",
        line_ranges=[(alpha_line, beta_line)],
    )

    expected = stamp.digest_file(SERVICE.encode())
    assert result.stamped == 1
    assert result.changed is True
    after = feature.read_text(encoding="utf-8").splitlines()
    assert f"- code: `src/service.py::charge` @{expected}" == after[alpha_line + 1]
    assert "- code: `src/service.py::charge`" == after[beta_line + 1]


def test_stamp_page_only_targets_leaves_a_sibling_citation_on_the_same_node_untouched(
    tmp_path: Path,
):
    # One node cites two files but only one of them was regrounded this turn; the other
    # citation must be left exactly as it was, not silently refreshed.
    feature = _book(tmp_path, "`src/service.py::charge`, `src/other.py::other`")
    _service(tmp_path)
    other = tmp_path / "src/other.py"
    other.write_text("def other():\n    pass\n", encoding="utf-8")

    lines = feature.read_text(encoding="utf-8").splitlines()
    heading_line = next(i for i, line in enumerate(lines, start=1) if line == "# Charge")
    node_range = (heading_line, len(lines) + 1)

    result = stamp.stamp_page(
        tmp_path, tmp_path, "docs/features/billing/charge.md",
        line_ranges=[node_range],
        only_targets={node_range: frozenset({"src/service.py"})},
    )

    expected = stamp.digest_file(SERVICE.encode())
    assert result.stamped == 1
    text = feature.read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{expected}" in text
    assert "`src/other.py::other`" in text
    assert "`src/other.py::other` @" not in text


def test_stamp_page_only_targets_leaves_an_already_stamped_sibling_digest_standing(
    tmp_path: Path,
):
    # Both citations were already stamped by a prior turn; regrounding one of them must not
    # erase the other's standing digest just because this pass never re-read it.
    feature = _book(tmp_path, "`src/service.py::charge` @000000000000,"
                              " `src/other.py::other` @111111111111")
    _service(tmp_path)
    other = tmp_path / "src/other.py"
    other.write_text("def other():\n    pass\n", encoding="utf-8")

    lines = feature.read_text(encoding="utf-8").splitlines()
    heading_line = next(i for i, line in enumerate(lines, start=1) if line == "# Charge")
    node_range = (heading_line, len(lines) + 1)

    result = stamp.stamp_page(
        tmp_path, tmp_path, "docs/features/billing/charge.md",
        line_ranges=[node_range],
        only_targets={node_range: frozenset({"src/service.py"})},
    )

    expected = stamp.digest_file(SERVICE.encode())
    assert result.stamped == 1
    text = feature.read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{expected}" in text
    assert "`src/other.py::other` @111111111111" in text


def test_stamp_page_leaves_a_stamped_target_whose_file_was_deleted_standing(tmp_path: Path):
    # A file that vanished since the last stamp is what dangling-code-ref/unreachable-citation
    # surface — restamping the node must not also strip the prior, real observation.
    feature = _book(tmp_path, "`src/service.py::charge` @000000000000")

    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")

    assert result.stamped == 0
    assert "src/service.py::charge" in result.unresolved
    assert not result.changed
    assert "`src/service.py::charge` @000000000000" in feature.read_text(encoding="utf-8")


def test_cli_stamp_node_file_pair_scopes_the_restamp_to_one_citation(
    tmp_path: Path, capsys,
):
    feature = _book(tmp_path, "`src/service.py::charge`, `src/other.py::other`")
    _service(tmp_path)
    (tmp_path / "src/other.py").write_text("def other():\n    pass\n", encoding="utf-8")

    rc = main([
        "-C", str(tmp_path), "stamp", "--no-index",
        "--node", "docs/features/billing/charge.md", "--file", "src/service.py",
    ])
    assert rc == 0
    text = feature.read_text(encoding="utf-8")
    assert "`src/service.py::charge` @" in text
    assert "`src/other.py::other` @" not in text


def test_cli_stamp_checkout_flag_resolves_a_foreign_repository_ref(tmp_path: Path):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    feature = _book(tmp_path, "`repo://globex/src/service.py::charge`")
    checkout = tmp_path / "checkouts" / "globex"
    _service(checkout)

    rc = main([
        "-C", str(tmp_path), "stamp", "--no-index",
        "--path", "docs/features/billing/charge.md", "--whole-page",
        "--checkout", f"globex={checkout}",
    ])
    assert rc == 0
    expected = stamp.digest_file(SERVICE.encode())
    assert f"@{expected}" in feature.read_text(encoding="utf-8")


def test_cli_stamp_checkout_flag_rejects_a_malformed_value(tmp_path: Path, capsys):
    _book(tmp_path, "`src/service.py::charge`")
    rc = main([
        "-C", str(tmp_path), "stamp", "--no-index",
        "--path", "docs/features/billing/charge.md", "--whole-page",
        "--checkout", "not-a-pair",
    ])
    assert rc == 2
    assert "--checkout must be REPOSITORY=PATH" in capsys.readouterr().err


def test_node_line_range_runs_to_end_of_file_for_a_lone_node(tmp_path: Path):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    graph = load(tmp_path)
    node = graph.find_ui_node("docs/features/billing/charge.md")
    assert node is not None
    line_count = len(feature.read_text(encoding="utf-8").splitlines())
    assert stamp.node_line_range(graph, node) == (node.line, line_count + 1)


def test_node_line_range_stops_at_the_next_sibling_on_the_page(tmp_path: Path):
    _two_node_book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    graph = load(tmp_path)
    alpha = graph.find_ui_node("docs/features/billing/charge.md#alpha")
    beta = graph.find_ui_node("docs/features/billing/charge.md#beta")
    assert alpha is not None
    assert beta is not None
    assert stamp.node_line_range(graph, alpha) == (alpha.line, beta.line)


def test_stamp_targets_scopes_the_restamp_to_the_given_node_and_file(tmp_path: Path):
    _book(tmp_path, "`src/service.py::charge`, `src/other.py::other`")
    _service(tmp_path)
    (tmp_path / "src/other.py").write_text("def other():\n    pass\n", encoding="utf-8")
    graph = load(tmp_path)

    results = stamp.stamp_targets(
        graph, tmp_path, [("docs/features/billing/charge.md", "src/service.py")],
    )

    assert len(results) == 1
    assert results[0].unresolved == []
    text = (tmp_path / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    assert "`src/service.py::charge` @" in text
    assert "`src/other.py::other` @" not in text


def test_stamp_targets_leaves_a_nodes_other_stamped_citations_standing(tmp_path: Path):
    # The turn-finalize repro: a node with several already-stamped citations gets one pair
    # restamped. Only the assigned bullet's digest may change — the rest go from stamped to
    # unstamped-citation if their `@digest` is silently dropped here.
    _book(
        tmp_path,
        "`src/service.py::charge` @000000000000, `src/other.py::other` @111111111111",
    )
    _service(tmp_path)
    (tmp_path / "src/other.py").write_text("def other():\n    pass\n", encoding="utf-8")
    graph = load(tmp_path)

    results = stamp.stamp_targets(
        graph, tmp_path, [("docs/features/billing/charge.md", "src/service.py")],
    )

    assert len(results) == 1
    assert results[0].stamped == 1
    expected = stamp.digest_file(SERVICE.encode())
    text = (tmp_path / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{expected}" in text
    assert "`src/other.py::other` @111111111111" in text


def test_stamp_targets_leaves_a_sibling_nodes_citation_of_the_same_file_untouched(
    tmp_path: Path,
):
    _two_node_book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    graph = load(tmp_path)

    results = stamp.stamp_targets(
        graph, tmp_path, [("docs/features/billing/charge.md#alpha", "src/service.py")],
    )

    assert len(results) == 1
    assert results[0].stamped == 1
    text = (tmp_path / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    alpha_line = next(i for i, line in enumerate(lines) if line == "## Alpha")
    beta_line = next(i for i, line in enumerate(lines) if line == "## Beta")
    assert "@" in lines[alpha_line + 2]
    assert "@" not in lines[beta_line + 2]


def test_stamp_targets_reports_an_unresolved_node_without_dropping_the_others(tmp_path: Path):
    _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    graph = load(tmp_path)

    results = stamp.stamp_targets(
        graph, tmp_path, [
            ("docs/features/billing/charge.md", "src/service.py"),
            ("docs/features/billing/missing.md#nope", "src/service.py"),
        ],
    )

    by_page = {r.page: r for r in results}
    assert by_page["docs/features/billing/charge.md"].stamped == 1
    assert by_page[""].unresolved == ["docs/features/billing/missing.md#nope"]


def test_cli_stamp_file_without_node_is_rejected(tmp_path: Path, capsys):
    _book(tmp_path, "`src/service.py::charge`")
    rc = main(["-C", str(tmp_path), "stamp", "--no-index", "--file", "src/service.py"])
    assert rc == 2


def test_stamp_page_reports_a_bullet_whose_line_count_changed_as_unresolved(
    tmp_path: Path, monkeypatch,
):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    # `restamp_leading_code_spans` never adds or removes a line on its own; force the
    # mismatch branch by handing it a `digest_for` that turns one line into two.
    original = stamp.restamp_leading_code_spans
    monkeypatch.setattr(
        stamp, "restamp_leading_code_spans",
        lambda value, digest_for: original(value, digest_for) + "\nextra",
    )
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.unresolved == ["- code: `src/service.py::charge`"]
    assert result.changed is False
    assert "@" not in feature.read_text(encoding="utf-8")


def test_stamp_page_from_catalog_uses_the_catalogs_digest_not_the_live_files(tmp_path: Path):
    # The file on disk has drifted since the catalog was last built. Migration must stamp
    # the *catalog's* stale digest, not re-read the file — so `stale-citation` fires right
    # after migration, instead of the drift silently looking fresh.
    root = tmp_path
    _book(root, "`src/service.py::charge`")
    _service(root, "def charge(amount):\n    return amount * 2\n")
    stale_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py", content_sha256=stale_digest),
                ),
            ),
        ),
    )
    result = stamp.stamp_page_from_catalog(root, "docs/features/billing/charge.md", catalog)
    assert result.stamped == 1
    assert result.unresolved == []
    text = (root / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{stale_digest[:12]}" in text
    assert stale_digest[:12] != stamp.digest_file((root / "src/service.py").read_bytes())


def test_stamp_page_from_catalog_leaves_a_file_with_no_catalog_row_unstamped(tmp_path: Path):
    _book(tmp_path, "`src/missing_from_catalog.py::charge`")
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE", files=(),
            ),
        ),
    )
    result = stamp.stamp_page_from_catalog(tmp_path, "docs/features/billing/charge.md", catalog)
    assert result.stamped == 0
    assert result.unresolved == ["src/missing_from_catalog.py::charge"]
    assert result.changed is False


def test_cli_stamp_from_catalog_migrates_the_whole_book_and_deletes_the_catalog(
    tmp_path: Path,
):
    feature = tmp_path / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        "- code: `src/service.py::charge`\n"
        "- code: `src/uncatalogued.py::other`\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    (tmp_path / "src/uncatalogued.py").write_text("def other():\n    pass\n", encoding="utf-8")

    stale_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=stale_digest),
                ),
            ),
        ),
    )
    catalog_path = source_snapshots.catalog_path(tmp_path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")

    assert main(["-C", str(tmp_path), "stamp", "--from-catalog"]) == 0

    text = feature.read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{stale_digest[:12]}" in text
    assert "`src/uncatalogued.py::other`\n" in text
    assert not catalog_path.exists()


def test_cli_stamp_from_catalog_with_path_leaves_the_catalog_and_other_pages_migratable(
    tmp_path: Path,
):
    # A --path migration only stamps the pages named on the command line. The catalog must
    # survive so a later invocation can still migrate the page that was left out this time --
    # deleting it here would permanently lose that page's digest (bug: c0237c3b).
    billing = tmp_path / "docs/features/billing/charge.md"
    billing.parent.mkdir(parents=True, exist_ok=True)
    billing.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n- code: `src/service.py::charge`\n",
        encoding="utf-8",
    )
    refund = tmp_path / "docs/features/billing/refund.md"
    refund.write_text(
        "---\ntype: concept\nslug: refund\ntitle: Refund\n---\n"
        "# Refund\n\n- code: `src/refund.py::refund`\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    (tmp_path / "src/refund.py").write_text("def refund(amount):\n    return -amount\n",
                                             encoding="utf-8")

    service_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    refund_digest = hashlib.sha256(b"stale refund text\n").hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=service_digest),
                    source_snapshots.SourceFile(path="src/refund.py",
                                                 content_sha256=refund_digest),
                ),
            ),
        ),
    )
    catalog_path = source_snapshots.catalog_path(tmp_path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")

    assert main([
        "-C", str(tmp_path), "stamp", "--from-catalog", "--path",
        "docs/features/billing/charge.md",
    ]) == 0

    assert f"@{service_digest[:12]}" in billing.read_text(encoding="utf-8")
    assert "@" not in refund.read_text(encoding="utf-8")
    assert catalog_path.exists(), "a --path migration must not delete the catalog"

    # The still-unmigrated page's row is still readable -- nothing was lost.
    assert main([
        "-C", str(tmp_path), "stamp", "--from-catalog", "--path",
        "docs/features/billing/refund.md",
    ]) == 0
    assert f"@{refund_digest[:12]}" in refund.read_text(encoding="utf-8")
    assert catalog_path.exists(), "a --path migration must not delete the catalog"


def test_cli_stamp_from_catalog_whole_book_keep_catalog_flag_skips_deletion(tmp_path: Path):
    feature = tmp_path / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n- code: `src/service.py::charge`\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    service_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=service_digest),
                ),
            ),
        ),
    )
    catalog_path = source_snapshots.catalog_path(tmp_path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")

    assert main(["-C", str(tmp_path), "stamp", "--from-catalog", "--keep-catalog"]) == 0

    assert f"@{service_digest[:12]}" in feature.read_text(encoding="utf-8")
    assert catalog_path.exists(), "--keep-catalog must skip deletion even in whole-book mode"


def test_cli_stamp_from_catalog_whole_book_covers_every_surface_sharing_one_catalog(
    tmp_path: Path,
):
    # One `sources.json` can be shared by several sibling surfaces under the same features
    # root (e.g. several books in a multi-repo workspace). Whole-book `--from-catalog` must
    # migrate every one of them before deleting the catalog -- if `graph.ui_nodes` only saw
    # a subset, deleting afterward would permanently lose the rest's digests.
    billing = tmp_path / "docs/features/billing/charge.md"
    billing.parent.mkdir(parents=True, exist_ok=True)
    billing.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n- code: `src/service.py::charge`\n",
        encoding="utf-8",
    )
    shipping = tmp_path / "docs/features/shipping/track.md"
    shipping.parent.mkdir(parents=True, exist_ok=True)
    shipping.write_text(
        "---\ntype: concept\nslug: track\ntitle: Track\n---\n"
        "# Track\n\n- code: `src/tracking.py::track`\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    (tmp_path / "src/tracking.py").write_text("def track(order):\n    return order\n",
                                               encoding="utf-8")

    service_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    tracking_digest = hashlib.sha256(b"def track(order):\n    return order\n").hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=service_digest),
                    source_snapshots.SourceFile(path="src/tracking.py",
                                                 content_sha256=tracking_digest),
                ),
            ),
        ),
    )
    catalog_path = source_snapshots.catalog_path(tmp_path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")

    assert main(["-C", str(tmp_path), "stamp", "--from-catalog"]) == 0

    assert f"@{service_digest[:12]}" in billing.read_text(encoding="utf-8")
    assert f"@{tracking_digest[:12]}" in shipping.read_text(encoding="utf-8")
    assert not catalog_path.exists()


def test_stamp_touches_exactly_the_targets_doctor_flags_as_unstamped_citation(tmp_path: Path):
    # Regression for the bare-target bug: `doctor`'s grounding check and `stamp` must agree on
    # which targets are "cited but not yet stamped" -- a bare target `doctor` flagged that
    # `stamp` silently skipped is exactly how the bug went unnoticed (doctor kept warning,
    # stamp never cleared it, forever).
    from ostler import doctor
    from ostler.model import load

    feature = tmp_path / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        "- code: `src/service.py::charge`\n"
        "- code: src/other.py::other\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    (tmp_path / "src/other.py").write_text("def other():\n    pass\n", encoding="utf-8")

    before = doctor.run(load(tmp_path))
    flagged = {f.ref for f in before.findings if f.code == "unstamped-citation"}
    assert flagged == {"src/service.py::charge", "src/other.py::other"}

    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.stamped == len(flagged)
    assert result.unresolved == []

    after = doctor.run(load(tmp_path))
    assert not {f.ref for f in after.findings if f.code == "unstamped-citation"}


def test_stamp_page_stamps_a_non_utf8_file_without_crashing(tmp_path: Path):
    # The original crash: `.read_text(encoding="utf-8")` on a cited file that is not valid
    # UTF-8 (a `.docx`, a stray binary) raised `UnicodeDecodeError` uncaught. Byte-based
    # hashing never decodes, so this must stamp cleanly instead.
    feature = _book(tmp_path, "`src/legacy.php`")
    data = b"<?php\n// \xff\xfe not valid utf-8\necho 1;\n"
    target = tmp_path / "src/legacy.php"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")

    assert result.stamped == 1
    assert result.unresolved == []
    expected = stamp.digest_file(data)
    assert f"`src/legacy.php` @{expected}" in feature.read_text(encoding="utf-8")


def test_stamp_page_from_catalog_migrates_an_unchanged_crlf_file_to_its_byte_digest(
    tmp_path: Path,
):
    # The retired catalog's own recipe decoded then hashed the text, which `read_text`
    # translates CRLF -> LF on the way through -- so a CRLF file's legacy digest never equals
    # its byte digest. A file unchanged since the catalog was built must still migrate forward
    # onto its *byte* digest (what live stamping produces from here on), not the catalog's
    # value, or `stale-citation` would immediately fire on a file nobody touched.
    from ostler import doctor
    from ostler.model import load

    root = tmp_path
    _book(root, "`src/service.py::charge`")
    crlf_bytes = SERVICE.replace("\n", "\r\n").encode()
    target = _service(root)
    target.write_bytes(crlf_bytes)
    legacy_digest = hashlib.sha256(SERVICE.encode()).hexdigest()  # read_text's CRLF -> LF
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=legacy_digest),
                ),
            ),
        ),
    )

    result = stamp.stamp_page_from_catalog(root, "docs/features/billing/charge.md", catalog)

    byte_digest = stamp.digest_file(crlf_bytes)
    assert byte_digest != legacy_digest[:12]
    assert result.stamped == 1
    text = (root / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{byte_digest}" in text

    report = doctor.run(load(root))
    assert not any(
        f.ref.startswith("src/service.py::charge@")
        for f in report.findings if f.code == "stale-citation"
    )


def test_stamp_page_from_catalog_keeps_a_changed_crlf_files_catalog_digest_and_it_reports_stale(
    tmp_path: Path,
):
    from ostler import doctor
    from ostler.model import load

    root = tmp_path
    _book(root, "`src/service.py::charge`")
    original_crlf = SERVICE.replace("\n", "\r\n").encode()
    legacy_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=legacy_digest),
                ),
            ),
        ),
    )
    # The live file has drifted since the catalog was built: different content entirely, not
    # just the CRLF translation the bridge tolerates.
    target = _service(root, "def charge(amount):\n    return amount * 2\n")
    target.write_bytes(target.read_text(encoding="utf-8").replace("\n", "\r\n").encode())

    result = stamp.stamp_page_from_catalog(root, "docs/features/billing/charge.md", catalog)

    assert result.stamped == 1
    text = (root / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{legacy_digest[:12]}" in text
    assert f"@{legacy_digest[:12]}" != f"@{stamp.digest_file(original_crlf)}"

    report = doctor.run(load(root))
    stale_refs = {f.ref for f in report.findings if f.code == "stale-citation"}
    assert any(ref.startswith("src/service.py::charge@") for ref in stale_refs)

