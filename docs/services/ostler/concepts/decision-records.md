---
type: concept
slug: decision-records
title: Decision records
---
# Decision records

A decision record is an architecture decision proposed from a cluster of
[debt register](the-debt-register.md) records that share one cause. It lives in the artifacts repo
beside the shelf, as `adr/<id>.md`, and names the records it rests on as its evidence. Each of those
records names the decision back in its `decision` field. The two links have to agree, and
`ostler doctor` reports either side that points at nothing or at the wrong partner. The
review-debt workflow proposes decisions through `Ostler.propose_decision`. No ostler command moves
a decision past `proposed`: a person edits the file to accept, reject or supersede it.

- code: ostler/ostler/adr.py::Decision@0616ec2d019d
- code: ostler/ostler/adr.py::propose@0616ec2d019d
- code: ostler/ostler/adr.py::decisions@0616ec2d019d
- code: ostler/ostler/api.py::Ostler.propose_decision@bca229b30be1
- code: ostler/ostler/doctor.py::_check_decisions@52668a3449b3
- code: ostler/ostler/path.py::adr_root@1bcbaa1e640a
- tests: ostler/tests/test_adr.py::test_three_records_yield_one_proposed_decision_with_repos_and_evidence
- tests: ostler/tests/test_adr.py::test_each_record_carries_the_new_id_and_nothing_else_changed
- tests: ostler/tests/test_adr.py::test_one_artifacts_commit_holds_the_adr_and_every_record
- tests: ostler/tests/test_adr.py::test_a_failed_commit_restores_every_file_and_removes_the_adr
- tests: ostler/tests/test_adr_doctor.py::test_an_intact_decision_yields_no_finding
- detail: [The debt register](the-debt-register.md)
- detail: [ostler doctor's register links check](../doctor-checks.md#ostler-doctor-register-links)

## The file

A decision file is frontmatter, then three sections in this order: `## Context`, `## Decision` and
`## Consequences`. A section with no text keeps its heading. Ostler reads every `*.md` directly in
`adr/` and sorts the decisions by id. A file that does not parse is left out of the read.

## Fields

### field: id
- type: string
- required: yes
- the file's name less `.md`, one path-safe segment. A proposed decision gets a minted
  `<PREFIX>-<ULID>` from the workspace allocator, so a decision id never collides with a story,
  epic, milestone or record id.

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

`propose` takes a title, the three section texts and the evidence ids.

1. It drops repeated evidence ids and keeps the first of each.
2. It refuses an empty evidence list with `a decision needs evidence: name at least one record`.
3. It resolves each id, a short handle included, to a record on the shelf. It refuses an id with
   no record as `no record '<id>' to cite as evidence`, a record that does not parse as
   `record '<id>' cannot be read: <cause>`, and a record that already names a decision as
   `record '<id>' is already bound to decision '<decision>'`.
4. It mints the id and refuses a decision that fails validation, such as an empty title, as
   `invalid decision: <field>: <cause>`.
5. It writes `adr/<id>.md`, sets `decision: <id>` on each evidence record and changes nothing
   else in them, then commits the decision and every record as one artifacts commit,
   `chore: propose <id> from <n> records`.
6. A failed commit restores each record's old text, deletes the decision file, and removes
   `adr/` when this proposal created it.

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
- a decision and its records change in one commit, or none of them change.
- the decision files and the shelf live in the same artifacts repo, never in a code repo.
