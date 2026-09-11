---
type: concept
slug: okf-builder-audit-module
title: OKF-builder audit module
---
# OKF-builder audit module

- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py`

Run-owned semantic review receipts, rebuilt against current source and claims. The module manages the full lifecycle of audit evidence: preparing packets from source, managing review contracts to detect prompt/schema changes, persisting typed verdicts, and memoizing results so repeated assessments avoid redundant LLM calls.

## Configuration and Scope

### AuditScope
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::AuditScope`
- `docs_path` — root path to the documentation directory
- `source_path` — file or directory in source to audit
- `context_paths` — optional supporting files to include in context
- `service` — service name filter (empty string disables filtering)
- `max_packets` — limit on packets to assess in one pass; `None` means no limit
- `packet_max_items` — maximum candidates+claims per packet (default 80)
- `packet_max_chars` — maximum total characters per packet (default 60,000)
- tests: `workflows/tests/okf_builder/test_audit.py::test_support_context_reaches_packets_and_invalidates_receipts`
- tests: `workflows/tests/okf_builder/test_audit.py::test_missing_support_context_is_invalid_without_model_spend`

## Filter mechanisms and limitations

Each `AuditScope` field is one of a stack of filters that narrow the prepared audit; every
filter that takes a value out of scope names itself on `BehaviorAuditOutcome.limitations`
(`workflows/src/workhorse_workflows/okf_builder/shared/audit.py:536-538`), and the audit's two
final limitations — "Model judgments are not semantic proofs or whole-book completeness
guarantees." and "Selection limits apply to packets; omitted packets are not assessed." — are
appended to every outcome regardless of scope. The filters run during `preparation`, not on
the prepared result: filtering on the prepared result would still re-open and validate every
node off disk, which is what would fail this run on a sibling service's book while that
service's own run is authoring it (`ostler/ostler/behavior.py:294-298`).

### concept: service filter

Limits which book nodes are *read* to those whose graph-relative `path` starts with the
`book_scope(root, service)` prefix. The citation index (`cited_paths` / `cited_symbols`)
stays whole-graph: a candidate cited only from a sibling book remains a candidate for this
audit, and a node whose path does not start with the scope is skipped from the read so a
duplicate heading in another service's book is not this audit's limitation. The filter is
read-time, not post-filter; the empty string disables it.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::extract_book` (the `scope` parameter)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/paths.py::book_scope`
- consistency: audit-scope — every prepared packet's claims carry paths inside the `book_scope` prefix when `scope.service` is set
- tests: `workflows/tests/okf_builder/test_audit.py::test_book_to_source_mismatches_queue_only_the_selected_book`

### concept: source-path filter

