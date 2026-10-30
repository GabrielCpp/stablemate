---
type: concept
slug: the-books-markdown-model
title: The book's markdown model
---
# The book's markdown model

Every `ostler` command that reads or edits a book first loads it into one `Graph`: the in-memory
model `model.py` builds by walking the fixed doc roots and parsing every markdown page underneath. `load`
finds the repository root (`find_root`), refuses to go on while the artifacts dir or the repository still holds the old shelf layout, resolves where each declared kind of document lives
(`doc_roots`: services, milestones, decisions and ADRs at their built-in paths under `docs/`, epics, specs and the register at the top level of the artifacts dir, and any `dynamic_registry.TemplateKind` at its default path), and returns
a `Graph` holding every `UINode` (a typed node of the OKF UI profile), `Story`, `Epic`,
`Milestone`, `FeatureRecord` and `SeedItem` the walk found. `_Cached` and `_DocProducts` hold one
path's parsed products for the life of the process, so a second read of the same file in the same
command reuses the parse instead of repeating it; `read_doc` and `read_links` are the entry points
that populate this cache, and `_persist` is what a write command flushes back through. `Entry`
models one item of an `entries=True` key's nested list together with what it states about itself.
A handful of top-level checks read the whole graph for a cross-cutting shape problem rather than
one node's bullets: `required_section_problems` and `section_order_problems` check a page's
`## Heading`s against its type's `SectionSpec`s, and `story_status`/`story_dependencies`/
`story_fixtures` read a story's own declared bullets back out of its `UINode`.

`markdown.py` parses one page's raw text into the structures `model.py` holds: `MarkdownDoc` is a
page's frontmatter plus body, `Section` one `##`-delimited region, `Bullet` one `- key: value`
line with its source span, and `Table` a GFM pipe table with header, rows and span. `split`
divides a raw file into frontmatter and body before either is parsed. `References` and
`extract_refs` collect every link a document makes, and the remaining private helpers
(`iter_links`, `leading_code_spans`, `all_code_spans`, `prose_text`, `text_beside_links`,
`code_line_spans`, `comment_blocks`) locate a markdown link or a fenced/inline code span inside a
line of prose, which is how a `code:` bullet's citation and a page's ordinary prose links are told
apart.

`graph.py` answers "what part of the graph does this command apply to". `build` turns a raw walk
into the queryable shape, `subset` narrows a `Graph` to one surface or screen's reachable nodes,
and `select` and the path-matching helpers (`_parse_path`, `_match_path`, `_seg_match`, `_hops_to`,
`_root_of`, `_orphan_ids`) resolve a dotted path argument like a CLI command's `--surface`/`--node`
flag against the live graph. `render_text`, `render_tree` and `render_ids` are the three shapes a
selection can be printed in.

`links.py`'s `LinkResolver` and `LinkTarget` resolve a markdown link's href to the page it
actually points at, and `is_doc_link` tells a documentation link apart from an external URL.
`refs.py` is the sibling parser for a `code:`/`tests:` bullet's value rather than a markdown link:
`CodeRef` is one parsed reference, `parse_code_ref` and `render_code_ref` convert a bullet string
to and from it, `strip_digest` drops a `@hash` suffix, `normalize_ref` and `ref_path` compare two
references for the same underlying file, `bare_targets` and `code_refs` collect every reference a
page makes, `bullet_ref` reads the one off a single bullet, and `is_test_source` tells a
`tests:`-rooted reference apart from a `code:`-rooted one.

`registry.py` is the book's type vocabulary, read by every other module in this group rather than
owning data itself: `SectionSpec` is one required heading; `EntityType` and `UINodeType` describe
a kind of node or page; `epic_seq`/`epic_slug`/`epic_dir_name`/`next_epic_seq` parse and mint an
epic directory's numeric prefix; `normative_keys`, `declared_keys`, `check_keys`, `fixture_keys`,
`performed_keys`, `arrange_keys`, `condition_keys`, `address_keys`, `refusal_keys`,
`capture_keys`, `attached_keys` and their `attributed_*` counterparts each name the bullet keys of
one kind that carry a particular obligation; `unknown_bullet_keys`, `owning_keys`,
`self_declared_empty`, `states_no_claim`, `normative_claims`, `claim_groups`, `listed_checks` and
`undetermined_claims` classify a node's declared bullets into what it actually claims;
`doc_root_of`, `type_of`, `base_type`, `spec_type_for`, `ui_type`, `ui_type_named` and
`is_known_type` map a page's declared `type:` to the kind it belongs to; `SeedSpec` describes a
seed file's shape.

