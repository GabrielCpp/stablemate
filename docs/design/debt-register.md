# The debt register

Disclosure: the brainstorm that led here read the existing solution before this skill
loaded: the coder's backlog module, ostler's backlog, path and ids modules, the core config
for the artifacts dir, and the milestone skill. Every design decision that came from that
reading is a claim in section 1b. Each part and concept below passed the test "would I have
named this without having seen the solution".

## 1. Problem

A maintainer runs agent workflows over a workspace of adjacent repositories. Each coder turn
leaves behind technical improvements the story did not need: a refactor, a wider surface, a
check nobody could run. Today each lands as one line in a bullet list, and the list is per
repository. When the maintainer sits down to prioritise, a line gives too little to decide
on. When an agent is asked what the debt says about the architecture, it opens a few lines,
reasons from those, and the answer carries the bias of the sample.

Done looks like this to the maintainer:

- Every deferred improvement is a folder with a record: what, why, where in the code, and
  room for a target design when someone grows it.
- One place holds the improvements of every repository in the workspace, and a reader can
  list them all in one page.
- A trend report over the register names every item it was given, or it is rejected. The
  number is the register's own count, whatever it is that day.
- A cluster of items that share a cause becomes a proposed architecture decision record,
  with the items as its evidence, and each item points back at the decision.
- Prioritising one item hands it to the lane that works it and closes its record.

Out of scope:

- User-facing proposals. Those are milestones and keep their own format.
- The defects QA files for the fix lane to drain. That path stays as it is.
- Screen mockups for technical items. A record may carry a diagram or a sketch, and nothing
  checks for one.
- Clustering at filing time. Trends are found in a review that reads the whole register.
- A second system of record such as a tracker's issues.
- The loss accepted on purpose: an architecture decision that spans repositories has no
  copy inside any one repository. A developer reading one repository alone does not see it.
- Backward compatibility with the bullet-list backlog. The three repositories migrate once,
  the old file is deleted, and no reader or writer of the `- [id] text` grammar survives
  except the one-shot Import.

## 1b. Claims

From the brainstorm and the reading disclosed above.

1. "Each item is a folder with `story.md`, optional mockup and a target design." (the
   request)
2. "The register lives in the artifacts dir under `backlog/<repo>/<service>/<id>/`." (the
   request)
3. "Items carry `pattern`, `area`, `symbols`, `filed_by`, `source_story` frontmatter." (the
   brainstorm)
4. "Filing time does dedup only, with the existing same-cause machinery." (the brainstorm)
5. "A periodic step-back renders every record to one line and reads the whole table." (the
   brainstorm)
