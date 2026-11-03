---
type: concept
slug: the-text-index
title: The text index
---
# The text index

`ostler search` ranks sections, not files. The index holds one row per markdown section of every page
under every document root the graph loads: the book, epics, milestones, template kinds, and the
artifacts roots for specs, the register and the architecture decision records, and the docs home's
`docs/decisions` folder. The specs root contributes only the files directly in a story's spec folder,
where the format places a spec. A QA run's results sit below that folder and are not searched. A decision's slug is its folder name, its title is its `summary` and its
`summary` is a row of its own, so a word of the slug finds a decision that has no text yet. The text before a page's first heading is a row
of its own. A section with no text of its own has no row.

A search with no `--root` and no `--type` reads the current knowledge: the service books, the decisions, the architecture decision records and any template kind's root. It leaves out epics, milestones, specs and the register, which are plans and history. `--root` names one root, and `--root all` reads every root. `--type` reads that type wherever it sits. A fixture page stays out unless the search names `--type fixture` or `--root all`. A page gives at most two hits, so the next hits come from other pages.

The index leaves out `verify:`, `run:` and `fixture:` bullets and their continuation lines, so a section's snippet shows what it explains. A section holding only those bullets has no row. `code:` and `tests:` bullets stay, so a cited path finds its page.

A query is split into words, and each word becomes a prefix term. The terms are joined with OR and
ranked by BM25 with porter stemming, so "parallel" finds "parallelism". A match in the page title
weighs 10, in the slug 5, in the heading path 3 and in the body 1. A hit carries the section's page,
its anchor, its heading path and a snippet.

The store is a SQLite FTS5 file in the parse-index directory, one per repository. Each page is keyed
by the sha of its bytes, so a refresh re-reads only the pages that changed and drops the rows of the
pages that are gone. A change of the index epoch drops every row. With the parse index disabled the
store lives in memory for the one command and no file is written. `ostler index build` refreshes the
store and prints its counts.

- code: ostler/ostler/textindex.py::rows_for@8cef87954c77
- code: ostler/ostler/textindex.py::documents@5db0a195489b
- code: ostler/ostler/textindex.py::_without_checks@d87791288e05
- code: ostler/ostler/textindex.py::TextIndex.open@07a2697340db
- code: ostler/ostler/textindex.py::TextIndex.refresh@09cc8903f3a2
- code: ostler/ostler/textindex.py::TextIndex.search@efaf18dd94c9
- rule: search joins the question's terms with OR so an agent sends every spelling of a term in one call and ranking sorts them
- rule: a `decision.md` is indexed under the root `decisions` with the folder name as its slug and its `summary` as its title, so `ostler search` finds it by a word of its slug
- rule: the specs root indexes only the path the format declares for a spec, because a spec folder also holds QA results, and older runs left whole repository copies there that would rank as many identical hits
- rule: search defaults to current knowledge, because an agent asking how something works pays to read plans and history that no longer describe it; a caller reaches them by naming a root, a type or `all`
- rule: a page gives at most two hits, because the title weighs on every section of a page and one page would otherwise fill the list with near-equal scores
- rule: check bullets are not indexed, because they say how a claim is tested, and they filled the snippets of the hits they matched
- rule: a change to what a row holds changes the index's row format, because a page's rows are keyed by its bytes and would otherwise stay as they were
- rule: a hit is a section, so the caller reads the paragraph and then walks the node's edges with ostler trace
- tests: ostler/tests/test_textindex.py::test_rows_for_gives_preamble_and_section_rows
- tests: ostler/tests/test_textindex.py::test_title_match_outranks_body_match
- tests: ostler/tests/test_textindex.py::test_porter_stemming_finds_parallel
- tests: ostler/tests/test_textindex.py::test_refresh_is_incremental
- tests: ostler/tests/test_textindex.py::test_a_scenario_checkout_under_a_spec_is_not_searched
- tests: ostler/tests/test_textindex.py::test_a_refresh_drops_the_rows_of_a_copy_below_a_spec
- tests: ostler/tests/test_textindex.py::test_type_and_root_filters
- tests: ostler/tests/test_textindex.py::test_default_search_leaves_out_plans_and_history
- tests: ostler/tests/test_textindex.py::test_a_fixture_page_stays_out_until_asked_for
- tests: ostler/tests/test_textindex.py::test_one_page_cannot_fill_the_hits
- tests: ostler/tests/test_textindex.py::test_check_bullets_are_not_searched
- tests: ostler/tests/test_textindex.py::test_disabled_index_searches_without_a_file
- tests: ostler/tests/test_textindex.py::test_cli_index_build_json