Limits which source files enter the evidence inventory to those matched by the
`source_path` selector. Directory selectors exclude the ostler cache directories
(`__pycache__`, `.git`, `.venv`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`,
`.nox`, `node_modules`); `.pyc` / `.pyo` files and directory symlinks are not traversed.
Explicit file selectors override the cache exclusions — a path that names a file inside a
cache directory is still read. A selector that matches no source file after exclusions is
named on `EvidenceInventory.limitations` as "Selector {selector} selected no source files
after exclusions."; an empty selector raises `ValueError("empty selector: supply an explicit
file/directory or [] for a book-only review")` from `extract_evidence`, surfacing as
`BehaviorAuditOutcome.status = "invalid"` and an `evidence-preparation` `out_of_scope`
`UnresolvedItem`. A zero-file inventory adds the limitation "No source files selected; this
is not evidence of source coverage."

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::extract_evidence`
- consistency: audit-inventory — explicit file selectors survive cache-directory exclusions
- consistency: audit-inventory — a selector matching zero source files is reported as a `Selector ... selected no source files after exclusions.` limitation rather than raising
- tests: `ostler/tests/test_behavior.py::test_directory_selection_prunes_caches_but_explicit_file_selectors_remain_visible`

### concept: context_paths filter

Pulls extra Python, Go, TypeScript or PHP files into the packet's `support_context` without
adding them as candidates. Directories are unsupported — a `context_paths` entry that is a
directory yields no support context. Languages outside Python, Go, TypeScript and PHP are not
extracted; the file becomes an `out_of_scope` unresolved item rather than blocking the pass.
A `context_paths` file that fails to parse (status != `"parsed"`) causes `preparation` to
raise `ValueError("Support context unavailable: ...")`, which the audit flow's `setup()`
catches and turns into a `BehaviorAuditOutcome.status = "invalid"` gate with one
`out_of_scope` `UnresolvedItem` per failed file. A failing support-context path is the only
filter that aborts the audit on preparation; the rest ship partial reports.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::extract_evidence` (the `context_paths` parameter)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::preparation`
- consistency: audit-packet — a context_paths file contributes no candidates to any packet
- consistency: audit-preparation — a context_paths file that fails to parse produces an `invalid` outcome and zero reviewer turns spent
- tests: `workflows/tests/okf_builder/test_audit.py::test_support_context_reaches_packets_and_invalidates_receipts`
- tests: `workflows/tests/okf_builder/test_audit.py::test_missing_support_context_is_invalid_without_model_spend`

### concept: max_packets filter

Slices `prepared.packets[:scope.max_packets]` before the iteration body reads receipts.
Omitted packets are not assessed — the count is recorded on
`BehaviorAuditOutcome.omitted_packets` and named in the appended limitation "Selection
limits apply to packets; omitted packets are not assessed." `None` disables the filter; `0`
or any non-positive value is rejected by Pydantic (`gt=0` on `AuditScope.max_packets`). A
drive that omits packets is *partial*, not *invalid*; the next drive picks the rest up from
the prepared inventory on disk.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::assess_audit` (`selected = prepared.packets[:scope.max_packets]`)
- consistency: audit-outcome — a drive that drops packets via `max_packets` reports `status = "partial"` (not `"invalid"`) and counts the drops on `omitted_packets`
- detail: [assess_audit entry points](assess-audit-entry-points.md)
- detail: [OKF-builder audit module](okf-builder-audit-module.md)
- tests: `workflows/tests/okf_builder/test_audit.py::test_sampling_and_unsupported_source_are_explicit_partial_reports`

### concept: packet_max_items filter

Splits an oversized packet into chunks of at most `max_items` candidates + claims. The split
loop rejects `max_items < 2` at the top of `build_audit_packets`. A chunk that is still too
large is split again — first candidates in half, then claims — until a chunk fits
`max_chars` or the indivisible remainder (one candidate + one claim) raises.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::build_audit_packets` (the `max_items` parameter, default 80)
- consistency: audit-packet — every packet after splitting carries no more than `packet_max_items` candidates + claims
- tests: `ostler/tests/test_behavior.py::test_packet_budget_counts_indivisible_context_without_truncation`

### concept: packet_max_chars filter

Bounds the serialized JSON size of each packet; packets exceeding it are halved recursively.
`max_chars < 1` raises `ValueError("max_chars must be positive")` at the top of
`build_audit_packets`. An indivisible oversized context — one candidate, one claim, still
over budget — raises `ValueError("oversized packet for {module}: cannot fit
max_chars={max_chars} without truncation")` from the split loop, aborting `preparation`; the
audit flow catches this in `setup()` and reports an `invalid` outcome with `error` set.
`assess_audit`'s repair-batching loop reuses `packet_max_chars` as the largest repair-finding
it will queue: a finding larger than that budget is recorded as a `validation_error`
`UnresolvedItem` named "a repair finding exceeds the context budget; inspect the packet
report", so the gate can still see it but it is not actionable from the worklist.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::build_audit_packets` (the `max_chars` parameter, default 60,000)
- consistency: audit-packet — every packet's serialized JSON size does not exceed `packet_max_chars`
- consistency: audit-preparation — an indivisible oversized packet raises `ValueError`, which `setup()` records as an `invalid` outcome
- tests: `ostler/tests/test_behavior.py::test_packet_budget_counts_indivisible_context_without_truncation`

### concept: tier-1 candidate filter

Keeps only tier-1 candidates — cited by the book or exported by the language's rule
(`exported_symbol`) — in the packet; tier-2 candidates (uncited, unexported symbols) are
counted as `AuditPreparation.deferred_candidates`. A file where every candidate is tier 2 and
no claim cites the file builds no packet at all — the reviewer never sees those symbols
under the default tier. A module-level candidate (`<module>`) has no name to keep private,
so it is always tier 1 even when nothing in the book cites the file. A packet that kept some
tier-1 candidates carries the limitation "{N} tier-2 candidates (private, uncited symbols)
are not in this packet; `ostler audit --tier all` reviews them." `tier="all"` is a different
call (`ostler audit --tier all`), not a scope field — the audit flow always builds at tier 1.
The deferral is the only filter where what is dropped is recoverable by re-running with
`--tier all`; the rest of the filters' drops are bounded choices, not retrievable work.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::candidate_tier`
- code: `ostler/ostler/behavior.py::build_audit_packets` (the `tier` parameter, default `1`)
- consistency: audit-packet — a candidate the book does not cite and the language does not export is never in a tier-1 packet
- consistency: audit-packet — a module-level `<module>` candidate is always tier 1 even without a citation
- tests: `ostler/tests/test_behavior.py::test_tier_one_keeps_cited_and_exported_candidates_and_defers_the_rest`
- tests: `ostler/tests/test_behavior.py::test_a_file_of_only_private_uncited_candidates_costs_no_packet_at_tier_one`

### concept: skip_undocumented filter

Drops a parsed source file with exported symbols and no citing claims from packet building;
the file is listed on `AuditPreparation.undocumented` and on
`BehaviorAuditOutcome.undocumented_files`. Every exported symbol of such a file lands in
`UndocumentedFile.exported_symbols` — including the tier-1 vs tier-2 split inside the file;
the repair tells the operator which symbols to document or to exclude from the scope.
`skip_undocumented=False` builds a packet for every parsed file regardless of citations; the
audit flow does not expose this — it is the default `True` only.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::build_audit_packets` (the `skip_undocumented` parameter, default `True`)
- consistency: audit-outcome — a parsed file with exported symbols and no citing claim is reported on `undocumented_files` and never reaches a reviewer
- tests: `workflows/tests/okf_builder/test_audit.py::test_uncited_exported_file_is_queued_without_a_packet`

### concept: out-of-scope-claims filter

Drops claims whose every citation names a file outside the selected source files but that
exists under the audit's `root`; the count is recorded on
`AuditPreparation.out_of_scope_claims` and named in every packet's limitation. A claim
citing only files outside `source_path` but inside `root` is reported as out-of-scope and
sent to no reviewer. A claim citing only a missing or malformed path stays in scope — its
citation cannot tell "outside selected" from "deleted"; the audit reports it as
`ungrounded`.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::build_audit_packets` (the `root` parameter)
- consistency: audit-preparation — a claim whose every citation resolves outside the selected source scope is counted on `out_of_scope_claims` and absent from every packet
- tests: `ostler/tests/test_behavior.py::test_claims_citing_only_existing_unselected_files_are_out_of_scope_with_a_root`

### concept: empty-selector filter

Reports a `Selector {path} selected no source files after exclusions.` limitation per
directory selector that matches nothing, rather than raising. The audit still runs against
whatever other selectors did match — an empty selector is a recorded caveat, not a blocked
drive. Only directory selectors produce empty-selector limitations; explicit file selectors
are matched literally.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `ostler/ostler/behavior.py::extract_evidence` (`empty_selectors`)
- consistency: audit-inventory — a directory selector that selects no source file yields one `"Selector ... selected no source files after exclusions."` limitation and does not abort the audit
- tests: `ostler/tests/test_behavior.py::test_empty_scope_empty_directories_and_empty_files_are_explicit`

### concept: empty-packet reporting

Validates a packet that has neither candidates nor claims without dispatching it to a
reviewer, and counts it on `BehaviorAuditOutcome.empty_packets`. An empty packet still
claims a digest and is recorded as assessed; the count is informational, not blocking.

- detail: [Filter mechanisms and limitations](#filter-mechanisms-and-limitations)
- code: `workflows/src/workhorse_workflows/okf_builder/audit/flow.py::Audit.start`
- consistency: audit-outcome — a packet with no candidates and no claims is recorded as `assessed` and contributes one to `empty_packets` without spending a reviewer turn
- detail: [assess_audit entry points](assess-audit-entry-points.md)
- tests: `workflows/tests/okf_builder/test_audit.py::test_sampling_and_unsupported_source_are_explicit_partial_reports`

The filters stack: an audit run with `service="acme"`, `source_path="acme"`,
`max_packets=1`, `packet_max_items=80`, `packet_max_chars=60000` reads only `acme`'s book
nodes, only `acme`'s source files, builds at most one packet per drive, splits packets at 80
items or 60k chars, defers tier-2 symbols, drops undocumented files, and reports out-of-scope
claims and empty selectors as caveats — and every one of those drops is reproducible from
the `BehaviorAuditOutcome.limitations` string list.

## Review Contract and Binding

A review contract is a digest of the dispatch contract: the audit prompt file and the result schema. It binds verdicts to the exact conditions under which they were produced, ensuring that a later re-run with different instructions or schema does not reuse stale receipts.

### ReviewContract
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::ReviewContract`
- `version` — schema version (currently 1)
- `prompt_digest` — SHA256 of the audit prompt file at dispatch time
- `schema_digest` — SHA256 of the AuditVerdicts JSON schema at dispatch time
- `digest` (property) — canonical SHA256 of the contract, used to identify related receipts
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_binds_receipts_to_review_contract`
- tests: `workflows/tests/okf_builder/test_audit.py::test_in_flight_contract_change_never_marks_reply_current`

### ReceiptPolicy
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::ReceiptPolicy`

Binds a verdict file to its contract and verdict digest. Persisted alongside `verdicts.json` to detect stale receipts that cannot be reused.

- `contract` — ReviewContract
- `verdicts_digest` — SHA256 of the raw verdict JSON
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_binds_receipts_to_review_contract`
- tests: `workflows/tests/okf_builder/test_audit.py::test_in_flight_contract_change_never_marks_reply_current`

### review_contract(prompt_path, result_schema) → ReviewContract
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::review_contract`

Creates a ReviewContract from the current prompt and schema digests.

### verdict_schema() → str
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::verdict_schema`

Returns the JSON schema of AuditVerdicts as a canonical string (sorted keys, compact separators).

### ReviewContractChanged
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::ReviewContractChanged`

Exception raised when the review contract changes during dispatch or verdict recording. Treated as an operator gate to prevent silently reusing verdicts under changed conditions.

## Audit Prompt Contract

The audit flow renders a single prompt template at every reviewer turn; the template is the
contract the reviewer is bound by until the prompt file or the AuditVerdicts schema changes
(the digest that protects that binding is the `prompt_digest` recorded on the `ReviewContract`).
The contract is **evidence before repair**: the reviewer must read the supplied complete
enclosing source — including side effects and early guards — before judging isolated snippets
or return values, must inspect the same-node book context (signatures and prose) before
declaring a candidate `missing`, and must name an explicit structural reason for the omission.
Insufficient evidence, including absent source, classifies as `unresolved` with no repair; an
observed mismatch is `partial` (with the supported clause), not a claim that documented
behavior is absent. The assessment is packet-only and read-only: the reviewer returns JSON
directly, uses no tools, runs no tests, opens no browser, and edits no files. The verdict
vocabulary on the rendered prompt names the four claim statuses (`supported`, `contradicted`,
`partial`, `unresolved`) and the four candidate statuses (`covered`, `missing`,
`implementation_detail`, `unresolved`); a `covered` candidate carries `book_evidence`
references to the exact document lines that establish the behavior, with signature-only
coverage citing the signature's node and inclusive start_line/end_line.

- code: `workflows/src/workhorse_workflows/okf_builder/audit/prompts/behavior-audit.md`
- tests: `workflows/tests/okf_builder/test_audit_prompt.py::test_rendered_audit_requires_evidence_before_repair`

### BookEvidenceRef
- code: `ostler/ostler/behavior_models.py::BookEvidenceRef`

Documented evidence within this packet, not a new normative obligation. A `BookEvidenceRef`
names exactly one node from `packet.book_context` and an inclusive line range inside that
context; signature-only coverage cites the signature's node plus start_line/end_line.

- `node` — exact node ID in packet.book_context; that context binds the document path
- `start_line` — inclusive first document line within the supplied book context
- `end_line` — inclusive last document line, at or after start_line

### CandidateVerdict.book_evidence
- code: `ostler/ostler/behavior_models.py::CandidateVerdict.book_evidence`

The tuple of `BookEvidenceRef` records a covered candidate supplies to record where in the
book the behavior is documented. Only covered verdicts may carry `book_evidence`; the
validator rejects book evidence on any other status. Distinct, nonblank book spans
establishing the covered source behavior. Confirms documented source coverage, not QA proof.

## Assessment and Preparation

### preparation(scope) → AuditPreparation
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::preparation`

Reads the scoped book (no formatting or source import) and extracts evidence from the source files. Returns an audit preparation object with candidate behaviors and book claims, filtered by service and source scope.

Raises ValueError if source_path is missing or support context files cannot be parsed.
- tests: `workflows/tests/okf_builder/test_audit.py::test_audit_preparation_runs_once_per_drive`

### prepare_audit(logger, scope, run_dir, prompt_path) → AuditPreparation
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::prepare_audit`

The read-once half of the assessment: computes an `AuditPreparation` from source and book, then persists `preparation.json` and one `packet.json` per selected packet under `<run_dir>/behavior-audit/<digest>/`. The audit flow's `setup()` calls it once; the iteration body reads the cached result. Splitting it from `assess_audit` keeps the per-iteration hot loop off the book- and source-reading path — for an N-packet audit the per-packet work is O(1) (receipt scan) instead of O(book + source).
- tests: `workflows/tests/okf_builder/test_audit.py::test_audit_preparation_runs_once_per_drive`
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_rebuilds_source_and_claims_before_reusing_receipts`

### assess_audit(logger, scope, run_dir, prompt_path, prepared=None) → AuditWork
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::assess_audit`
- detail: [assess_audit entry points](assess-audit-entry-points.md)

Main assessment entry point. Scans receipts against the prepared packets, reuses memoised verdicts when the review contract has not changed, and returns a partial or complete outcome with pending packets for review.

When `prepared` is `None` (the default), the call self-contains: it runs `prepare_audit` first and writes the on-disk artifacts the iteration body reads. The audit flow passes a cached `AuditPreparation` from `setup()` so the read-once work is not repeated per packet.

Returns AuditWork with:
- `outcome` — BehaviorAuditOutcome
- `pending` — tuple of AuditPacket that need a verdict
- `result_schema` — string schema for validation
- tests: `workflows/tests/okf_builder/test_audit.py::test_book_to_source_mismatches_queue_only_the_selected_book`
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_rebuilds_source_and_claims_before_reusing_receipts`
- tests: `workflows/tests/okf_builder/test_audit.py::test_sampling_and_unsupported_source_are_explicit_partial_reports`
- tests: `workflows/tests/okf_builder/test_audit.py::test_unsupported_files_become_out_of_scope_items`

## Outcome and Reporting

### BehaviorAuditOutcome
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::BehaviorAuditOutcome`

Summary of an audit run: what was assessed, what failed, what is unresolved, and limitations.

- `schema_version` — 1 or 2 (2 is current, with review contract tracking)
- `review_contract` — ReviewContract or None (None for old checkpoints)
- `policy_digest` — the review contract's own digest, stored alongside so a lookup does not need to reconstruct the contract
- `status` — "assessed" (all packets read), "partial" (some skipped), or "invalid" (preparation failed)
- `report_path` — file path where the outcome JSON is written
- `scope_digest` — SHA256 of the prepared packets, unchanged when evidence/claims are unchanged
- `scope` — the AuditScope this run was assessed under
- `scope_clear` — true when this pass left nothing outstanding (no pending packet, no repair, no unresolved verdict); reset to `false` by `record_audit_budget_stop` and `record_audit_error`
- `total_packets`, `assessed_packets`, `omitted_packets` — packet counts
- `empty_packets` — packets with no candidates or claims (validated without model call)
- `selected_candidates`, `selected_claims` — counts of candidates and claims selected into the prepared packets
- `reports` — the AuditReport for each assessed packet
- `memo_hits`, `memo_partial` — recall optimization metrics
- `unresolved` — list of verdict explanations that could not be classified
- `undocumented_files` — source files exporting symbols that no book claim cites
- `unaudited_packets` — packets with no receipt (from budget stop or parse error)
- `repairs` — AuditRepair objects, grouped by file
- `limitations` — schema and selection caveats
- `error` — the fatal error message when `status` is "invalid"

### AuditRepair
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::AuditRepair`

Documents a gap discovered during assessment that needs author attention.

- `target` — file path or anchor where the repair applies
- `context` — the gap narrative and evidence (chunk of max_chars)

### clear_except_unaudited (property)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::BehaviorAuditOutcome.clear_except_unaudited`

True when the outcome shows no repairs, unresolved verdicts, or omitted packets — only packets awaiting receipt from a future pass. Indicates a partial audit that may ship pending turn budget completion.
- tests: `workflows/tests/okf_builder/test_audit.py::test_clear_except_unaudited_names_only_the_budget_shape`

## Test-file handling

The behavior audit's `undocumented_files` field and the coverage inventory's unit list use
different rules for test files, and the asymmetry is not a defect to fix here — it is two
predicates answering different questions on the same corpus:

- The behavior audit asks **"is this source file documented as behavior?"** — answered by
  joining the source inventory against the book's `code:` citations via `extract_book`
  (`ostler/ostler/behavior.py:201`). `extract_book` builds `cited_paths` solely from
  `node.meta.get("code")` (`ostler/ostler/behavior.py:233`): every path a `code:` bullet
  cites enters the set, and `tests:` citations never do. A test file that no node cites
  via `code:` therefore lands in `undocumented_files`, even when its owning flow node
  cites it via `tests:`. The audit cannot repurpose `tests:` citations without changing
  what the field means — a test citation is the QA author declaring who ran the
  behaviour, not a documented behaviour.
- The coverage inventory asks **"is this source file a coverage unit the book must
  cover?"** — answered by `skipped` (`workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::skipped`)
  on the inventory side, which filters `tests/` directories and test-suffixed / test-prefixed
  filenames before they become units. Tests are cited by `tests:` bullets, not covered as
  first-class source, so they are removed from the unit set at inventory time and never
  reach `undocumented_files` through that path.

The practical effect: a `workflows/tests/**/*.py` file that some flow node cites via
`tests:` only — a common shape for a `flow` whose `code:` cites the production module
and whose `tests:` covers the regression suite — is reported under `undocumented_files`
in the audit's outcome (`BehaviorAuditOutcome.undocumented_files`,
`workflows/src/workhorse_workflows/okf_builder/shared/audit.py:162`) even though the
coverage join correctly excludes the same file via `SKIP_DIRS = {"tests", ...}`
(`workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py:52`). The audit's
behaviour is correct by its own predicate — it is the same shape a production file with
no `code:` citation would have — and the asymmetry is intentional: an author documenting
a test as behavior would do so on a node that owns a `code:` bullet for the test's path,
in which case the file is cited and the audit reports coverage.

- detail: [Source inventory filtering](source-inventory-filter.md) — the `skipped` exclusion rule and the rationale for filtering tests at inventory time
- detail: [Audit result field roles](audit-result-field-roles.md) — the role of `undocumented_files` alongside `findings`, `status`, and `notes`

## Verdict Management

### AuditWork
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::AuditWork`

Result of assess_audit: the outcome, pending packets, and the schema for verdicts.

### packet_label(packet) → str
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::packet_label`

Returns a digest and the source paths a packet covers, used to label receipt directories.

### verdict_memo(scope, contract) → VerdictMemo
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::verdict_memo`

Creates or opens the per-run verdict memo (ostler's IndexStore) for this book and contract. Used to cache and recall verdicts across assessment passes.
- tests: `workflows/tests/okf_builder/test_audit.py::test_memoized_verdicts_cost_no_turn_in_another_run`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_new_claim_reduces_the_packet_to_what_the_memo_lacks`

### write_receipt(packet_dir, report, contract) → None
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::write_receipt`

Atomically writes a verdict receipt to a packet directory:
- `verdicts.json` — the raw verdict model
- `report.json` — the full AuditReport
- `review-contract.json` — ReceiptPolicy binding the verdict to the contract

Unlinks the policy file first to ensure an interrupted write never blesses a partial receipt.
- tests: `workflows/tests/okf_builder/test_audit.py::test_memoized_verdicts_cost_no_turn_in_another_run`
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_binds_receipts_to_review_contract`
- tests: `workflows/tests/okf_builder/test_audit.py::test_in_flight_contract_change_never_marks_reply_current`

### read_receipt(packet_dir, packet, contract) → AuditReport | None
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::read_receipt`

Reads and validates a receipt in packet_dir. Returns the AuditReport if the policy contract matches and the verdict digest is valid; None otherwise. Allows detection of stale receipts whose contract has changed.
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_binds_receipts_to_review_contract`
- tests: `workflows/tests/okf_builder/test_audit.py::test_in_flight_contract_change_never_marks_reply_current`

### recall_report(artifacts, packet, memo, contract) → AuditReport | AuditPacket
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::recall_report`

Queries the memo for a complete or partial verdict against the packet. If a complete hit, writes a receipt and returns the report. If a partial hit, returns a reduced packet and leaves the full one in `parent.json`. If no hit or validation fails, returns the original packet.
- tests: `workflows/tests/okf_builder/test_audit.py::test_memoized_verdicts_cost_no_turn_in_another_run`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_new_claim_reduces_the_packet_to_what_the_memo_lacks`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_dropped_verdict_is_re_asked_on_its_own_not_by_re_asking_the_packet`

## Recording and Pass Tracking

### record_audit_verdicts(logger, packet, verdicts, run_dir, contract, prompt_path, scope=None) → AuditReport
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::record_audit_verdicts`

Persists a typed verdict before structural validation. Writes the raw receipt, validates against packet (or parent if reduced), and saves the result. Checks that the review contract has not changed during dispatch; raises ReviewContractChanged if it has.
- tests: `workflows/tests/okf_builder/test_audit.py::test_resume_binds_receipts_to_review_contract`
- tests: `workflows/tests/okf_builder/test_audit.py::test_in_flight_contract_change_never_marks_reply_current`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_repair_answered_for_exactly_the_owed_items_completes_the_pass`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_repair_naming_a_foreign_id_is_rejected_not_remembered`
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_dropped_verdict_is_re_asked_on_its_own_not_by_re_asking_the_packet`
- tests: `workflows/tests/okf_builder/test_audit.py::test_validation_error_resolution_path_is_retry_then_ship`

### audit_pass(logger, run_dir, advance) → int
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::audit_pass`

Tracks how many audit passes this run has opened (persisted in `behavior-audit/passes`). Used to coordinate multiple assessment rounds in a single workflow run.
- tests: `workflows/tests/okf_builder/test_audit.py::test_outcome_records_pass_and_rework_counts`

### record_audit_budget_stop(logger, outcome, turns, budget) → BehaviorAuditOutcome
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::record_audit_budget_stop`

Records a turn budget exhaustion: updates the outcome status to "partial", clears `scope_clear`, and adds a limitation explaining which packets remain unaudited.
- tests: `workflows/tests/okf_builder/test_audit.py::test_turn_budget_ends_the_pass_with_the_unaudited_packets_listed`

### record_audit_error(logger, outcome, packet_digest, error) → BehaviorAuditOutcome
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::record_audit_error`

Records a fatal error during verdict validation: marks outcome as "invalid", clears `scope_clear`, records the error on the outcome's `error` field, writes the error message to the packet directory, and returns the failed outcome.
- tests: `workflows/tests/okf_builder/test_audit.py::test_a_spent_reviewer_turn_is_gated_not_fatal`
- tests: `workflows/tests/okf_builder/test_audit.py::test_invalid_verdicts_retry_twice_then_checkpoint_await`

