---
type: concept
slug: auditing-a-books-claims-against-source
title: Auditing a book's claims against source
---
# Auditing a book's claims against source

`ostler doctor`'s behavior audit answers one question a citation check cannot: not just "does
this `code:` bullet point at a file that exists", but "does the file still do what the book says
it does". `behavior.py`'s `build_audit_packets` is the entry point: for every cited file it pairs
the book's claims about it (`extract_claims`, `extract_book`) with evidence pulled straight out
of the file's own source (`extract_evidence`), windowed to the lines actually cited
(`_windowed_book_context`, `_outermost_contexts`) rather than the whole file, and bundles the pair
into an `AuditPacket`. `exported_symbol` and `cited_symbol` decide whether a symbol a citation
names is the kind of thing a citation can legally point at; `undocumented_file` flags a file with
evidence but no citation at all; `candidate_tier` ranks how confidently an unclaimed piece of
evidence might belong to an existing claim. `_check_claim_verdict`, `_check_candidate_verdict` and
`_check_candidate_links` turn one packet into a `ClaimVerdict`/`CandidateVerdict`, and
`validate_verdicts` is the final pass that turns a set of verdicts into the findings `doctor.py`
reports.

Evidence extraction is language-specific, dispatched by file extension rather than shared across
languages. `behavior_python.py`'s `PythonEvidence` walks a file with Python's own `ast` module.
`behavior_tree.py`'s `TreeEvidence` and `behavior_go.py`'s `GoEvidence` instead walk a
tree-sitter parse (via `syntax.py`), `behavior_go.py` specifically handling Go's receiver methods
and embedded fields that a language-generic walk would miss; `LanguageTable` in `behavior_tree.py`
maps a file extension to the tree-sitter node kinds that count as a declaration in that language.
`behavior_cli.py`'s `run` is the thin CLI entry point `ostler doctor --behavior` calls into.
`behavior_models.py` is the shared data model every one of these modules builds and
`behavior.py` consumes: `BehaviorEvidence`/`EvidenceFile`/`FileExcerpt` hold what a source file
contains, `SourceContext`/`SourceExcerpt`/`BookContext`/`BookClaim`/`BookClaims` hold what the
book says about it, `AuditPacket`/`AuditPreparation` pair the two before judgment, and
`ClaimVerdict`/`CandidateVerdict`/`BookEvidenceRef`/`AuditVerdicts`/`AuditReport` hold the
judgment itself.

`behavior_memo.py` is why a repeated audit does not re-walk every source file on every run:
`claim_digest`/`candidate_digest` and their context-aware counterparts
(`claim_context_digest`/`candidate_context_digest`) hash a claim or a piece of evidence together
with enough of its surrounding context that a verdict can be trusted unchanged only when both
sides are unchanged; `VerdictMemo` and `MemoRecall` are the persisted store and lookup,
`salvage_verdicts`/`reduce_packet`/`merge_verdicts` carry a prior run's still-valid verdicts
forward into a new one so the audit only re-judges what actually moved.

`checks.py` is unrelated to the audit above: it is the parser for a `verify:` bullet's check
expression, the vocabulary a string like `exit_status(code=0)` is written against everywhere in
the book. `CheckSpec` and `CheckParam` declare one check's name and typed parameters; `parse_check`
parses a raw string into a `CheckCall` or a `Refusal` (via `parse_expression`'s `Call`/`Malformed`
split and `_unknown_check`'s message for a name outside `_vocabulary`); `bind` resolves a parsed
call's arguments against its `CheckSpec` with the right type (`_typed`, `_value`); `describe`
renders a `CheckCall` back to its canonical string form; `is_check_expression` and
`relocatable_to_tests` decide whether a string is a check at all and whether it is the kind of
check `carve.py`-style page splits may relocate. `shared_checks.py`'s `check_shared_checks` flags
two nodes declaring the identically-worded check (`_repeated`) when one should instead reference
or extend the other. `stack_checks.py`'s `check_stack` validates an `ops/stack.yml` claim against
the stack file itself. `outcome_rules.py`'s `check_outcomes` validates that a flow node's declared
`outcome:`/`move:` bullets are internally consistent — the checks it runs
(`_check_outcomes`, `_check_moves`) read a page's claimed checks (`_claims`, `_shown`,
`_check_steps`) and the moves those checks imply (`_outcomes`, `_method_of`) rather than any
source file, so it feeds `doctor.py` from the book's own declarations, not from an audit of code.

