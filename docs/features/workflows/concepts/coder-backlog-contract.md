---
type: concept
slug: coder-backlog-contract
title: Coder backlog contract
---
# Coder backlog contract

The coder backlog is a parsed worklist shared by the filing adapter and the standalone fix
drain. Filing accepts item records from a story's `backlog-items.json`, normalizes their ids,
deduplicates by exact id, id-token set, or normalized description, and appends new bullets to
the configured backlog. The fix drain reads only `## Filed by coder`, selects the first
unblocked bullet, turns it into one authored story in the `fixes` epic, and settles it by either
removing the shipped bullet or appending a blocked annotation that later draws skip.

The parser is the boundary for all backlog edits: selection, blocking, and the direct prune
fallback use the same `ostler.markdown` bullet locations, so fenced examples and headings are
not mistaken for work items. Story creation is idempotent by the selected bullet id; an existing
story that covers that id is re-authored only in empty sections and reused.

- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::backlog_bullets`
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_backlog_items`
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::select_fix_item`
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::seed_fix_story`
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::prune_fix_item`
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::mark_fix_blocked`
- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_pruned_and_committed`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_second_failing_check_flags_rather_than_retrying_again`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_blocked_item_is_flagged_and_the_next_draw_skips_it`

## Fields

### line

- type: integer
- required: true
- verify: count(subject="backlog bullet line requirements", equals=1)
- semantics: zero-based absolute source-file line containing the parsed bullet, including front matter lines
- verify: count(subject="backlog edit locations", equals=1)

### id

- type: string
- required: true
- verify: count(subject="backlog bullet id requirements", equals=1)
- semantics: bracketed backlog handle used for selection, story coverage, pruning, and blocking
- verify: count(subject="identified backlog bullets", equals=1)

### text

- type: string
- required: true
- verify: count(subject="backlog bullet text requirements", equals=1)
- semantics: bullet description without its bracketed id; a blocked suffix is retained for visibility and removed from normalized identity comparisons
- verify: count(subject="backlog bullet descriptions", equals=1)

## Methods

### BacklogBullet.blocked

- sig: `BacklogBullet.blocked -> bool`
- does: returns true when the bullet text contains the case-insensitive `(blocked` marker
- returns: boolean indicating whether future fix selection must skip this bullet
- verify: count(subject="blocked backlog detection", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::BacklogBullet.blocked`

### backlog_bullets

- sig: `backlog_bullets(text: str, *, section: str = "") -> list[BacklogBullet]`
- does: parses markdown through `ostler.markdown` and returns bracketed backlog bullets in source order
- verify: count(subject="parsed backlog bullet lists", equals=1)
- does: when `section` is non-empty, limits results to that parsed section and returns an empty list when the section is absent
- verify: count(subject="section-scoped backlog bullet lists", equals=1)
- does: excludes bullets without an id and bullets inside fenced examples
- verify: count(subject="filtered backlog bullets", equals=1)
- returns: `BacklogBullet` records with file-absolute zero-based line locations
- verify: count(subject="backlog bullet records", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::backlog_bullets`

### Seen.add

- sig: `Seen.add(item_id: str, desc: str) -> None`
- does: records a non-empty id, its order-insensitive token set, and a non-empty normalized description for later duplicate checks
- returns: no value
- verify: count(subject="recorded backlog duplicate keys", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::Seen.add`

### Seen.duplicate

- sig: `Seen.duplicate(item_id: str, desc: str) -> bool`
- does: reports true when the id, id-token set, or normalized description has already been recorded
- verify: count(subject="backlog duplicate decisions", equals=1)
- returns: false for an item with no matching identity signal
- verify: count(subject="backlog duplicate misses", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::Seen.duplicate`

### kebab

- sig: `kebab(raw: str) -> str`
- does: lowercases the supplied value, replaces runs of non-alphanumeric/dot/underscore/hyphen characters with hyphens, and trims edge hyphens
- returns: stable sanitized backlog id
- verify: count(subject="sanitized backlog ids", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::kebab`

### norm_desc

- sig: `norm_desc(desc: str) -> str`
- does: removes a trailing blocked annotation, lowercases the description, replaces non-alphanumeric runs with spaces, and trims whitespace
- returns: normalized description key, or an empty string when no identity text remains
- verify: count(subject="normalized backlog descriptions", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::norm_desc`

### id_token_set

- sig: `id_token_set(item_id: str) -> frozenset[str]`
- does: splits an id on dots, hyphens, or underscores and lowercases the non-empty tokens
- verify: count(subject="split backlog id token sets", equals=1)
- returns: order-insensitive token set used by duplicate detection
- verify: count(subject="returned backlog id token sets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::id_token_set`

### file_backlog_items

- sig: `file_backlog_items(logger: logging.Logger, spec_dir: str = "", docs_path: str = "", repo_dir: str = "") -> BacklogDrain`
- does: resolves the docs root and reads `<spec_dir>/backlog-items.json`; an empty spec directory returns without changing the backlog
- verify: count(subject="reconciled backlog item files", equals=1)
- does: creates the configured backlog with `# Backlog` when it is absent and creation succeeds
- verify: count(subject="created missing backlogs", equals=1)
- does: appends valid non-duplicate items under their requested section, or under `## Filed by coder` when no section is supplied
- verify: count(subject="appended coder backlog bullets", equals=1)
- does: skips invalid or duplicate records, then removes the items file after reconciliation; it keeps the file when the backlog cannot be created or the unlink fails
- verify: count(subject="reconciled backlog item file outcomes", equals=1)
- returns: `BacklogDrain` counts and notes describing appended, skipped, and file-removal outcomes
- verify: count(subject="backlog drain results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::file_backlog_items`

### select_fix_item

- sig: `select_fix_item(logger: logging.Logger, docs_path: str = "", backlog_path: str = "", repo_dir: str = "") -> FixPick`
- does: resolves the configured backlog and searches only the parsed `## Filed by coder` section
- verify: count(subject="coder backlog sections searched", equals=1)
- does: skips blocked bullets and bullets with empty text, then returns the first remaining bullet without mutating the file
- verify: count(subject="selected unblocked backlog bullets", equals=1)
- does: reports a dry selection when the backlog file, section, or drainable bullet is absent
- verify: count(subject="dry backlog selections", equals=1)
- returns: `FixPick` containing the selected id and text, or a reason with no fix
- verify: count(subject="fix selection results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::select_fix_item`
- tests: `workflows/tests/coder/fix/test_flow.py::test_an_empty_backlog_does_not_enter_the_fix_loop`

### seed_fix_story

- sig: `seed_fix_story(logger: logging.Logger, bullet_id: str = "", bullet_text: str = "", epics_dir: str = "", epic: str = "", docs_path: str = "", repo_dir: str = "") -> FixStorySeed`
- does: resolves or self-creates the selected epic bucket, defaulting to the perpetual `fixes` bucket without registering it in the epic queue
- verify: count(subject="resolved fix story buckets", equals=1)
- does: reuses an existing story covering the bullet id and fills only empty required sections
- verify: count(subject="idempotent fix story reuses", equals=1)
- does: otherwise registers a researched seed and creates one story whose acceptance criteria contains exactly the selected bullet text
- verify: count(subject="new authored fix stories", equals=1)
- raises: `WorkflowFailed` when the bullet id or text is missing
- verify: count(subject="invalid fix story seed failures", equals=1)
- returns: `FixStorySeed` with the epic, story paths, bullet identity, and reuse/creation reason
- verify: count(subject="seeded fix stories", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::seed_fix_story`
- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_pruned_and_committed`

### prune_fix_item

- sig: `prune_fix_item(logger: logging.Logger, bullet_id: str = "", docs_path: str = "", backlog_path: str = "", repo_dir: str = "") -> FixPruned`
- does: removes the matching parsed bullet through Ostler, falling back to the configured custom backlog path when Ostler cannot prune it
- verify: removed(subject="the shipped coder backlog bullet")
- does: commits only the rewritten backlog path after a successful prune
- verify: count(subject="scoped backlog prune commits", equals=1)
- returns: `FixPruned` marked true for a removed bullet and false when no id or matching bullet exists
- verify: count(subject="backlog prune results", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::prune_fix_item`
- tests: `workflows/tests/coder/fix/test_flow.py::test_one_item_is_seeded_fixed_checked_pruned_and_committed`

### mark_fix_blocked

- sig: `mark_fix_blocked(logger: logging.Logger, bullet_id: str = "", note: str = "", docs_path: str = "", backlog_path: str = "", repo_dir: str = "") -> FixBlocked`
- does: appends `(blocked: <note>)` to the matching unblocked bullet and writes the backlog in place
- verify: count(subject="annotated blocked backlog bullets", equals=1)
- does: uses `qa failed after retry` when the note is empty, and leaves an already blocked bullet unchanged
- verify: unchanged(subject="an already blocked backlog bullet")
- returns: `FixBlocked` marked true for a found bullet, including an already blocked no-op, and false when the id or bullet is absent
- verify: count(subject="blocked coder backlog bullets", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/backlog.py::mark_fix_blocked`
- tests: `workflows/tests/coder/fix/test_flow.py::test_a_second_failing_check_flags_rather_than_retrying_again`
