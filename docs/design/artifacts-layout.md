# Artifacts layout and the docs home

Disclosure: this note was written after reading the existing system. The conversation that
settled the layout read `core/stablemate_core/config.py`, the ostler shelf roots, the register
and the decision records, and the coder's decisions folder. Every part below was checked
against the test "would I have named this without having seen the solution?".

## 1. Problem

An operator who works across several repositories records a decision, and an agent in another
session never finds it. A coder run in a workspace writes the operator's answer under the
artifacts dir. An interactive session in the same repository writes it under the repository.
Each one reads only its own folder, so the operator answers the same question twice.

The artifacts dir also mixes two kinds of document with no rule between them. Some documents
the operator writes and keeps, such as a service book or a milestone. Others stand in for an
external system, such as a ticket board or a backlog. Nothing says which folder holds which
kind, or which one git tracks.

Done looks like this to the operator:

- Every agent working on a repository, whether a coder run or an interactive session, a
  checkout or a worktree, files and reads decisions in one folder.
- `ls docs/decisions` and `ostler search` show each decision by a readable name.
- One rule answers where any document goes: `docs/` is tracked, the artifacts top level is not.

Settled with the operator on 2026-10-28:

- The docs home is the repository for a repository listed in no workspace. It is the
  artifacts dir for a repository listed in any workspace.
- All workspaces share one artifacts dir. Workspaces may overlap.
- `$STABLEMATE_WORKSPACE` goes away. Workspaces live only in the home config.
- Tracked, under `docs/` of the docs home: `services/<service>/`, `milestones/<slug>/`,
  `decisions/<slug>/decision.md`, `adrs/<slug>/adr.md`.
- Untracked, at the artifacts top level: `backlogs/<repo>/<area>/<id>/`, `epics/<KEY>/`,
  `specs/<id>/`, `researches/`, `benchmarks/`, `scratch/`.
- Folder names are plural, except `scratch/`.
- A decision names its repository in its frontmatter, not in its path.
- Service ids are unique across every workspace.
- A monorepo keeps `docs/decisions` in the repository.
- Agents learn where decisions go through skills.

Out of scope:

- Container runs. The docker harness is a draft with no published image.
- Superseding or retiring a decision.
- A remote for the artifacts repo.
- The history of backlog records. The operator accepts that untracking the backlog drops it.
- Epics in a monorepo stay tracked in the repository's git. The operator accepts that they
  move to the untracked artifacts top level.

## 1b. Claims

1. The active workspace is a property of the process, set by `workhorse run` through
   `$STABLEMATE_WORKSPACE` (core config, `active_workspace`).
2. ADRs and the backlog live side by side at the artifacts top level (ostler `doc_roots`).
3. Every backlog filing and close is a commit in the artifacts repo (ostler `register.commit`).
4. An ADR is named by a minted id (`adr.propose`).

## 2. Parts and concepts

### Level 1

1. **Docs home**. It owns the answer to "where do this repository's tracked documents live".
   It never knows which documents exist. It hands a folder to every shelf.
2. **Kept documents**. It owns the documents the operator writes or approves and keeps under
   version control. It never knows how the docs home was chosen. It reads the folder from the
   docs home.
3. **External stand-ins**. It owns the documents that would live in a ticket system or a wiki
   in another setup. It never knows git. It always sits at the artifacts top level.
4. **Layout move**. It owns recognising a folder in the old layout and naming the move. It
   never moves anything itself. It runs before any shelf is read.

Flow: a command starts in a folder. The docs home resolves that folder's repository to a
docs home. The layout move checks the docs home and the artifacts dir and refuses on an old
layout. Each shelf then reads or writes under its own root.

### Level 2

**Docs home**

| Concept | Owns | Never knows |
|---|---|---|
| Workspace table | the named groups of repositories in the home config | which process runs |
| Repository identity | the facts that make a checkout one repository: its folder, the main folder of its worktree, its origin URL | workspace names |
| Membership | whether a repository identity matches any member of any workspace | the shelves |
| Run members | the member list of the one workspace a run names, for checkouts and repository-qualified refs | where documents go |

**Kept documents**

| Concept | Owns | Never knows |
|---|---|---|
| Service book | `docs/services/<service>/`, one folder per service id | other workspaces' names |
| Service id rule | that one service id belongs to one repository | how a page is written |
| Milestone | `docs/milestones/<slug>/` | epics |
| Decision | `docs/decisions/<slug>/decision.md` and the files beside it | the agent that filed it |
| Decision filing | minting a free slug and writing the empty decision for one repository | the question's content |
| ADR | `docs/adrs/<slug>/adr.md` and the files beside it | how its evidence records are stored |

