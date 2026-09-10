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

## Review Contract and Binding

A review contract is a digest of the dispatch contract: the audit prompt file and the result schema. It binds verdicts to the exact conditions under which they were produced, ensuring that a later re-run with different instructions or schema does not reuse stale receipts.

### ReviewContract
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::ReviewContract`
- `version` — schema version (currently 1)
- `prompt_digest` — SHA256 of the audit prompt file at dispatch time
- `schema_digest` — SHA256 of the AuditVerdicts JSON schema at dispatch time
- `digest` (property) — canonical SHA256 of the contract, used to identify related receipts

### ReceiptPolicy
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::ReceiptPolicy`

Binds a verdict file to its contract and verdict digest. Persisted alongside `verdicts.json` to detect stale receipts that cannot be reused.

- `contract` — ReviewContract
- `verdicts_digest` — SHA256 of the raw verdict JSON

### review_contract(prompt_path, result_schema) → ReviewContract
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::review_contract`

Creates a ReviewContract from the current prompt and schema digests.

### verdict_schema() → str
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::verdict_schema`

Returns the JSON schema of AuditVerdicts as a canonical string (sorted keys, compact separators).

### ReviewContractChanged
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::ReviewContractChanged`

Exception raised when the review contract changes during dispatch or verdict recording. Treated as an operator gate to prevent silently reusing verdicts under changed conditions.

## Assessment and Preparation

### preparation(scope) → AuditPreparation
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::preparation`

Reads the scoped book (no formatting or source import) and extracts evidence from the source files. Returns an audit preparation object with candidate behaviors and book claims, filtered by service and source scope.

Raises ValueError if source_path is missing or support context files cannot be parsed.

### prepare_audit(logger, scope, run_dir, prompt_path) → AuditPreparation
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::prepare_audit`

The read-once half of the assessment: computes an `AuditPreparation` from source and book, then persists `preparation.json` and one `packet.json` per selected packet under `<run_dir>/behavior-audit/<digest>/`. The audit flow's `setup()` calls it once; the iteration body reads the cached result. Splitting it from `assess_audit` keeps the per-iteration hot loop off the book- and source-reading path — for an N-packet audit the per-packet work is O(1) (receipt scan) instead of O(book + source).

### assess_audit(logger, scope, run_dir, prompt_path, prepared=None) → AuditWork
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::assess_audit`
- detail: [assess_audit entry points](assess-audit-entry-points.md)

Main assessment entry point. Scans receipts against the prepared packets, reuses memoised verdicts when the review contract has not changed, and returns a partial or complete outcome with pending packets for review.

When `prepared` is `None` (the default), the call self-contains: it runs `prepare_audit` first and writes the on-disk artifacts the iteration body reads. The audit flow passes a cached `AuditPreparation` from `setup()` so the read-once work is not repeated per packet.

Returns AuditWork with:
- `outcome` — BehaviorAuditOutcome
- `pending` — tuple of AuditPacket that need a verdict
- `result_schema` — string schema for validation

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

### write_receipt(packet_dir, report, contract) → None
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::write_receipt`

Atomically writes a verdict receipt to a packet directory:
- `verdicts.json` — the raw verdict model
- `report.json` — the full AuditReport
- `review-contract.json` — ReceiptPolicy binding the verdict to the contract

Unlinks the policy file first to ensure an interrupted write never blesses a partial receipt.

### read_receipt(packet_dir, packet, contract) → AuditReport | None
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::read_receipt`

Reads and validates a receipt in packet_dir. Returns the AuditReport if the policy contract matches and the verdict digest is valid; None otherwise. Allows detection of stale receipts whose contract has changed.

### recall_report(artifacts, packet, memo, contract) → AuditReport | AuditPacket
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::recall_report`

Queries the memo for a complete or partial verdict against the packet. If a complete hit, writes a receipt and returns the report. If a partial hit, returns a reduced packet and leaves the full one in `parent.json`. If no hit or validation fails, returns the original packet.

## Recording and Pass Tracking

### record_audit_verdicts(logger, packet, verdicts, run_dir, contract, prompt_path, scope=None) → AuditReport
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::record_audit_verdicts`

Persists a typed verdict before structural validation. Writes the raw receipt, validates against packet (or parent if reduced), and saves the result. Checks that the review contract has not changed during dispatch; raises ReviewContractChanged if it has.

### audit_pass(logger, run_dir, advance) → int
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::audit_pass`

Tracks how many audit passes this run has opened (persisted in `behavior-audit/passes`). Used to coordinate multiple assessment rounds in a single workflow run.

### record_audit_budget_stop(logger, outcome, turns, budget) → BehaviorAuditOutcome
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::record_audit_budget_stop`

Records a turn budget exhaustion: updates the outcome status to "partial", clears `scope_clear`, and adds a limitation explaining which packets remain unaudited.

### record_audit_error(logger, outcome, packet_digest, error) → BehaviorAuditOutcome
- code: `workflows/src/workhorse_workflows/okf_builder/shared/audit.py::record_audit_error`

Records a fatal error during verdict validation: marks outcome as "invalid", clears `scope_clear`, records the error on the outcome's `error` field, writes the error message to the packet directory, and returns the failed outcome.