`schemas.py`'s `load` and `validate` check a structured document (a stack file, a seed file)
against its bundled JSON Schema. `syntax.py` wraps tree-sitter for every non-Python source
language a `code:` reference can point into: `_parser`/`_tree`/`parse` build a parse tree,
`language_for` picks the grammar by file extension, `walk` and `text_of`/`field_text` traverse it,
and `error_names` and `grammar_version`/`_distribution_version` report a parse failure or the
grammar build in use. `values.py` parses the handful of bullet value shapes with their own
grammar: `_url`, `_http_method`, `_checkout_path` and `dialog_answer`/`_dialog_answer`.
`untyped.py` and `util.py` each supply an `is_mapping` test (and `untyped.py` an `is_sequence`
one) used where a bullet's YAML-decoded value needs a type check before the typed parsers above
run on it.

`index.py` is the on-disk half of the caching `model.py`'s in-memory `_Cached` only covers within
one process: `IndexStore` is a content-addressed store of parse products for one repository root,
keyed by `epoch` (a single combined hash over every input that could invalidate it —
`epoch_inputs`, `_schemas_material`, `_kinds_material`, `_config_material`, `_freeze_material`,
`_shape_material`, `_ostler_version`); `content_sha`/`_file_sha`/`_sha` hash one file's content,
`_nested_types`/`_reachable_dataclasses`/`dataclass_shape_digest` hash a dataclass's shape so a
code change to a model class invalidates the store without a content change to any book file;
`clean` discards a store, and `active`/`use`/`session` manage which store is current for the
block a command runs in.

`query.py`'s `search` and `query` answer a free-text or typed lookup across the graph —
`list_entities`, `_story_row`, `_ui_row`, `_seed_row` and `_body_text` build the per-entity rows a
query matches against, and `_surfaces_referenced` collects which surfaces a result touches.
`provenance.py` answers a different question, when rather than what: `story_commits` and
`_trailers` find every commit carrying a story's exact `Story:` trailer, `source_freshness` and
`_context` compare a node's cited source against the commit history to flag it stale,
`story_provenance`/`node_provenance` render a story's or node's full commit history, and
`checkout_for`/`default_repository` resolve which of a run's several checkouts a `code:` target's
repository name points into.

`result.py`'s `Result` is the one success/message/paths record every mutating command in this
group (and most of the scaffolding and editing group) returns. `keys.py`'s `pressable` and `_key`
parse a `press:` bullet's key name against the small grammar of pressable key names a book can
declare. `__init__.py` is empty.