**External stand-ins**

| Concept | Owns | Never knows |
|---|---|---|
| Backlog shelf | `backlogs/<repo>/<area>/<id>/record.md` | git |
| Epic shelf | `epics/<KEY>/` and the stories under it | the docs home |
| Spec shelf | `specs/<id>/` | the docs home |
| Working folders | `researches/`, `benchmarks/`, `scratch/` | every shelf |
| Ignore list | that every top-level folder except `docs/` is ignored | what each folder holds |

## 3. Invariants

1. Every agent on one repository gets the same docs home. The owner is **Membership**.
   Repository identity upholds it by resolving a worktree and a clone to the member they came
   from.
2. One member name maps to one folder across all workspaces. The owner is **Workspace
   table**, which refuses the home config otherwise (A2).
3. Two decisions never share a slug. The owner is **Decision filing**, which refuses a taken
   slug.
4. A service id belongs to one repository. The owner is **Service id rule**, run by doctor.
5. Nothing at the artifacts top level is tracked, and everything under `docs/` is. The owner
   is **Ignore list**, written by the artifacts repo setup.
6. No shelf is read through an old layout. The owner is **Layout move**.

## 4. Forces and patterns

Forces:

- The same repository reaches an agent in three shapes: the member folder, a worktree of it,
  and a clone of its URL.
- Workspaces grow and overlap, and the operator edits them by hand.
- A run needs one workspace's member list, while a document lookup needs only "is this a
  member of any".
- Agents cannot mint a ULID or compute a docs home by hand.
- Existing artifacts dirs already hold the old layout.

Patterns:

- **Between parts:** one value handed along. The docs home is a folder, computed once per
  command and passed to each shelf. No part reads the environment.
- **Repository identity:** a plain function returning a small value type with three fields.
  No variation, so no role.
- **Membership:** a plain function over the workspace table. Any match wins, because all
  workspaces share one docs home, so overlap needs no tiebreak.
- **Run members:** the run's own parameter, read from its checkpoint. It replaces claim 1.
- **Decision filing:** one ostler command, `ostler decisions add <slug>`, which skills and
  prompts call. It answers the force that agents cannot compute the docs home.
- **Layout move:** a check at graph load that refuses with the exact moves printed. It does not
  read both layouts.

Claims:

- Claim 1 is rejected. A process flag reaches only the processes a run starts, which is the
  defect in section 1.
- Claim 2 is rejected. An ADR is a kept document, and the backlog is a stand-in.
- Claim 3 is rejected for the backlog, which is untracked now. An ADR proposal still commits
  its own file where the docs home is the artifacts repo.
- Claim 4 is rejected. A slug makes an ADR findable by name, as with decisions.

SOLID check: each Owns reads without "and". Repository identity holds three facts that answer
one question, so it is one concept. Adding a fourth identity shape, such as a mirror URL,
changes Repository identity alone.

## 5. Mapping onto the existing system

Revision log:

1. Section 2, Repository identity: added the worktree and clone shapes after reading
   `kit/workspace.checkout_workspace`, which builds run checkouts from a member's URL or as a
   worktree of its folder. A folder match alone misses every run checkout.
2. Section 1, out of scope: added the backlog history and monorepo epics losses after section 5b.

### Docs home

- **Workspace table**: Exists. `core/stablemate_core/config.py` `resolve_workspace` and
  `_member_of`. Reshape: it gains a check that one member name maps to one folder across all
  workspaces (A2).
- **Repository identity**: New, in core config beside `member_name`.
- **Membership**: Reshape. `docs_home(start)` today returns the artifacts dir when
  `active_workspace()` is set. It changes to return the artifacts dir when the identity of the
  repository holding `start` matches any member. `active_workspace` and `WORKSPACE_ENV` are
  deleted.
- **Run members**: Reshape.
  - `workhorse/workhorse/cli/run.py` `_enter_workspace` stops exporting the variable. It keeps
    validating the name and creating the artifacts repo.
  - `ostler/ostler/provenance.py` `effective_checkouts` today maps repository-qualified refs
    through the active workspace. It changes to the union of every workspace's members, which
    invariant 2 makes unambiguous.
  - `paddock/paddock/runner.py` stops popping the variable. `paddock/paddock/tasks/tree.py`
    `_workspace_env` writes the copy's members into the trial's home config instead (A3).