`drivers.py` declares the `driver:` vocabulary itself — `DRIVERS` is the fixed tuple
(`"web"`, `"mobile"`, `"http"`, `"cli"`, `"artifact"`, `"iac"`, `"none"`) every `driver:` bullet
and compile backend is checked against.

- code: ostler/ostler/behavior.py::build_audit_packets@9b054226c6dd
- code: ostler/ostler/behavior.py::extract_evidence@9b054226c6dd
- code: ostler/ostler/behavior.py::extract_claims@9b054226c6dd
- code: ostler/ostler/behavior.py::exported_symbol@9b054226c6dd
- code: ostler/ostler/behavior.py::cited_symbol@9b054226c6dd
- code: ostler/ostler/behavior.py::undocumented_file@9b054226c6dd
- code: ostler/ostler/behavior.py::validate_verdicts@9b054226c6dd
- code: ostler/ostler/behavior_cli.py::run@324557ae52a9
- code: ostler/ostler/behavior_go.py::GoEvidence@f1f9630c97e2
- code: ostler/ostler/behavior_python.py::PythonEvidence@56f54c99d10e
- code: ostler/ostler/behavior_tree.py::TreeEvidence@c32ff5de858b
- code: ostler/ostler/behavior_tree.py::LanguageTable@c32ff5de858b
- code: ostler/ostler/behavior_models.py::AuditPacket@23f8eb86babc
- code: ostler/ostler/behavior_models.py::ClaimVerdict@23f8eb86babc
- code: ostler/ostler/behavior_models.py::CandidateVerdict@23f8eb86babc
- code: ostler/ostler/behavior_models.py::BookClaim@23f8eb86babc
- code: ostler/ostler/behavior_models.py::AuditReport@23f8eb86babc
- code: ostler/ostler/behavior_memo.py::VerdictMemo@e8aa0356d04e
- code: ostler/ostler/behavior_memo.py::claim_digest@e8aa0356d04e
- code: ostler/ostler/behavior_memo.py::salvage_verdicts@e8aa0356d04e
- code: ostler/ostler/behavior_memo.py::merge_verdicts@e8aa0356d04e
- code: ostler/ostler/checks.py::CheckSpec@b3b97ff94fb4
- code: ostler/ostler/checks.py::CheckParam@b3b97ff94fb4
- code: ostler/ostler/checks.py::parse_check@b3b97ff94fb4
- code: ostler/ostler/checks.py::bind@b3b97ff94fb4
- code: ostler/ostler/checks.py::describe@b3b97ff94fb4
- code: ostler/ostler/checks.py::Refusal@b3b97ff94fb4
- code: ostler/ostler/checks.py::is_check_expression@b3b97ff94fb4
- code: ostler/ostler/shared_checks.py::check_shared_checks@c96e41ffd13b
- code: ostler/ostler/stack_checks.py::check_stack@2f4549d63d1b
- code: ostler/ostler/outcome_rules.py::check_outcomes@408c771787b5
- code: ostler/ostler/drivers.py::DRIVERS@cc0927c9bd8e
- detail: [ostler](../cli.md)

## Contract

- a verdict is memoized by content, not by file path: `behavior_memo.py` salvages a prior verdict
  only when both the claim's and the evidence's context digest match the prior run exactly; any
  change to either side forces a fresh judgment.
- evidence extraction never edits the book: every `behavior_*.py` module reads a source file and
  reads the book's own claims; only `behavior.py`'s verdicts, consumed by `doctor.py`, ever
  produce a finding.
- a check expression that fails to parse is a `Refusal`, not an exception: `parse_check` always
  returns one or the other, so a malformed `verify:` bullet is reported as a finding by whatever
  called `parse_check`, never as a crash.
- `outcome_rules.py` checks the book against itself: it validates a flow node's own `outcome:`/
  `move:` bullets for internal consistency and never reads product source, unlike every other
  module in this group.
