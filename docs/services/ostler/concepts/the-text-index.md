---
type: concept
slug: the-text-index
title: The text index
---
# The text index

`ostler search` ranks sections, not files. The index holds one row per markdown section of every page
under every document root the graph loads: the book, epics, milestones, template kinds, and the
artifacts roots for specs, the register and the architecture decision records, and the docs home's
`docs/decisions` folder. A decision's slug is its folder name, its title is its `summary` and its
`summary` is a row of its own, so a word of the slug finds a decision that has no text yet. The text before a page's first heading is a row
of its own. A section with no text of its own has no row.

A query is split into words, and each word becomes a prefix term. The terms are joined with OR and
ranked by BM25 with porter stemming, so "parallel" finds "parallelism". A match in the page title
weighs 10, in the slug 5, in the heading path 3 and in the body 1. A hit carries the section's page,
its anchor, its heading path and a snippet.

The store is a SQLite FTS5 file in the parse-index directory, one per repository. Each page is keyed
by the sha of its bytes, so a refresh re-reads only the pages that changed and drops the rows of the
pages that are gone. A change of the index epoch drops every row. With the parse index disabled the
store lives in memory for the one command and no file is written. `ostler index build` refreshes the
store and prints its counts.

- code: ostler/ostler/textindex.py::rows_for@6e7935aa7652
- code: ostler/ostler/textindex.py::TextIndex.refresh@6e7935aa7652
- code: ostler/ostler/textindex.py::TextIndex.search@6e7935aa7652
- rule: search joins the question's terms with OR so an agent sends every spelling of a term in one call and ranking sorts them
- rule: a `decision.md` is indexed under the root `decisions` with the folder name as its slug and its `summary` as its title, so `ostler search` finds it by a word of its slug
- rule: a hit is a section, so the caller reads the paragraph and then walks the node's edges with ostler trace
- tests: ostler/tests/test_textindex.py::test_rows_for_gives_preamble_and_section_rows
- tests: ostler/tests/test_textindex.py::test_title_match_outranks_body_match
- tests: ostler/tests/test_textindex.py::test_porter_stemming_finds_parallel
- tests: ostler/tests/test_textindex.py::test_refresh_is_incremental
- tests: ostler/tests/test_textindex.py::test_type_and_root_filters
- tests: ostler/tests/test_textindex.py::test_disabled_index_searches_without_a_file
- tests: ostler/tests/test_textindex.py::test_cli_index_build_json
