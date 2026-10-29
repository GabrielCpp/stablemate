---
type: concept
slug: scaffolding-and-editing-book-files
title: Scaffolding and editing book files
---
# Scaffolding and editing book files

`crud_generic.py` is the generic instance CRUD every user-declared kind from `dynamic_registry.py`
shares: `create_instance`, `find_instance`, `edit_instance` and `delete_instance` resolve a kind
name to its `TemplateKind` (`_kind_by_name`), find or build the instance's path from its
`path_template` (`_resolve_path`, `_find_path`, `_instance_name`, `_safe_component`), and list
what already exists under a kind (`_kind_children`). `dynamic_registry.py` is the model and
storage these commands and `ostler new`'s built-in kinds both read: `TemplateKind` is one
declared kind (its `doc_root`, `path_template`, `parent`, required fields), `load_raw`/`save_raw`
read and write one repo's `.agents/templates.yml`, `parse_kind`/`load_kinds` turn that file's
`kinds:` entries into `TemplateKind`s, `as_entity_types` reduces them to the shape `doctor.py`'s
conformance walk consumes, and `validate_kinds` runs the hard-error checks (name collision, a
`parent` that is not bundle-shaped, `extra_files` on a leaf-shaped kind) at `template new`/`edit`
time rather than on every `load_kinds`. `templates.py` is the command layer on top:
`new`/`find`/`edit`/`delete`/`apply` manage a template definition itself (not an instance of one),
`edit` applies `kind.field=value` assignments before re-validating, and `apply` scaffolds each
declared kind's `default_path` directory and injects a `### <title>` section into the project's
`CLAUDE.md` between generated markers (`_claude_section`, `_inject_claude_md`) so an applied
template's usage is discoverable without reading `templates.yml`.

`scaffold.py`'s `scaffold` is the entry point behind `ostler new`: it builds a new page's body
from its kind's bundled template (`_file_body`), stubs out the bullets the kind's `required`
list names (`_bullet_stubs`), and either writes a new file or resolves into an existing one at a
`#heading` (`_resolve_in_file`); `_scaffold_hosted_page` and `_scaffold_section` cover the two
cases where a new kind nests under an existing page rather than getting its own file, and
`_list_under` lists what already exists under a parent for a `new`/`find` prompt. `stamp.py`
keeps a scaffolded page's leading `code:`/`tests:` bullets in sync with the file they cite:
`digest_file` hashes a source file's content, `digest_citation` hashes only the declarations a
symbol citation names (the whole file for a citation with no symbol), `citation_is_fresh` accepts
either that digest or the whole-file digest older pages carry, `stamp_page`/`stamp_page_from_catalog` rewrite a
bullet's `@hash` suffix to match, `restamp_leading_code_spans`/`_restamp_bare` do the same for a
bare citation with no symbol, `unstamp_text` strips every digest back out for a diff-friendly
view, and `node_line_range`/`stamp_targets` find which lines of a page a given node's bullets
occupy. `_legacy_text_digest` computes the pre-stamping digest format a migrated page may still
carry.

`edit.py` is the general-purpose rewrite layer several CLI commands share: `relink` and `rename`
move a page or rewrite every link to it (`_doc_files`, `_replace_token`, `_href_style_and_target`
preserving a link's original relative-vs-absolute style); `migrate_context`/`_navigate` walk a
legacy-layout page forward to its new location; `_story_status_change`/`_set_status_bullet` and
`_ledger_change` apply one status or ledger transition to a story or data-state node;
`settle_review`/`settle_answers` close out a review's answered questions, and `_verify_finding`
checks a proposed edit does not introduce a new problem before it is written. `FileChange` and
`EditPlan` are the dry-run shape every one of these returns before anything touches disk.

`carve.py` and `fragment_carve.py` split one large page into several smaller, still-linked ones:
`carve.py`'s `carve_endpoints` is the entry point for splitting a server page's endpoints out one
per file, computing each new page's slice of the original (`_units`, `_target`, `_on_targets`,
`_shifted`, `_trim`), rendering it with its own address section and anchors
(`_endpoints_section`, `_heading_anchors`, `_address_map`, `_build_page`), rewriting the
remaining server page to be slimmer (`_slim_server`) and every reference to a moved endpoint to
point at its new page (`references`, `_claims`, `_broken`, `_rewrite`). `fragment_carve.py`'s
`carve_fragments` is the same operation for a reusable UI fragment rather than a server endpoint:
`_apart`/`_pack`/`_chosen` decide which fragments are worth splitting out and `_slim` rewrites the
host page once they are.

`freeze.py` locks a page's content against accidental drift: `freeze` computes and stores a
content fingerprint (`resolve_content`, `fingerprint`) keyed by the node's id (`_ids_path`,
`_load_ids`), and `unfreeze` removes it; `FreezePlan` is the dry-run shape. `autofix.py` and
`fmt.py` are the two passes behind `ostler fmt`: `autofix.py`'s `run_autofix`/`fix_text` repair a
small, fixed set of common bullet mistakes (`_unwrap_code_span`, `_is_null_equals`,
`_colon_keywords_as_equals`) that would otherwise read as a different, wrong value;
`fmt.py`'s `run_fmt`/`format_text` then re-render the whole file canonically — frontmatter key
order (`_canonical_frontmatter`), bullet key order (`_bullet_key`, `_bullet_run`, `_bullet_edit`,
`_apply_edits`, `_emit_bullet`), and wikilink style (`_rewrite_wikilinks`) — over whichever files
`_target_files` selects. `AutofixResult` and `FmtResult` report what each pass changed.