- code: ostler/ostler/model.py::Graph@4cecd6440d86
- code: ostler/ostler/model.py::UINode@c71aa17614e7
- code: ostler/ostler/model.py::Story@cc19afdc0a41
- code: ostler/ostler/model.py::Epic@0351d65b6600
- code: ostler/ostler/model.py::Milestone@a31e4c596fca
- code: ostler/ostler/model.py::FeatureRecord@f25f266314bb
- code: ostler/ostler/model.py::SeedItem@50d55f6e9e46
- code: ostler/ostler/model.py::Entry@5c7160a18c7a
- code: ostler/ostler/model.py::load@cd542ca5a0c9
- code: ostler/ostler/model.py::find_root@a03e6d51e782
- code: ostler/ostler/model.py::doc_roots@cc98ffe30811
- code: ostler/ostler/model.py::read_doc@839985ca5f85
- code: ostler/ostler/model.py::read_links@128fefe4d140
- code: ostler/ostler/model.py::required_section_problems@881f2776d757
- code: ostler/ostler/model.py::section_order_problems@178ff01958c8
- code: ostler/ostler/model.py::story_status@33102012c194
- code: ostler/ostler/model.py::story_dependencies@9d4b58f829c6
- code: ostler/ostler/model.py::story_fixtures@79a7512d2bcc
- code: ostler/ostler/markdown.py::MarkdownDoc@dea72bc55864
- code: ostler/ostler/markdown.py::Section@afb0fa4199ad
- code: ostler/ostler/markdown.py::Bullet@15867fcf658b
- code: ostler/ostler/markdown.py::Table@e4c1cca15127
- code: ostler/ostler/markdown.py::References@e80fb1ecfb9e
- code: ostler/ostler/markdown.py::extract_refs@185c57ef4c03
- code: ostler/ostler/markdown.py::split@d8192b004ec9
- code: ostler/ostler/graph.py::build@31a892ee2146
- code: ostler/ostler/graph.py::subset@5ff191ccb1b9
- code: ostler/ostler/graph.py::select@fd0edfdfcb48
- code: ostler/ostler/graph.py::render_text@25fb5eed1cb9
- code: ostler/ostler/graph.py::render_tree@1d10055fb631
- code: ostler/ostler/graph.py::render_ids@0a6cafd97470
- code: ostler/ostler/links.py::LinkResolver@c854ba2f8176
- code: ostler/ostler/links.py::LinkTarget@ffc21e8050df
- code: ostler/ostler/links.py::is_doc_link@aa0ea7dd1ae5
- code: ostler/ostler/refs.py::CodeRef@77592b00fec4
- code: ostler/ostler/refs.py::parse_code_ref@86a4a16ae9a1
- code: ostler/ostler/refs.py::render_code_ref@c419159581a5
- code: ostler/ostler/refs.py::strip_digest@11601062492e
- code: ostler/ostler/refs.py::bullet_ref@a1a41caa5b7f
- code: ostler/ostler/refs.py::is_test_source@16692ca38f54
- code: ostler/ostler/qa/context.py::_is_non_production_path@30ef25affa37
- code: ostler/ostler/registry.py::SectionSpec@191fd87ca41d
- code: ostler/ostler/registry.py::EntityType@285a52342af6
- code: ostler/ostler/registry.py::epic_seq@48ab4844ac7b
- code: ostler/ostler/registry.py::normative_keys@57fd51c6a734
- code: ostler/ostler/registry.py::unknown_bullet_keys@6e0b920dbb8a
- code: ostler/ostler/registry.py::doc_root_of@f4b419e184ee
- code: ostler/ostler/registry.py::type_of@358aaeed15b3
- code: ostler/ostler/schemas.py::load@6a7bb5ce312a
- code: ostler/ostler/schemas.py::validate@8901df4c3ca5
- code: ostler/ostler/syntax.py::parse@b9a90028e72c
- code: ostler/ostler/syntax.py::language_for@5b80fb0f6273
- code: ostler/ostler/syntax.py::walk@b82da7c10d86
- code: ostler/ostler/values.py::_url@1ddcb7976ef2
- code: ostler/ostler/values.py::dialog_answer@e0f43edd44dc
- code: ostler/ostler/untyped.py::is_mapping@58e488a40df0
- code: ostler/ostler/util.py::is_mapping@12fd23931817
- code: ostler/ostler/index.py::IndexStore@139843410cfb
- code: ostler/ostler/index.py::epoch@3b1f97e9f7e9
- code: ostler/ostler/index.py::content_sha@85504fd5170e
- code: ostler/ostler/index.py::clean@9ac0c4043bc8
- code: ostler/ostler/index.py::active@bb6bee252338
- code: ostler/ostler/index.py::use@910af9a1bd74
- code: ostler/ostler/index.py::session@f052b19671d8
- code: ostler/ostler/query.py::search@354430186027
- code: ostler/ostler/query.py::query@dee579a3cb02
- code: ostler/ostler/query.py::list_entities@b6cce43b16aa
- code: ostler/ostler/provenance.py::story_commits@a8e110557895
- code: ostler/ostler/provenance.py::source_freshness@9f49205b3fd4
- code: ostler/ostler/provenance.py::story_provenance@5ac7b3748da3
- code: ostler/ostler/provenance.py::node_provenance@1ef40f990f5b
- code: ostler/ostler/provenance.py::checkout_for@c798b5423249
- code: ostler/ostler/result.py::Result@70521683fe83
- code: ostler/ostler/keys.py::pressable@c60cef0f162a
- code: ostler/ostler/__init__.py@994811fd4652
- rule: the grounding gate and doctor share one definition of test source, so a path doctor forbids in `code:` is never demanded by the gate
- detail: [ostler](../cli.md)

## Contract

- one graph per command: a command loads one `Graph` with `model.py`'s `load` and reads or edits
  through it; nothing in this group reaches back to disk mid-command outside the `_Cached`/
  `IndexStore` layers those functions already manage.
- epoch invalidation is content-addressed, not time-addressed: `index.py`'s `epoch` changes when
  any input `epoch_inputs` names changes content, never on a clock, so a store survives untouched
  across runs that change nothing it depends on.
- a code reference always resolves through `refs.py`: `normalize_ref`/`ref_path` are the only
  comparison a citation check or a provenance lookup uses to decide two `code:` bullets name the
  same file, never a raw string comparison of the bullet text.
- a reference parses before it is walked: `syntax.py`'s `parse` always returns a tree (with
  `error_names` reporting what failed to parse inside it) rather than raising, so a malformed
  source file is a finding some other check reports, not a crash in the parser.