- Tests that set the variable move to a home config with a `[workspaces]` table:
  `core/tests/test_workspaces.py`, `workhorse/tests/test_workspace_flag.py`,
  `workflows/tests/test_kit_workspace.py`, `workflows/tests/coder/shared/test_pr_local_merge.py`,
  `workflows/tests/okf_book/conftest.py`, `ostler/tests/test_qa_tools.py`,
  `ostler/tests/test_workspace_docs_home.py`, `ostler/tests/test_qa_runbook_workspace.py`,
  `paddock/tests/test_runner.py`.

### Kept documents

- **Service book**: Exists. `docs/services/<service>/` under the docs home.
- **Service id rule**: New. A doctor check that a service's `code:` bullets cite one
  repository (A7).
- **Milestone**: Exists, unchanged.
- **Decision**: Reshape.
  - `workflows/.../coder/shared/paths.py` `decisions_dir` already resolves
    `<docs home>/docs/decisions`, and stays.
  - Writers change from `<slug>.md` to the command: `coder/shared/prompts/resolve-operator.md`,
    `coder/dev/prompts/_dev-scope.md`, and rule 2.13 in
    `base-library/.../code-structure/references/modules.md`.
  - Readers glob `*/decision.md`: `coder/fix/prompts/fix-item.md` and the resolver prompt.
  - ostler `doc_roots` gains a `decisions` root, so `ostler search` indexes it.
  - Frontmatter: `repo`, `status` (`accepted`), `summary`. Body sections: Question, Decided,
    Grounded in, Context, following the template rule 2.13 ships today. No `area` field,
    because no reader filters by it.
- **Decision filing**: New. `ostler decisions add <slug> [--repo <name>] --summary "<line>"`.
  `--repo` defaults to the member name of the repository holding the cwd. It prints the path of
  `decision.md`.
- **ADR**: Reshape.
  - `ostler/ostler/path.py` `adr_root_in` and `adr_root`, and `model.doc_roots`, move the root
    to `<docs home>/docs/adrs`.
  - `ostler/ostler/adr.py` `propose` takes a slug from review-debt in place of
    `ids.allocate`, and writes `<slug>/adr.md`. It commits only where the docs home is the
    artifacts repo (A4). `ids.decision_files` globs `*/adr.md`.
  - `workflows/.../review_debt/nodes/decisions.py` asks its agent for the slug.

### External stand-ins

- **Backlog shelf**: Reshape.
  - `path.register_root_in` and `model.doc_roots` rename `backlog` to `backlogs`.
  - `register.file_record`, `register.close_and_commit` and `register.commit` stop committing.
    `register.commit` is deleted once `adr.propose` commits through its own helper.
- **Epic shelf**: Reshape. `model.BUILTIN_DOC_ROOTS` `epics` moves from `<docs home>/docs/epics`
  to `<artifacts>/epics`. Callers through `epics_root_in`: `workflows/.../kit/paths.py`,
  `coder/shared/paths.py` `epics_repo_root`, `author/shared/paths.py`, `coder/shared/queue.py`,
  `okf_book/shared/book_flow.py`.
- **Spec shelf**: Exists. `doc_roots` already overrides specs to `<artifacts>/specs`. The
  unused `docs/specs` entry in `BUILTIN_DOC_ROOTS` goes.
- **Working folders**: Exist.
- **Ignore list**: Reshape. `core` `ARTIFACTS_IGNORED` lists `specs/`, `scratch/`,
  `researches/`. It becomes every top-level folder except `docs/`: `backlogs/`, `epics/`,
  `specs/`, `researches/`, `benchmarks/`, `scratch/`. The operator's `.gitignore` already
  carries `benchmarks/` by hand.

### Layout move

New, in ostler graph load. It refuses when the artifacts dir holds `backlog/` or `adr/`, or a
docs home holds `docs/epics/`. It prints the moves:

- `git mv backlog backlogs`, then `git rm -r --cached backlogs`;
- `docs/epics/<KEY>` to `<artifacts>/epics/<KEY>`;
- `adr/<id>.md` to `docs/adrs/<slug>/adr.md`.

The operator's artifacts dir holds 13 tracked backlog files and no `adr/`.

### What the existing system has that the design lacks