6. "A gate rejects a trend report unless every id appears." (the brainstorm, after the
   surveyor's partition gate)
7. "Clusters past a threshold draft an ADR under the artifacts dir with a `repos` field."
   (the brainstorm)
8. "The producers reach the register through ostler's `backlog` doc root, extended to take
   the repo key from the id prefix." (the brainstorm)
9. "The artifacts dir is one git repo that ignores `specs/` and tracks the register." (the
   brainstorm, as an open check)

## 2. Parts and concepts

### Level 1: parts

**Intake.** Receiving one proposed improvement from whoever found it and recording it once.
Owns: the shape a proposal must have to be accepted, and the rule that says a proposal is
already registered. Never knows: where records are stored, or what a review does with them.
Hands a record to the Register.

**Register.** Keeping every record of every repository in the workspace, and answering
"show me all of them" and "show me this one". Owns: the record store and its keys, and the
one-page listing of the whole. Never knows: who filed a record or why a review wants it.
Hands records and the listing to Review and Promotion.

**Review.** Reading the whole register, grouping items that share a cause, and reporting
the trends with every item accounted for. Owns: the clusters and the report, and the proof
that the report covers the register. Never knows: how records are stored, or what a
decision record looks like. Hands clusters to Decision.

**Decision.** Turning a cluster into a proposed architecture decision and binding the items
to it. Owns: the decision document and the links in both directions. Never knows: how
clusters were found. Hands back-links to the Register.

**Promotion.** Taking one item into work and closing its record. Owns: the choice of lane,
the handoff, and the closed state of a record. Never knows: how the lane does its work.
Hands a work item to a lane and a closed record to the Register.

Flow. A producer proposes an improvement. Intake checks it against the Register and stores a
record. At its own cadence, Review takes the Register's listing, reads every record, groups
them, and writes an accounted report. Decision reads clusters above a size and writes a
proposed record, then marks each member item. At any time, a person or an agent picks an
item through Promotion, which hands it to a lane and closes the record with its reason.

Test of the split: a paragraph with no technical words reads "someone files an idea, it
lands on one shelf for the whole workspace, a reviewer reads the shelf end to end and names
the patterns, a pattern big enough gets a written decision, and anyone can pick an idea off
the shelf to do it". A tracker with labels or a folder of markdown both fit it. No part is
named after a stage of the current implementation.

### Level 2: concepts

Shared value type, consulted by Intake, Register, Review and Promotion: the **Record**. It
is one proposal as stored: its id, its repository, its area, the pattern of fix it calls
for, the code it names, who filed it, which story it fell out of, its one-line summary, its
status, its decision link, and its free prose. It belongs to the Register, which owns its
shape.

**Intake**

| Concept | Owns | Never knows |
|---|---|---|
| Proposal | What a producer says: a title a person can act on, the reason the slice worked without it, and the code it touches | Record ids, storage |
| Producer | One origin of proposals and how to read it: a coder turn's follow-ups, QA's leftovers, QA's deferred book checks, a person at the command line, a code survey, a parity survey | Other producers, the Register |
| Same-cause rule | Whether a proposal restates a registered open item | The store layout; it is given the open items |
| Import | Turning an existing bullet list into records once, minting ids for lines that have none; the only reader of the old grammar, and deleted with its last use | Live producers |

**Register**

| Concept | Owns | Never knows |
|---|---|---|
| Record | The stored shape of one proposal, as above | Why anyone reads it |
| Shelf | Where the register of a workspace lives, apart from the session-owned folders beside it, and the key of each record inside it: repository, then area, then id | The record's prose |
| Listing | One line per record, every record, in a fixed field order, for a reader who must see the whole | Clusters, decisions |
| Locator | Resolving an id or a short handle to one record's folder | Record contents |

**Review**

| Concept | Concept owns | Never knows |
|---|---|---|
| Complete read | The set of ids the review was given, taken from the Listing | How records are stored |
| Cluster | A named group of items that share a cause, with the shared cause in one line | The decision format |
| Trend report | The clusters, the singletons, and the cause of each, written for the maintainer | Storage |
| Accounting | Whether every id of the Complete read appears in the Trend report exactly once | What the clusters mean |

**Decision**

| Concept | Owns | Never knows |
|---|---|---|
| Decision record | Context, decision, consequences, the repositories it binds, and the items that are its evidence | How clusters were found |
| Threshold | The cluster size at which a decision is proposed | Record storage |
| Back-link | The decision id written onto each evidence item | The decision's prose |

**Promotion**

| Concept | Owns | Never knows |
|---|---|---|
| Pick | One item chosen for work, by a person or an agent | The lane's internals |
| Lane | What a lane needs to start on an item: the item as a one-criterion work unit, or as a story under an epic | The register |
| Closure | A record's end: done, folded into a decision, or dropped, with the reason | Who picked it |

No part has more than seven concepts.

## 3. Invariants

1. **One record per cause.** An open record's cause appears once in the register. Owner:
   the Same-cause rule, which refuses the duplicate at Intake. Upheld by Import, which runs
   the same rule over an old list.
2. **Every record has a repository and an area.** Owner: the Record, which refuses to be
   written without them. Upheld by each Producer, which supplies them from the run it sits
   in.
3. **The listing is the register.** Every record appears once in the Listing, and no line
   names a record that is gone. Owner: the Listing, which is derived from the Shelf on
   every read and never stored.
4. **A trend report covers its read.** The set of ids in the report equals the set of ids
   in the Complete read, each once. Owner: Accounting, which rejects the report. Upheld by
   the Trend report's writer.
5. **A decision names its evidence and its evidence names it.** Owner: the Decision record,
   which refuses to be written without evidence ids and writes the Back-link in the same
   step.
6. **A closed record stays readable.** Closure changes status and reason and deletes
   nothing, so a later review can see what was done and what was dropped. Owner: Closure.
7. **The register leaves the code repositories.** No record is written inside a repository
   the register describes. Owner: the Shelf, which resolves only into the workspace's
   artifacts place.
8. **Ids are workspace-wide.** A record id collides with no story, seed or milestone id in
   the workspace. Owner: the Locator, which draws ids from the one id space and refuses a
   taken one.

## 4. Forces and patterns

Forces:

- Producers vary and will grow: a coder turn, QA's deferred checks, a person, a survey.
  Each has its own way of saying what it found.
- The store's place varies by how a run is launched: one repository alone, or a workspace
  of several. The producers must not care.
- The register grows without bound over months. Reading it must stay one page, and a review
  must stay complete.
- Review cadence is independent of filing cadence. Filing happens inside a story turn with
  no human present and no time for architecture judgement.
- A trend must be falsifiable. The failure to fear is a plausible report built on a sample.
- Lanes vary: a one-criterion fix unit today, a story under an epic tomorrow.
- A test must swap the store for a temporary folder and the review's reader for a fake.
- Record prose grows per item. The one-line summary must stay stable while the folder
  fills.

Between parts: **one value handed along**. The Record passes from Intake to Register to
Review to Decision and back. Parts touch the register through the Shelf and the Locator
only. Force: the store's place varies, and a test swaps it.

Inside the parts:

- **Producer** is a role with six variants: the coder's follow-ups, QA's leftovers, QA's
  deferred checks, a person's command, the code survey and the parity survey. Each variant owns one way of reading its origin into a Proposal. The
  choice of variant belongs to the run or the command that calls Intake. Force: producers
  vary. The existing coder path becomes one variant, not the base the others extend.
- **Same-cause rule** is a plain function over the open items and one proposal. Force:
  none beyond the invariant, so no pattern. The judgement inside it, word match then a
  closed question to a model, is one variant today and needs no role until a second one
  exists.
- **Import** is a plain function run once. No force varies, so no pattern.
- **Record** is a frozen value with a flat set of fields and a prose body. Force: the
  Listing needs stable fields while the prose grows, so the fields are frontmatter and the
  prose is the body.
- **Shelf** is a role with two variants: the workspace's artifacts place keyed by
  repository, and a temporary folder for tests. The choice sits with the process that
  resolves the run's configuration. Force: the place varies, and a test swaps it.
- **Listing** is a plain rendering, derived on every read. Force: the register grows, so
  the one page is computed, never kept.
- **Locator** is a plain function over the Shelf. No variation.
- **Complete read** is a value: the id set the review started from. **Accounting** is a
  plain function comparing two id sets. Force: falsifiability. The gate is deterministic so
  no model can argue with it.
- **Cluster** and **Trend report** are values written by a model turn that is handed the
  Listing and every record. Force: the register grows, so the reader gets compression first
  and the folders second.
- **Decision record** is a value with a fixed section order. **Threshold** is one setting
  of the review. Force: none varies today beyond the number, so a setting, not a role.
- **Lane** is a role with two variants: the one-criterion fix unit, and a story under an
  epic. The choice sits with the Pick. Force: lanes vary. The fix unit that exists becomes
  one variant.
- **Closure** is a plain function that rewrites status and reason.

Claims, re-derived or rejected:

1. Folder per item: re-derived from the force "prose grows per item while the line stays
   stable". The folder is the Record's home; `story.md` is a poor name for a technical
   record and becomes `record.md` (A1).
2. Artifacts dir keyed by repository: re-derived from "the place varies" and invariant 7.
   The `<service>` level becomes the area key of the Shelf.
3. The frontmatter fields: re-derived from the Listing's need for stable fields and from
   Review's need for a join key. `pattern` and `symbols` are the join keys.
4. Dedup only at filing: re-derived from "review cadence is independent of filing cadence".
5. Whole table first: re-derived from "the register grows" and "a trend must be
   falsifiable".
6. Accounting gate: re-derived from falsifiability.
7. Decision record in the artifacts dir with a `repos` field: re-derived from the force
   that a cluster spans repositories, which no single repository can own.
8. Repo key from the id prefix: **rejected**. See lookup L1. The repository is a field the
   Producer supplies from its run, and the Shelf keys on it.
9. One git repo with the register tracked: kept as lookup L2.

Open lookups:

- L1. Does an id's prefix name the repository when several repositories share one artifacts
  place? Decides whether claim 8 stands.
- L2. Is the artifacts place a git repository today, and what does it ignore? Decides how
  Intake commits a record.
- L3. Does any lane read the backlog by path or section today, so that moving the register
  breaks a drain? Decides what Promotion must keep.
- L4. Does the existing dedup see the whole open register or one section? Decides whether
  the Same-cause rule can be reused as is.

SOLID, one question each:

- Single responsibility: every Owns reads without "and". The Decision record owns the
  document and its evidence list, which is one thing: a decision without evidence is not
  one.
- Open/closed: a fourth Producer adds one concept and one line in the caller; a third Lane
  adds one concept and one line in the Pick.
- Liskov: each Producer variant is a Producer only; the coder's follow-ups are not the base
  of QA's deferred checks.
- Interface segregation: the Producer role declares only "read your origin into
  Proposals". The Lane role declares only "start on this Record".
- Dependency inversion: Intake's Never-knows names no Producer variant; Promotion's names no
  Lane variant.

## 5. Mapping onto the existing system

Revision log:

- Build, before slice 1. Section 6: the deletion of the bullet grammar moves from slice 2
  to slice 6. After slice 2 the fix lane, author story mode, story-edit, epic-edit and the
  two survey emitters still read or write bullets. Each producer now moves in the slice that
  moves its reader: QA leftovers with the fix lane in slice 3, and the survey emitters, the
  epic-edit run variable and story mode in slice 6. Slice 6 deletes the file doc root, the
  section titles, the bullet readers and writers, the author config's file requirement and
  genesis's file check. `markdown.bracketed` stays, because the epic index reads it. The
  Import ships in slice 2, and the user runs it once slice 6 has landed.
- Build, before slice 1. Section 2, Producer gained two variants the design missed: the code
  survey's findings and the parity survey's missing surfaces. Both write a fenced bullet
  section that story mode consumes. As records they carry `filed_by: survey` and
  `filed_by: parity`. A rerun reuses the open record whose title matches, and a stale record
  stays open until a person closes it. Parity findings are user-facing, which strains
  section 1's out-of-scope line. They stay in the register until a milestone path takes
  them, and that move is a follow-up.
- Build, before slice 1. Section 5, Lane: story under epic is author story mode
  (`author/shared/nodes/story_mode.py`: `seed_story`, `prune_bullet`), reached from the
  story mode of `workhorse-author`, story-edit's add and epic-edit's add-story. It is not
  `ostler create story` alone.
- Build, before slice 1. Section 5, Shelf and Record: the records get their own module,
  `ostler/ostler/register.py`, and their own doc root key, `register`, resolved to
  `<artifacts>/backlog` the way `specs` is. The file root `backlog` and
  `ostler/ostler/backlog.py` live beside them until slice 6 deletes both.
  `paths.decisions_dir` derives from the file root today and is re-derived from the docs
  root in slice 6.
- Build, before slice 1. Section 2, Record: `filed_by` takes one value per Producer:
  `coder`, `qa` (the leftovers the fix lane drains), `qa-deferred` (book checks), `person`,
  `survey`, `parity`. `status` is one of `open`, `done`, `dropped`, `promoted`. The fix lane
  draws `filed_by: qa` only, so a book check is never drained, as today.
- Build, before slice 1. Section 5, Proposal: `FollowUp` gains `repo`, `area`, `pattern`
  and `symbols`, which the dev turn's prompt asks for. A workspace story spans several
  repositories, so the run alone does not say which one a follow-up belongs to (A6). The
  coder Producer takes the follow-up's `repo` when it names a repository of the run's
  workspace, takes the only repository when there is one, and otherwise refuses the
  follow-up with a logged reason.
- Build, before slice 1. Section 6, slice 2: the Import cannot land the records and the
  deletion in one commit, because they live in two repositories. It commits the records in
  the artifacts repo and removes the old file from the code repository's working tree. The
  user commits that removal in the code repository.
- Build, before slice 1. Section 5b, ostler CLI: `prune` keeps its name and becomes a
  Closure, `ostler backlog prune <id> --as done|dropped|promoted --reason <text>`.
- Section 4, claim 8, rejected after L1: ostler mints ids from one registry per docs root,
  and in a workspace the docs root is the shared artifacts place, so every repository
  shares one prefix. The repository is a Record field supplied by the Producer.
- Section 2, Intake, concept **Import** added after reading `ostler backlog adopt` and this
  repo's own `docs/backload.md`: twenty-one unnamed one-liners that must become records
  once. The design had missed the migration.
- Section 2, Promotion, concept **Closure** gained the "dropped" state and its reason after
  reading the `(blocked …)` suffix the fix lane honours. A blocked bullet is a record with a
  reason, not a deleted one.
- Section 1, out of scope, gained the per-repository ADR copy as an accepted loss after L2.

Lookups resolved:

- L1. `ostler/ostler/ids.py:58` derives the prefix once per graph root and pins it. In a
  workspace the root is the artifacts dir (`core/stablemate_core/config.py:507`), so the
  prefix does not name the repository. Claim 8 rejected.
- L2. The artifacts place at `~/Documents/ai-artifacts` had no `.git` until 2026-10-23,
  when it was initialised by hand with the same ignore file `ensure_artifacts_repo`
  (`core/stablemate_core/config.py:514`) would write: `specs/` only, no remote. The
  coder's filing commits through `commit_paths`
  (`workflows/src/workhorse_workflows/kit/git.py:118`), which returns False without a
  repository, so every workspace filing before that date was silently skipped. The
  artifacts place now has three ignored, session-owned folders, `specs/`, `scratch/` and
  `researches/`, and the register's `backlog/` and `adr/` are the tracked ones. Intake
  still calls `ensure_artifacts_repo` so a fresh machine behaves the same, and that helper
  writes the three ignore lines instead of one.
- L3. The fix lane reads one section of one markdown file by title
  (`workflows/src/workhorse_workflows/coder/shared/backlog.py:select_fix_item`). The
  epic-edit planner is told the backlog path by a run variable
  (`author/epic_edit/prompts/plan-epic-edit.md:21`). Both are receivers in 5b.
- L4. `Seen` seeds from every bullet of the file and `_filed_as` reads every bullet; neither
  is section-scoped. The Same-cause rule can read the whole open register.

### Parts

**Intake**: Reshape. Lives in `workflows/src/workhorse_workflows/coder/shared/backlog.py`.
Today it writes one bullet through `Ostler.backlog_add` and commits into whatever root
`find_docs_root` returns. The mismatch: it knows the store layout (section titles, the
bullet grammar) and the commit target. The design moves layout knowledge to the Register.

**Register**: Reshape. Lives in `ostler/ostler/backlog.py` and `ostler/ostler/path.py:64`.
Today the `backlog` doc root is one file, `docs/backlog.md`, under the graph root, and in a
workspace that is one flat file for every repository. The design makes it a directory root
resolved into the artifacts place like `specs` already is (`ostler/ostler/model.py:662`),
keyed by repository and area.

**Review**: New. A workflow lane under `workflows/src/workhorse_workflows/`, modelled on the
surveyor's partition step and its deterministic gate
(`author/surveyor/prompts/partition-findings.md`), which already reads every record and
rejects a partition that leaves one out.

**Decision**: New. A markdown kind under the artifacts place at `adr/<id>.md`, written by
the Review lane. Ostler gains a reader for it so `ids.referenced` and the doctor see its
evidence links (`ostler/ostler/ids.py:153` already folds backlog ids into the referenced
set).

**Promotion**: Reshape. The fix lane's `select_fix_item` is one Lane variant and today is
also the Pick: it draws the first drainable bullet of a section. The design separates Pick
from Lane so a person can pick a record for either lane.

### Concepts

| Concept | Verdict | Where, and the mismatch if any |
|---|---|---|
| Proposal | Exists | `schemas/dev_story.py` `FollowUp` (title, reason). Gains the code it touches. |
| Producer: coder follow-ups | Exists | `backlog.py:file_follow_up_backlog`. Writes a bullet; will write a Record. |
| Producer: QA deferred checks | Exists | `backlog.py:file_deferred_obligations`. Same change. |
| Producer: person | Exists | `ostler backlog add` (`cli.py:478`). Same change; gains `--repo` and `--area`. |
| Same-cause rule | Exists | `backlog.py:Seen`, `_filed_as`, `causes.same_causes`. Reads bullets; will read Listing lines. |
| Import | Exists | `ostler backlog adopt`. Will mint a Record per line instead of an id per bullet. |
| Record | New | `ostler/ostler/backlog.py`, a frozen value read from `record.md` frontmatter and body. |
| Shelf | Reshape | `path.py:backlog_path_in` returns a file under root. Returns `<artifacts>/backlog` and takes a repository. |
| Listing | New | `ostler backlog list` exists for bullets; gains the one-line-per-record table with fixed columns. |
| Locator | Exists | `ids.resolve` short handles. Gains folder resolution. |
| Complete read, Accounting | New | The Review lane's gate, after `surveyor/nodes` partition errors. |
| Cluster, Trend report | New | The Review lane's prompt and schema. |
| Decision record, Threshold, Back-link | New | `ostler/ostler/adr.py` reader and writer; the lane writes it. |
| Pick | Reshape | `select_fix_item` draws by section; will draw by status and repository. |
| Lane: fix unit | Exists | `coder/fix/flow.py`. Unchanged inside. |
| Lane: story under epic | Exists | Author story mode, `author/shared/nodes/story_mode.py` (`seed_story`, `prune_bullet`), reached from story mode, story-edit and epic-edit. Unchanged inside; resolves a record id where it resolved a bullet. |
| Producer: survey, parity | Exists | `author/surveyor/nodes/partition.py:emit_artifacts` and `author/parity_surveyor/nodes/parity.py:emit_parity_backlog`. Write fenced bullet sections; will write records. |
| Closure | Reshape | `backlog_prune` deletes the line; becomes a status write. |

### What the existing system has that the design lacks

- `## Filed by coder` and `## Book checks QA could not run` as section titles. Sections
  were the old store's only key. They become the `filed_by` and `area` fields. Not waste,
  absorbed.
- `backlog-items.json` in a spec dir and its drain `file_backlog_items`. A fourth Producer
  the design missed: QA's own leftovers. Added as a variant with no new concept.
- The `(blocked …)` suffix. Absorbed into Closure as the dropped-with-reason state.
- The milestone `sourceItems` doctor check (`doctor.py:1340`). The user-facing path reads
  register ids. It stays and reads the same id space, so no change.
- `backlog_file(root, configured)` honouring a run parameter `backlog_path`. A per-run path
  override is waste under invariant 7 and is deleted with the parameter.
- The `backlog` doc root as a file path in `BUILTIN_DOC_ROOTS` (`model.py:655`), the
  `- [id] text` grammar in `markdown.bracketed`, and the section titles. All waste once
  Import has run; slice 6 deletes them, with the last reader.

### Claims against the existing system

Claims 1 to 7 are not followed by the code today and are followed by the design. Claim 8 is
followed by neither. Claim 9 is followed by neither today; the design follows it.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Fix lane | Draws the next drainable defect the coder filed, in filing order, skipping dropped ones | `workflows/tests`, 32 tests selected by `backlog`, `follow_up`, `deferred` | 32 green | every test that asserts a behaviour is rewritten over records and green; a test that asserts only the bullet grammar is deleted and listed in the slice's report |
| ostler CLI users | `backlog add`, `list`, `prune`, `adopt`, and `create backlog-item` with the same exit codes and ids | `ostler/tests/test_backlog.py`, 9 tests | 9 green | the same five commands exist over records with the same exit codes; grammar-only tests deleted and listed |
| Dev turn operator | A commit "file the deferred follow-ups of <story>" after a story with follow-ups | nothing | one commit per story with follow-ups in a single-repo run; none in a workspace run before 2026-10-23 (L2) | one commit in the artifacts repo in both modes |
| Epic-edit planner | A readable backlog at the path its run variable names | nothing | the prompt names a file | the variable names the Listing, and the prompt reads one page |
| Doctor | Backlog ids count as referenced, so a milestone `sourceItems` id resolves | ostler doctor tests on `backlog-item-in-multiple-milestones` | green | green |
| Lint gate | Zero findings from ruff, ty and basedpyright | `make lint` | 0 | 0 |
| This repo's own list | `docs/backload.md`, 21 one-liners, 3 with ids | nothing | 21 lines | 21 records after Import, the 3 ids kept |
| The two other workspace repositories' lists | Every line of each `docs/backlog.md`, with its id where it has one | nothing | not measured (A11) | one record per line, every existing id kept, the file deleted |

Rows enforced by nothing: the dev-turn commit becomes invariant 7's companion, "a filed
record is committed where it lives", owned by Intake. The epic-edit path and the repo's own
list are kept on purpose and gain a test in their slice.

## 6. Slices

**Slice 1, the walking skeleton.** A coder follow-up becomes a record on the shelf and shows
in the listing. Parts: Intake (Producer: coder follow-ups, Same-cause rule), Register
(Record, Shelf, Listing, Locator). Done when: a dev turn with two follow-ups in a workspace
run leaves two `record.md` folders under `<artifacts>/backlog/<repo>/<area>/<id>/`, one
commit in the artifacts repo, `ostler backlog list` prints two lines with repository, area,
pattern and summary, and a second filing of the same title adds nothing. 5b: the 32
workflow tests and the 9 ostler tests pass, rewritten one for one where they asserted on
bullets; lint 0.

**Slice 2, the other producers and the import.** Parts: Intake (Producer: QA deferred
checks, person; Import). Done when: `file_deferred_obligations` writes a record with area
`book` and `filed_by: qa-deferred`; `ostler backlog add --repo --area` writes one by hand;
`ostler backlog adopt --repo <name> <file>` runs once per workspace repository, three in
all, and turns each one's existing list into records keyed by that repository, keeping
every id a line already had and minting one for each line that had none; this repository's
`docs/backload.md` yields 21 records with its 3 ids kept; the records are committed in the
artifacts repo and the old list is removed from the code repository's working tree. 5b
unchanged.

**Slice 3, promotion.** Parts: Promotion (Pick, Lane: fix unit, Closure), Intake
(Producer: QA leftovers). Done when: QA's leftovers land as records with `filed_by: qa`;
the fix lane draws from records with status `open` and `filed_by: qa`, closes one as
`done` with the commit that fixed it, and a record closed as `dropped` carries its reason
where the `(blocked …)` suffix used to. The fix lane's own tests pass unchanged in what
they assert.

**Slice 4, review.** Parts: Review (Complete read, Cluster, Trend report, Accounting). Done
when: a `workhorse-review-debt` run over a register of N records writes `trends.md` naming
every one of the N ids, and a report missing one id is rejected and sent back with the
missing ids named, twice at most before the run stops with the gap in its result.

**Slice 5, decision.** Parts: Decision (Decision record, Threshold, Back-link). Done when:
a cluster of three or more yields `adr/<id>.md` with `status: proposed`, `repos`, and the
evidence ids; each evidence record carries `decision: <id>`; the doctor reports a decision
whose evidence id resolves to nothing.

**Slice 6, the story lane.** Parts: Promotion (Lane: story under epic), Intake (Producer:
survey, parity). Done when: a person picks a record into an epic with one command, the
story's `covers` names the record id, and the record closes as `promoted` with the story
slug; story mode, story-edit and epic-edit resolve a record id where they resolved a
bullet; the two survey emitters write records; the epic-edit run variable resolves to the
listing and a test reads it; no reader or writer of the bullet list remains outside the
Import.

## 7. Assumptions

1. **The register never needs to be read from inside a code repository by a non-agent
   tool.** Decided: records live only in the artifacts place (invariant 7). Basis: the
   request's words, "THE place for AI-generated and managed work". If wrong: re-derive the
   Shelf and invariant 7, and the out-of-scope loss in section 1.
2. **A workspace of repositories shares one artifacts place and one id prefix.** Decided:
   repository is a Record field, not an id prefix (claim 8 rejected). Basis:
   `ostler/ostler/ids.py:58` and `config.py:507`. If wrong: nothing breaks, the field is
   redundant.
3. **The fix lane may keep drawing by status and filer without a human pick.** Decided:
   slice 3 keeps the autonomous drain for QA-filed defects. Basis: the user's words, "the
   backlog is now only used for nice-to-have follow-ups", read as "the defect drain is
   not what changes". If wrong: re-derive Pick in section 2 and slice 3.
4. **A few hundred records fit one review context as a listing.** Decided: Complete read
   hands the whole listing to one model turn. Basis: 54 spec folders exist after the
   workspace's first months; a line is under 200 characters. If wrong: re-derive Complete
   read as a batched read with a merged accounting, still one gate.
5. **Three items is the threshold worth a decision.** Decided: Threshold defaults to 3.
   Basis: none. If wrong: one setting changes.
6. **The run that files knows its repository name.** Decided: the Producer supplies `repo`
   from the run's repository root name. Basis: `commits.scope(root.name)` already uses it.
   If wrong: re-derive invariant 2's upholder.
7. **Nobody edits `record.md` frontmatter by hand in a way the Listing cannot parse.**
   Decided: the Listing skips an unparsable record and the doctor reports it. Basis: the
   milestone kind takes the same stance. If wrong: add a Record invariant with a
   repair.
8. **`record.md` is the right file name.** Decided: A1 renames the request's `story.md`.
   Basis: a technical improvement is not a story and the story kind already owns that
   name in ostler's registry. If wrong: one constant.
9. **Time.** Slice 1 is two to three days of builder work; the whole is two to three
   weeks. Basis: 32 tests to rewrite and two modules to reshape. If wrong: slice order
   stands, the plan's end date moves.
10. **Proof.** A dev turn in a test fixture with two follow-ups stands in for a live run.
    Basis: the workflow tests already drive dev turns through substitution. If wrong: add
    a live run to slice 1's done-when, which needs a workspace and a day.
11. **Each of the two other workspace repositories keeps its backlog at ostler's default
    `docs/backlog.md`.** Decided: Import reads that path per repository, converts every line
    to a record, and deletes the file; anything not wanted is closed as dropped afterwards,
    so nothing is lost by the migration itself. No reader of the old file remains. Basis:
    the user's words, "migrate these to the new way and forget about the old one, no
    backward compat"; the paths were not read. If wrong only in the path: slice 2's
    done-when names the real ones.
