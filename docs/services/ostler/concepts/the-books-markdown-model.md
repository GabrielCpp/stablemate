---
type: concept
slug: the-books-markdown-model
title: The book's markdown model
---
# The book's markdown model

Every `ostler` command that reads or edits a book first loads it into one `Graph`: the in-memory
model `model.py` builds by walking the fixed doc roots and parsing every markdown page underneath. `load`
finds the repository root (`find_root`), resolves where each declared kind of document lives
(`doc_roots`: each kind at its built-in path under `docs/`, specs in the artifacts dir, and any `dynamic_registry.TemplateKind` at its default path), and returns
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

- code: ostler/ostler/model.py::Graph@b0f81cc8ce8a
- code: ostler/ostler/model.py::UINode@b0f81cc8ce8a
- code: ostler/ostler/model.py::Story@b0f81cc8ce8a
- code: ostler/ostler/model.py::Epic@b0f81cc8ce8a
- code: ostler/ostler/model.py::Milestone@b0f81cc8ce8a
- code: ostler/ostler/model.py::FeatureRecord@b0f81cc8ce8a
- code: ostler/ostler/model.py::SeedItem@b0f81cc8ce8a
- code: ostler/ostler/model.py::Entry@b0f81cc8ce8a
- code: ostler/ostler/model.py::load@b0f81cc8ce8a
- code: ostler/ostler/model.py::find_root@b0f81cc8ce8a
- code: ostler/ostler/model.py::doc_roots@b0f81cc8ce8a
- code: ostler/ostler/model.py::read_doc@b0f81cc8ce8a
- code: ostler/ostler/model.py::read_links@b0f81cc8ce8a
- code: ostler/ostler/model.py::required_section_problems@b0f81cc8ce8a
- code: ostler/ostler/model.py::section_order_problems@b0f81cc8ce8a
- code: ostler/ostler/model.py::story_status@b0f81cc8ce8a
- code: ostler/ostler/model.py::story_dependencies@b0f81cc8ce8a
- code: ostler/ostler/model.py::story_fixtures@b0f81cc8ce8a
- code: ostler/ostler/markdown.py::MarkdownDoc@115245786c4b
- code: ostler/ostler/markdown.py::Section@115245786c4b
- code: ostler/ostler/markdown.py::Bullet@115245786c4b
- code: ostler/ostler/markdown.py::Table@115245786c4b
- code: ostler/ostler/markdown.py::References@115245786c4b
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/markdown.py::split@115245786c4b
- code: ostler/ostler/graph.py::build@bfbff4611a77
- code: ostler/ostler/graph.py::subset@bfbff4611a77
- code: ostler/ostler/graph.py::select@bfbff4611a77
- code: ostler/ostler/graph.py::render_text@bfbff4611a77
- code: ostler/ostler/graph.py::render_tree@bfbff4611a77
- code: ostler/ostler/graph.py::render_ids@bfbff4611a77
- code: ostler/ostler/links.py::LinkResolver@471fa7366668
- code: ostler/ostler/links.py::LinkTarget@471fa7366668
- code: ostler/ostler/links.py::is_doc_link@471fa7366668
- code: ostler/ostler/refs.py::CodeRef@5de8b2ec8022
- code: ostler/ostler/refs.py::parse_code_ref@5de8b2ec8022
- code: ostler/ostler/refs.py::render_code_ref@5de8b2ec8022
- code: ostler/ostler/refs.py::strip_digest@5de8b2ec8022
- code: ostler/ostler/refs.py::bullet_ref@5de8b2ec8022
- code: ostler/ostler/refs.py::is_test_source@5de8b2ec8022
- code: ostler/ostler/registry.py::SectionSpec@5da47ef8ddca
- code: ostler/ostler/registry.py::EntityType@5da47ef8ddca
- code: ostler/ostler/registry.py::epic_seq@5da47ef8ddca
- code: ostler/ostler/registry.py::normative_keys@5da47ef8ddca
- code: ostler/ostler/registry.py::unknown_bullet_keys@5da47ef8ddca
- code: ostler/ostler/registry.py::doc_root_of@5da47ef8ddca
- code: ostler/ostler/registry.py::type_of@5da47ef8ddca
- code: ostler/ostler/schemas.py::load@17d011398cb2
- code: ostler/ostler/schemas.py::validate@17d011398cb2
- code: ostler/ostler/syntax.py::parse@0850b2c61451
- code: ostler/ostler/syntax.py::language_for@0850b2c61451
- code: ostler/ostler/syntax.py::walk@0850b2c61451
- code: ostler/ostler/values.py::_url@5fe41ca9c074
- code: ostler/ostler/values.py::dialog_answer@5fe41ca9c074
- code: ostler/ostler/untyped.py::is_mapping@c964a61d4a94
- code: ostler/ostler/util.py::is_mapping@6c753ed2df8c
- code: ostler/ostler/index.py::IndexStore@cfb08df1cba1
- code: ostler/ostler/index.py::epoch@cfb08df1cba1
- code: ostler/ostler/index.py::content_sha@cfb08df1cba1
- code: ostler/ostler/index.py::clean@cfb08df1cba1
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/index.py::use@cfb08df1cba1
- code: ostler/ostler/index.py::session@cfb08df1cba1
- code: ostler/ostler/query.py::search@9c9d233e28a0
- code: ostler/ostler/query.py::query@9c9d233e28a0
- code: ostler/ostler/query.py::list_entities@9c9d233e28a0
- code: ostler/ostler/provenance.py::story_commits@61d8f7f21af4
- code: ostler/ostler/provenance.py::source_freshness@61d8f7f21af4
- code: ostler/ostler/provenance.py::story_provenance@61d8f7f21af4
- code: ostler/ostler/provenance.py::node_provenance@61d8f7f21af4
- code: ostler/ostler/provenance.py::checkout_for@61d8f7f21af4
- code: ostler/ostler/result.py::Result@f4149eb63e51
- code: ostler/ostler/keys.py::pressable@a22c2b93f53b
- code: ostler/ostler/__init__.py@994811fd4652
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