- `$STABLEMATE_ARTIFACTS_DIR` stays. Paddock uses it to point a trial at its own artifacts dir,
  and it does not choose a workspace.
- The grill skill files settled decisions "where the repo keeps its rules". That covers book
  concepts, not this shelf. No change.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A coder run in a workspace | its docs home is the artifacts dir | `ostler/tests/test_workspace_docs_home.py` | artifacts dir | artifacts dir, for a member folder, a worktree and a clone |
| An agent in a repository listed in no workspace | its docs home is the repository | the same test | the repository | the repository |
| The operator's artifacts dir during a paddock trial | a trial never writes to it | `paddock/tests/test_runner.py` | untouched | untouched |
| A run resolving `repo:path` refs | each member name maps to its folder | `ostler/tests/test_qa_runbook_workspace.py` | the named workspace's map | the same map for every workspace that lists the member |
| `ostler search` over the operator's book | finds services, epics, specs, backlog records | the search tests | every root indexed | the same roots plus decisions |
| An ostler command's start-up time | one config read, no git call | nothing | not measured (A8) | under 50 ms added |

## 6. Slices

Each slice lands its book pages in the same commit as its code, starting with one concept page,
`artifacts-layout`, in the ostler book. Each slice grows that page with one `rule:` bullet per
folder it touches. `the-debt-register`, `decision-records`, `workflow-kit-paths`,
`coder-path-resolution` and `coder-shared-resolution` link to it.

1. **One docs home for every agent.** Repository identity, Membership and Run members. The
   variable is gone. Paddock writes its trial's workspace table.
   Done when: from a member folder, a worktree of it, and a clone of its URL, with no variable
   set, `ostler search` reads the artifacts book. A repository listed in no workspace still
   reads its own book. Every 5b row holds, and the start-up time is measured.
2. **Decisions filed by name.** Decision filing, the `decisions` search root, the prompts and
   rule 2.13.
   Done when: a coder run's blocked answer and an interactive session's answer for the same
   member repository land in the same `docs/decisions/<slug>/decision.md` folder, and
   `ostler search <slug word>` returns both.
3. **Kept and stand-in shelves.** `backlogs/` untracked with no commits, `docs/adrs/<slug>/`,
   `epics/` at the top level, the ignore list, the layout move, and the service id rule.
   Done when: the operator's artifacts dir passes the layout move after the printed commands,
   review-debt proposes an ADR under `docs/adrs/<slug>/adr.md`, and doctor flags a service that
   cites two repositories.

## 7. Assumptions

1. **A checkout belongs to a member when its folder, its worktree's main folder or its origin
   URL matches that member.** Decided: Repository identity holds those three facts. Basis:
   `kit/workspace.checkout_workspace` clones from `url` or adds a worktree of the member folder.
   If wrong: section 2 Repository identity, invariant 1, slice 1.
2. **Overlapping workspaces never bind one member name to two folders.** Decided: the
   workspace table refuses such a home config. Basis: none. If wrong: invariant 2 and Run
   members, which would need the run's workspace name to break the tie.
3. **A paddock trial can carry its own home config through `$STABLEMATE_CONFIG`.** Decided:
   paddock writes the copy's workspace table there. Basis: benchmarks keep a
   `home-config.toml` per gold benchmark. If wrong: 5b row 3, slice 1.
4. **In a monorepo, review-debt commits the ADR file with its own changes.** Decided:
   `adr.propose` commits only in the artifacts repo. Basis: none. If wrong: section 5 ADR,
   slice 3.
5. **A clone of a member's URL made outside any workspace task is a member too.** Decided: its
   docs home is the artifacts dir. Basis: the operator's answer that a repository in any
   workspace uses the artifacts dir. If wrong: Repository identity drops the URL shape, and
   assumption 1 changes.
6. **No decision exists yet in the old `docs/decisions/<slug>.md` shape.** Decided: the layout
   move skips decisions. Basis: rule 2.13 shipped on 2026-10-28. If wrong: the layout move
   adds the decision move.
7. **A service's `code:` bullets name the repository of each cited file in a workspace.**
   Decided: the service id rule reads them. Basis: `provenance.effective_checkouts` resolves
   repository-qualified refs. If wrong: section 2 Service id rule needs a `repo` field on the
   service page.
8. **One git call per command to read the repository identity costs under 50 ms.** Decided:
   no cache. Basis: none. If wrong: Membership caches the identity per process.