- code: ostler/ostler/crud_generic.py::create_instance@2d516d90a9aa
- code: ostler/ostler/crud_generic.py::find_instance@cc9b09d4ada0
- code: ostler/ostler/crud_generic.py::edit_instance@fe2f9c78130f
- code: ostler/ostler/crud_generic.py::delete_instance@6e9445d72aa6
- code: ostler/ostler/dynamic_registry.py::TemplateKind@281308a1d7ab
- code: ostler/ostler/dynamic_registry.py::load_raw@5e91e288f526
- code: ostler/ostler/dynamic_registry.py::save_raw@fcfdf2bb268a
- code: ostler/ostler/dynamic_registry.py::parse_kind@eb8cb51a0dd4
- code: ostler/ostler/dynamic_registry.py::load_kinds@ca1b93afa65c
- code: ostler/ostler/dynamic_registry.py::as_entity_types@50d7ebcbe638
- code: ostler/ostler/dynamic_registry.py::validate_kinds@e250bf878f69
- code: ostler/ostler/templates.py::new@8f2b104898f6
- code: ostler/ostler/templates.py::find@3762ec681771
- code: ostler/ostler/templates.py::edit@f2174965bdfa
- code: ostler/ostler/templates.py::delete@8e819efb6258
- code: ostler/ostler/templates.py::apply@443ce594ae1d
- code: ostler/ostler/scaffold.py::scaffold@39706cfe7d01
- code: ostler/ostler/scaffold.py::_scaffold_hosted_page@c0dc91c5f8ae
- code: ostler/ostler/scaffold.py::_scaffold_section@ad26a161a34c
- code: ostler/ostler/stamp.py::digest_file@dc3807532e47
- code: ostler/ostler/stamp.py::digest_citation@dbcdb8522dc9
- code: ostler/ostler/stamp.py::citation_is_fresh@9e99ef458898
- code: ostler/ostler/stamp.py::stamp_page@8420b2b4484f
- code: ostler/ostler/stamp.py::stamp_page_from_catalog@c1399661dae6
- code: ostler/ostler/stamp.py::restamp_leading_code_spans@3a41b1e9be27
- code: ostler/ostler/stamp.py::unstamp_text@48d86562ace0
- code: ostler/ostler/stamp.py::node_line_range@b6cbb222cd95
- code: ostler/ostler/stamp.py::StampResult@e347524a8c26
- code: ostler/ostler/edit.py::relink@a715cceddf7a
- code: ostler/ostler/edit.py::rename@53ea9523590a
- code: ostler/ostler/edit.py::migrate_context@fc6c3d9315e1
- code: ostler/ostler/edit.py::settle_review@ac44167228b0
- code: ostler/ostler/edit.py::settle_answers@112369669e6b
- code: ostler/ostler/edit.py::FileChange@cfc47dc3aec9
- code: ostler/ostler/edit.py::EditPlan@0102ac442561
- code: ostler/ostler/carve.py::carve_endpoints@8f34975f765d
- code: ostler/ostler/carve.py::references@7c397615aad5
- code: ostler/ostler/carve.py::CarvePlan@eeb1c1b27b2c
- code: ostler/ostler/fragment_carve.py::carve_fragments@9b1e415c5333
- code: ostler/ostler/freeze.py::freeze@cce15a1cc8f8
- code: ostler/ostler/freeze.py::unfreeze@c8162e6a2793
- code: ostler/ostler/freeze.py::fingerprint@ff9181d26dbf
- code: ostler/ostler/freeze.py::FreezePlan@46ff024d4d77
- code: ostler/ostler/autofix.py::run_autofix@e65fcc1b1bb7
- code: ostler/ostler/autofix.py::fix_text@19668ae09cdf
- code: ostler/ostler/autofix.py::AutofixResult@012563083f99
- code: ostler/ostler/fmt.py::run_fmt@cce8547cf398
- code: ostler/ostler/fmt.py::format_text@c30e6bc6c425
- code: ostler/ostler/fmt.py::FmtResult@6fa0ab31b1c7
- detail: [The book's markdown model](the-books-markdown-model.md)
- detail: [ostler](../cli.md)

## Contract

- a plan before a write: every command in this group returns a dry-run shape (`Result`,
  `FileChange`/`EditPlan`, `CarvePlan`, `FreezePlan`, `AutofixResult`, `FmtResult`) describing
  what it would change before — or instead of — writing it, so a caller can show a diff first.
- a declared kind validates once, at the template boundary: `validate_kinds` runs when a template
  is created or edited, not on every `load_kinds`, so a book that already has a template applied
  is never re-validated just for reading it.
- fmt runs after autofix: `autofix.py` repairs a misread bullet (a wrong key, an unwrapped code
  span) before `fmt.py` re-renders the file canonically, so canonical formatting never has to
  account for a value fmt itself would misparse.
- a stamped digest covers one citation, not the file: `stamp_page` rewrites the `@hash` suffix on
  the bullet that cites a file, never the cited file itself, so stamping a book page never
  touches product source.
- rule: a symbol citation's stamp covers the cited declaration, not the whole file. An edit
  elsewhere in the file leaves the citation fresh, so a code change after a story documented a
  file restamps nothing it did not touch. The tradeoff: a change outside the declaration that
  alters what it means, such as a constant it reads, no longer flags the citation. A citation
  with no symbol keeps the whole-file digest, and a page stamped before this rule stays fresh
  until its file changes.
