---
type: concept
slug: decision-records
title: Decision records
---
# Decision records

A decision record is an architecture decision proposed from a cluster of
[debt register](the-debt-register.md) records that share one cause. It lives under the docs home,
as `docs/adrs/<slug>/adr.md` (see [the artifacts layout](artifacts-layout.md)), and names the records it rests on as its evidence. Each of those
records names the decision back in its `decision` field. The two links have to agree, and
`ostler doctor` reports either side that points at nothing or at the wrong partner. The
review-debt workflow proposes decisions through `Ostler.propose_decision`. No ostler command moves
a decision past `proposed`: a person edits the file to accept, reject or supersede it.

- code: ostler/ostler/adr.py::Decision@f14c55fafbc7
- code: ostler/ostler/adr.py::propose@f14c55fafbc7
- code: ostler/ostler/adr.py::decisions@f14c55fafbc7
- code: ostler/ostler/api.py::Ostler.propose_decision@defd95727723
- code: ostler/ostler/doctor.py::_check_decisions@b6bae9bf1b96
- code: ostler/ostler/path.py::adr_root_in@6a1acd1702fd
- tests: ostler/tests/test_adr.py::test_three_records_yield_one_proposed_decision_with_repos_and_evidence
- tests: ostler/tests/test_adr.py::test_each_record_carries_the_new_id_and_nothing_else_changed
- tests: ostler/tests/test_adr.py::test_in_the_artifacts_repo_only_the_adr_is_committed
- tests: ostler/tests/test_adr.py::test_outside_the_artifacts_repo_nothing_is_committed
- tests: ostler/tests/test_adr.py::test_a_taken_slug_is_refused_and_the_first_decision_stays
- tests: ostler/tests/test_adr.py::test_a_failed_commit_restores_every_file_and_removes_the_adr
- tests: ostler/tests/test_adr_doctor.py::test_an_intact_decision_yields_no_finding
- detail: [The artifacts layout](artifacts-layout.md)
- detail: [The debt register](the-debt-register.md)
- detail: [ostler doctor's register links check](../doctor-checks.md#ostler-doctor-register-links)

## The file

A decision file is frontmatter, then three sections in this order: `## Context`, `## Decision` and
`## Consequences`. A section with no text keeps its heading. Ostler reads every `adr.md` one folder below
`docs/adrs/` and sorts the decisions by id. A file that does not parse is left out of the read.

## Fields

### field: id
- type: string
- required: yes
- the decision's slug, which is also its folder name. The caller chooses it, and it follows the
  decision slug rule: lowercase kebab, within the length cap.

### field: title
- type: string
- required: yes
- the decision in one non-empty line.

### field: status
- type: one of proposed, accepted, rejected, superseded
- default: proposed

### field: repos
- type: list of strings
- default: empty
- the repos of the evidence records, sorted and without repeats.

### field: evidence
- type: list of strings
- default: empty
- the ids of the records the decision rests on, in the order they were given.

## Proposing a decision

`propose` takes a slug, a title, the three section texts and the evidence ids.

1. It drops repeated evidence ids and keeps the first of each.
2. It refuses an empty evidence list with `a decision needs evidence: name at least one record`.
3. It refuses a bad slug with the slug rule's reason, and a slug whose folder exists as
   `decision '<slug>' already exists at <path>: read it, or pick a different slug`.
4. It resolves each id, a short handle included, to a record on the shelf. It refuses an id with
   no record as `no record '<id>' to cite as evidence`, a record that does not parse as
   `record '<id>' cannot be read: <cause>`, and a record that already names a decision as
   `record '<id>' is already bound to decision '<decision>'`.
5. It refuses a decision that fails validation, such as an empty title, as
   `invalid decision: <field>: <cause>`.
6. It writes `docs/adrs/<slug>/adr.md` and sets `decision: <slug>` on each evidence record,
   changing nothing else in them. The records sit on the untracked shelf and are never committed.
   When the docs home is the artifacts repo, it commits the decision file alone as
   `docs: propose <slug> from <n> records`. Under any other docs home it commits nothing.
7. A failed commit restores each record's old text and deletes the decision folder.

Every refusal writes nothing. A success reports `proposed decision '<id>' from <n> records`.

## What the doctor checks

`ostler doctor` holds both directions of the link, each finding an error.

- `decision-evidence-unresolved`: a decision cites an evidence id that no record folder on the
  shelf holds. A record folder whose `record.md` does not parse still holds its id here.
- `decision-back-link-missing`: a decision cites a record whose `decision` field is empty or names
  another decision. The finding points at the decision file.
- `decision-back-link-missing`: a record names a decision that has no file. The finding names the
  record id and carries no path.

## Contract

- one cluster, one decision: a record is evidence for at most one decision.
- a failed commit leaves the decision and its records as they were.
- the decision file is committed alone, and only in the artifacts repo; the records are not tracked.
