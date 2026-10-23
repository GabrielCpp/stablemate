# Milestone authoring

**Disclosure.** I read the existing solution before this note's order applied: the author
workflow's sub-flows, ostler's model and doctor, workhorse's pipeline and work list, and the
coder's workspace handling. Every design decision that reached me that way, or through the
grill, is a claim in section 1b. Section 4 re-derives or rejects each one.

The settled questions behind this note are in
[milestone-authoring-grill.md](milestone-authoring-grill.md). Client repos appear as
placeholders: `acme` is the web client with today's only milestone, `globex` is the mobile
client.

## 1. Problem

**Who feels this.** Two people. The release planner writes what a release must make true,
then watches an agent restate it, ask product questions back, and draw screens nobody agreed
to. The grill trees, designs and journey sketches the planner made along the way have no
place the decomposition reads, so the agents re-decide what was already settled. The workflow
author, the second person, writes the same "take the next item, run it, mark it done" loop by
hand in every stage, and each copy resumes differently after a stop.

**Done looks like.**

- The planner writes one release folder in one interactive session. A run consumes it as is,
  with no restating stage.
- A product question reaches the planner only when its answer would change the release
  contract. Every other question gets an answer the planner can read and overrule.
- 100% of stories that change a web or mobile service carry a mockup that a reviewer judged
  to agree with the release's journey mockup.
- Every story names the services it changes, by book name.
- A product spread over several repos keeps all its docs in one place, and every workflow
  finds them there.
- A stage that drains one kind of work is one line of workflow code.
- A run ends with every work item done, or at a gate that lists the unfinished ones.

**Out of scope.**

- Parallel work inside a run.
- Narrowing QA or the coder's checks to a story's services. The coder only passes the list
  into its prompt.
- Pushing the shared docs history to a remote.
- Changing the grill or decompose skills.
- The layout of epics and stories on disk.
- Migrating more than the one existing milestone, and reading the old format.

## 1b. Claims

From the grill record, numbered by its entries.

1. A release folder replaces the roadmap item, and the roadmap-to-milestone stage goes away.
   (G1)
2. The folder lives at `docs/milestones/<slug>/`, wherever the docs live. (G2)
3. The folder holds `milestone.md`, `grills/`, `mockups/` and `artifacts/`. Design notes stay
   outside it and are linked. (G4)
4. Selection takes the one approved milestone and fails on two. (G6)
5. A readiness check in ostler's doctor gates approval, and Author refuses a milestone that
   fails it. (G9)
6. One docs location per run: the repo's `docs/`, or `<artifacts_dir>/docs/` with
   `--workspace`. Never both, never searched across. (G13)
7. No per-workspace segment under the artifacts docs. (G14)
8. `docRoots` is removed. (G15)
9. `features` is renamed `services` all the way down. (G16)
10. Book names are unique. (G17)
11. Workspaces are named in the home config, and `--workspace <name>` replaces the coder's
    `.code-workspace` file. (G18)
12. The artifacts dir is a local git repo with no remote. (G19)
13. The coder treats the artifacts dir as one more workspace member. (G20)
14. A story lists its services by book name. (G21)
15. A UI book is one whose driver is `web` or `mobile`. (G22)
16. The pipeline is `self.pipeline(kind, to=target, n=chunk) or Continue(...)`, where the
    target is a state or a sub-flow and an item settles when its target returns. (G23, G24)
17. A barrier state fills the next kind from the graph. (G25)
18. The stage chain is: split epics, drain epics to the epic author, drain epics to the story
    split, drain stories to the story author, finalize. (G26)
19. The milestone becomes `authored` only when the work list is complete. Otherwise a gate
    lists the rest, and its answer requeues them. (G27)
20. A missing mockup blocks its story only. (G28)
21. The PM is the only agent reviewer. Deterministic checks stay as lint. (G29, G30)
22. Each stage has a fixed list of angles in code, one prompt per angle. (G31)
23. The PM spawns one sub-PM per angle through the CLI's subagent tool, or judges every angle
    itself where the CLI has none. (G32)
24. The PM answers product questions by filling gaps, and sends contract changes to the
    human. (G33)
25. Each question gets a fresh turn, and answers go to `grills/pm.md`. (G34)
26. The PM judges mockup agreement. (G35)

## 2. Parts and concepts

### Level 1

1. **Release contract.** Owns what the release must make true: its outcome, journeys,
   decisions, journey mockups and approval. Never knows how the release is broken into work.
   Hands the approved contract to Decomposition and Product judgement. Takes requests to
   amend it from Product judgement.
2. **Product layout.** Owns where a product's docs live and which services it has. Never
   knows what a release says. Hands the docs home and the service catalog to every other
   part.
3. **Decomposition.** Owns turning a contract into epics, stories and story mockups. Never
   knows who judges its output or in what order items arrive. Hands each output to Product
   judgement and raises product questions to it.
4. **Product judgement.** Owns whether an output serves the contract, and the answers to
   product questions inside the contract. Never knows how the output was produced. Hands
   verdicts and answers back, and hands contract-changing questions to Release contract.
5. **Progress.** Owns which work is pending, running, done or blocked, and when a run is
   finished. Never knows what a piece of work means. Hands items to Decomposition and
   reports completion to Release contract.

**Flow.** The planner builds the contract in a session, the readiness check passes, and the
planner approves it. A run starts: Product layout fixes the docs home and the catalog.
Release contract selects the approved milestone. Decomposition splits it into epics, and
Product judgement reviews the split. Progress fills the epic kind from the graph and drains
it through epic writing, then through story splitting with its review. It fills the story
kind and drains it through story mockup, story writing and review. During any stage,
Decomposition may raise a product question. Product judgement answers it, or asks Release
contract's owner. At the end, Progress checks every item is done. It then reports
completion, and Release contract marks the milestone authored, or Progress gates on the
rest.

### Level 2

**Release contract**

| Concept | Owns | Never knows |
|---|---|---|
| Milestone | the release outcome, journeys, constraints, acceptance and status | how it is decomposed |
| Decision record | one settled tree of decisions on one topic | which stage reads it |
| Design link | a pointer to a design that outlives the release | the design's content |
| Journey mockup | the visual contract of one journey through a UI service | story mockups |
| Readiness check | whether a milestone may be approved | the run that consumes it |
| Release selection | the one approved milestone in a docs home | the milestone's content |
| Amendment request | asking the contract's owner to change the contract | who raised the question |

**Product layout**

| Concept | Owns | Never knows |
|---|---|---|
| Workspace | a named set of repo folders on this machine | what docs say |
| Docs home | the one docs location of a run | which repos a workspace holds |
| Service catalog | the unique service names and each one's driver | stories |
| Docs history | local version history of a shared docs home | remotes |

**Decomposition**

| Concept | Owns | Never knows |
|---|---|---|
| Epic split | the ordered epics of a milestone | stories |
| Epic writing | one epic's page and its seeds | other epics |
| Story split | the stories of one epic and their services | story pages |
| Story mockup | the visual contract of one UI story | the journey mockup's review |
| Story writing | one story's page | its review |
| Structural lint | whether the graph is well formed | what the graph means |

**Product judgement**

| Concept | Owns | Never knows |
|---|---|---|
| Review | one verdict on a stage's output over all its angles | how the angles are judged |
| Angle catalog | the fixed angles of each stage, one instruction each | stages' outputs |
| Angle judge (role) | judging a set of angles on one output | the variants |
| Delegated judge | judging angles through one sub-reviewer per angle | the inline variant |
| Inline judge | judging every angle in one turn | the delegated variant |
| Gap answer | an answer to a question the contract leaves open | the human gate |
| Answer ledger | the durable, human-editable record of answers | who asked |

**Progress**

| Concept | Owns | Never knows |
|---|---|---|
| Work list | the status and laps of each item in a run | what an item means |
| Fill | adding one kind's items from the graph | the stage that drains them |
| Drain | taking a chunk, running it, settling it on return | what the target does |
| Stage target (role) | running one chunk of items to an outcome | the variants |
| State target | running a chunk as a transition into this flow's states | sub-flows |
| Flow target | running a chunk as one sub-flow call | states |
| Completion gate | whether the run finished every item | why an item stalled |

**Shared value types.** Product question, Verdict, Work item, Service name. Each part reads
them and none owns their meaning beyond the field shape.

**Read-only reference.** The Service catalog. Story split, Story mockup, Structural lint and
Readiness check consult it. Product layout alone builds it.

## 3. Invariants

| # | Invariant | Owner | Upheld by |
|---|---|---|---|
| I1 | A docs home holds at most one approved milestone. | Release selection | Milestone |
| I2 | An approved milestone passed the readiness check. | Readiness check | Release selection refuses on breach |
| I3 | A run reads and writes one docs home. | Docs home | Workspace |
| I4 | Service names are unique in a docs home. | Service catalog | Structural lint |
| I5 | A story's services name catalog services, and a story with a UI service has a mockup. | Structural lint | Story split, Story mockup |
| I6 | A story mockup agrees with its journey mockup. | Review | Story mockup |
| I7 | The contract's sections do not change during a run. | Completion gate | Amendment request |
| I8 | The work list is complete exactly when the milestone is authored. | Completion gate | Drain |
| I9 | An item settles only after its target returns. | Drain | Stage target |
| I10 | A kind is filled only after its barrier review passed. | Fill | Review |
| I11 | The docs history never pushes. | Docs history | |
| I12 | A verdict covers every angle of its stage. | Review | Angle judge |
| I13 | An answer in the ledger binds every later turn until the human edits it. | Answer ledger | Gap answer |

I7 is owned by the Completion gate because it is the one concept that sees the finished run.
It compares the contract digest taken at start with the one at the end.

## 4. Forces and patterns

### Forces

- F1. A stage's target varies: a few states of the same flow, or a whole sub-flow.
- F2. A run stops at any item and must resume without redoing settled work or skipping
  unsettled work.
- F3. The human edits the graph between runs, so a second record of what exists drifts.
- F4. Agent CLIs differ: some have a subagent tool, some do not.
- F5. Review angles grow over time, and each one is tuned on its own.
- F6. The docs location varies by launch, and it is one value for the whole run.
- F7. Each agent turn has a fixed cost, so items go in chunks.
- F8. Micromanaging agents from the engine has proved slow.
- F9. Workflows are the product, so a pattern belongs in the engine and its skill, where
  every workflow author meets it.
- F10. Every stage binds to the contract, so it must not move while a run reads it.
- F11. Repo folders differ per machine, so workspace membership is a machine fact.
- F12. Product questions repeat across stories, and the human must be able to overrule an
  answer.
- F13. A stage's output must be well formed before anyone judges its meaning.

### Between parts

- **A sequence of drains over a shared work list** (F2, F3, F7). Progress is the spine.
  Decomposition stages are targets it drains into. This re-derives claims 16 to 19.
- **One value handed along** (F6). The docs home is computed once at assembly and passed to
  every part. This re-derives claims 6 and 7.
- **A read-only catalog** (F6, F13). The Service catalog is built once and consulted.

### Inside a part

| Concept | Pattern | Force |
|---|---|---|
| Stage target | role with State target and Flow target variants. The call site picks by passing a state or a flow. | F1 |
| Drain | settle on return: an item claimed and still active when the drain state is re-entered has returned. | F2 |
| Fill | barrier that rebuilds a kind from the graph. | F3 |
| Angle judge | role with Delegated judge and Inline judge variants. The assembly picks by CLI capability. | F4, F8 |
| Angle catalog | data table, one instruction per angle. | F5 |
| Completion gate | digest at start compared at end, then a human gate listing the rest. | F10 |
| Answer ledger | append-only page bound into every judgement turn. | F12 |
| Structural lint | plain function run before Review. | F13 |
| Workspace | plain value read from the home config. | F11 |
| Docs history | plain function: init on first use, commit after each stage. | none beyond I11 |

Milestone, Decision record, Design link, Journey mockup, Release selection, Story split,
Epic writing, Story writing, Story mockup and Gap answer have no varying behaviour. They are
plain functions or plain pages.

### Claims

| Claim | Verdict |
|---|---|
| 1 | Re-derived. The restating stage carried no decision the planner had not made (problem). |
| 2, 3 | Re-derived from F6: the folder lives in the one docs home. Design links stay outside because a design outlives its release. |
| 4 | Re-derived as I1. |
| 5 | Re-derived as I2 and F13. |
| 6, 7 | Re-derived from F6. |
| 8 | Re-derived from F6: a second location setting is a second value. |
| 9 | Re-derived. A book is a service in the domain's words, and two names for one thing drift. |
| 10 | Re-derived as I4. A docs home spans repos only when names are unique. |
| 11 | Re-derived from F11. |
| 12, 13 | Re-derived from I11 and F2: a shared docs home needs history to resume from. |
| 14 | Re-derived, and narrowed by section 5: a story's services are the union of its seeds' services. |
| 15 | Re-derived. The driver is the domain's word for how a service is used. |
| 16 | Re-derived from F1, F2, F7, F9. |
| 17 | Re-derived from F3. |
| 18 | Re-derived. The order is breadth-first, the same as today (5b). |
| 19 | Re-derived as I8 and the Completion gate. |
| 20 | Re-derived. A blocked item settles `blocked` and the gate lists it. |
| 21 | Re-derived from F13: lint answers "well formed", Review answers "serves the contract". |
| 22 | Re-derived from F5. |
| 23 | Re-derived from F4 and F8. |
| 24 | Re-derived. Gap answer and Amendment request split the question by who owns the answer. |
| 25 | Re-derived from F12 as the Answer ledger. |
| 26 | Re-derived as I6. |

No claim is rejected.

### SOLID check

- **Single responsibility.** Every Owns reads without "and". Story split owns "stories and
  their services": the services are a field of each story, derived from seeds, not a second
  responsibility.
- **Open/closed.** A third stage target, or a third judge variant, adds one concept and one
  line at the call site or the assembly.
- **Liskov.** State target and Flow target are kinds of Stage target only. Delegated judge
  and Inline judge are kinds of Angle judge only.
- **Interface segregation.** Stage target declares "run these items, return". Angle judge
  declares "judge these angles on this output, return one verdict per angle".
- **Dependency inversion.** Drain never knows the variants. Review never knows the variants.

### Open lookups

- L1. Does the engine's pipeline settle rows when its handler returns a transition? Decides
  Drain's verdict.
- L2. Does any repo set `docRoots`? Decides how much migration claim 8 costs.
- L3. Where does the coder's workspace file come from today? Decides Workspace's migration.
- L4. Do seeds already carry services? Decides Story split.
- L5. Does doctor enforce required sections for any page type? Decides Readiness check.
- L6. Does any author flow hold a work list today? Decides where Work list lives.

## 5. Mapping onto the existing system

### Revision log

- R1. Section 2, Story split; claim 14. Seeds already carry a free `services:` tag
  (`ostler/ostler/model.py:28`), written by the epic author from evidence
  (`write-epic.md:36-37`). A story's services are now the union of its seeds' services.
  Structural lint checks each name against the catalog. A hand-written story list would be a
  second record of the same fact.
- R2. Section 3, I5; section 7, A3. Today's mockup rule reads seed `layers` and
  `design: required | preserve` (`story_author/nodes/mockup.py:46-55`). The design replaces
  it with "the story's services include a UI service". The `preserve` exemption goes. See A3.
- R3. Section 2, Docs home. The coder already runs with a docs repo apart from the code
  repo, through a `docs_path` parameter read on about 200 lines across the coder
  (`kit/paths.py:18-25`). The Docs home replaces that parameter. Its value is derived from
  the workspace, never passed in.
- R4. Section 2, Docs home; section 7, A10. ostler already resolves a code reference that
  names another repository through a checkout map (`ostler/ostler/doctor.py:1554-1566`).
  In a workspace run, the checkout map is the workspace's folders, so docs in the artifacts
  dir can cite code in every member.
- R5. Claim 9, narrowed. "features" names two things today: the directory that holds the
  books, and the `feature` page type, which describes one feature inside a book. Only the
  first is a service. The page type keeps its name.
- R6. Section 2, Docs home. Agent turns run `ostler` from inside a code repo, so the docs
  home must reach them without a parameter. A workspace run exports the workspace name in
  the environment, and ostler's root lookup returns the artifacts dir when it is set.

### Parts

| Part | Verdict | Where, and the mismatch |
|---|---|---|
| Release contract | Reshape | Today a single roadmap file (`author/shared/roadmap.py`) plus a milestone stage that restates it (`author/milestone/`). Becomes a folder read by ostler. |
| Product layout | Reshape | Docs location comes from `docRoots` with built-in defaults (`ostler/ostler/model.py:644-666`). Workspaces exist only in the coder, as a file. |
| Decomposition | Exists | The author sub-flows: epic_split, epic_author, story_split, story_author. Their review loops move out. |
| Product judgement | New | Three reviewers today (`review-epic-split.md`, `review-coverage.md`, `audit-story.md`) and a resolve-operator prompt. None answers product questions inside the contract. |
| Progress | Reshape | The engine has pipeline and work list (`workhorse/workhorse/pyflow/workflow.py:254-285`). Author has no work list (L6). |

### Concepts

**Release contract**

| Concept | Verdict | Where |
|---|---|---|
| Milestone | Reshape | ostler's milestone loader reads one file at `docs/milestones/*.md`. Becomes `docs/milestones/<slug>/milestone.md`. Status is a free string (`schema/milestone.schema.json:9`). It gains the enum `proposed approved authored delivered superseded`. |
| Decision record | New | `docs/milestones/<slug>/grills/<topic>.md`, plain pages ostler indexes but does not validate. |
| Design link | New | A link list in `milestone.md`. Doctor resolves each. |
| Journey mockup | New | `docs/milestones/<slug>/mockups/<journey>.html`. |
| Readiness check | Reshape | Doctor checks milestone links and cycles (`ostler/ostler/doctor.py:1242-1300`) but no sections. The required-sections mechanism exists for other types (`registry.py:170`, enforced at `doctor.py:1496-1507`). Milestone gains required sections, a mockup per UI journey, and no `Open Decisions` (L5). |
| Release selection | Reshape | `approved_roadmap` in `author/shared/roadmap.py`. Moves to ostler as a milestone query. `roadmap.py` is deleted. |
| Amendment request | Reshape | The operator gate on `_author-context.md` (`author/shared/paths.py:69-71`). Kept, raised only by Product judgement. |

**Product layout**

| Concept | Verdict | Where |
|---|---|---|
| Workspace | Reshape | The coder reads `workspace_file` from `AGENT_PARAM_WORKSPACE_FILE` (`workhorse/workhorse/supervisor.py:152-167`), never from config (L3). Becomes `workspaces:` in the home config (`core/stablemate_core/config.py`) and a `--workspace` flag on every workflow. 19 coder files read `workspace_file`. |
| Docs home | Reshape | `doc_roots()` and `BUILTIN_DOC_ROOTS` (`model.py:644-666`), read on 40 lines across 16 ostler files and one coder file. No repo sets `docRoots` (L2), so removal changes no behaviour. The coder's `docs_path` parameter is a second copy of the same value (R3). Becomes: the repo root, or `resolve_artifacts_dir()` (`config.py:432-440`) when the run's environment names a workspace (R6). ostler's root lookup (`model.py:620-628`) honours it, and the workspace folders become the checkout map (R4). |
| Service catalog | Reshape | Books under `docs/features/<book>` with a page driver. `features_root` appears on 139 lines (ostler 117, workflows 22), and base-library mentions `features` on 77 lines. Rename to `services`. In `agents.yml`, the coder's `workspace:` section becomes `services:`. |
| Docs history | New | core, beside `resolve_artifacts_dir`. Vendored into ostler, workhorse and farrier by `make vendor`. |

**Decomposition**

| Concept | Verdict | Where |
|---|---|---|
| Epic split | Reshape | `epic_split/flow.py`. Loses its review and rework loop (lines 60-103). |
| Epic writing | Exists | `epic_author`. |
| Story split | Reshape | `story_split/flow.py`. Loses its coverage review (lines 141-212). Story services derive from seeds (R1). |
| Story mockup | Reshape | `design_mockup` in `story_author/flow.py:112-126` ignores failure, and `design-mockup.md:23-24` says a missing mockup never blocks. Both reverse: a failed mockup settles the story `blocked`. |
| Story writing | Reshape | `story_author/flow.py`. Loses its audit (lines 214-265). |
| Structural lint | Exists | `validate_epic_split`, `validate_coverage`, `validate_story` and doctor. Gains I5. |

**Product judgement**

| Concept | Verdict | Where |
|---|---|---|
| Review | New | `author/pm/`, one sub-flow called after each stage's lint. Replaces the three reviewers. The audit receipt the planner and story writer read (`audit-receipt.json`) becomes the PM verdict's receipt. |
| Angle catalog | New | `author/pm/angles.py`, a table keyed by stage, with one prompt per angle under `author/pm/prompts/`. |
| Angle judge | New | The PM prompt receives the angles and the judge mode. |
| Delegated judge | New | PM prompt variant that tells the agent to spawn one subagent per angle. |
| Inline judge | New | PM prompt variant that judges every angle in one turn. The assembly picks by the agent CLI profile. |
| Gap answer | Reshape | Replaces `shared/prompts/resolve-operator.md` and the resolve loops in each sub-flow. |
| Answer ledger | New | `docs/milestones/<slug>/grills/pm.md`. |

**Progress**

| Concept | Verdict | Where |
|---|---|---|
| Work list | Reshape | The engine's `WorkList`. Author gains one per run, like the coder's (`coder/shared/work.py:47-59`). |
| Fill | New | A barrier node per stage that files items of a kind from the ostler graph. |
| Drain | Reshape | `Workflow.pipeline`. Today a handler returning a transition leaves its rows active, and the next claim re-takes them first (`workflow.py:279-285`, `worklist.py:118-152`) (L1). Becomes: on re-entry, settle the rows this state claimed before claiming more. |
| Stage target | Reshape | `pipeline` takes a `handler` callable. Becomes `to=`. |
| State target | New | `to=<state>`: the drain returns `Continue` into that state, and the state's chain ends by re-entering the drain. |
| Flow target | New | `to=<Workflow>`: the drain calls `handoff`, which returns synchronously (`engine.py:413-434`), and settles at once. |
| Completion gate | Reshape | `author/finalize/flow.py` with `mark_roadmap_authored` (`finalize/nodes/roadmap.py:42-67`). Becomes "mark milestone authored", guarded by work-list completeness and the contract digest. |

### What the existing system has that the design lacks

- **Rework caps** (`MAX_REWORKS=3`, `MAX_AUDIT_REWORKS=1`). A concept the design missed:
  Review's verdict must bound how often one item reworks. It becomes the work list's `laps`,
  which `claim` already counts. Drain blocks an item past a lap cap. No new concept.
- **Resolve caps** (`MAX_RESOLVES=2`). Waste. Gap answer replaces the resolve loop.
- **operator_mode human/auto** (`story_author/flow.py:307-308`). Waste for product
  questions, which the PM now answers. Kept for Amendment request and the Completion gate.
- **The milestone stage** (`author/milestone/`). Waste: claim 1.
- **Per-scope context gates** (`<epic_dir>/context.md`, `<story_dir>/context.md`). Waste
  for the PM's questions. The run-level gate remains.

### Claims against the existing system

Claims 1 to 15 and 21 to 26: the existing system follows none of them, and the design
follows all. Claims 16 and 17: the engine has `pipeline` and `WorkList`, but `pipeline` takes
a handler and leaves transitioned rows active, so it follows claim 16 only in part. Claim 18:
the existing order is the same breadth-first order. Claim 19: Finalize marks authored on
artifact validity, not on work-list completeness. Claim 20: the existing system never blocks
on a mockup.

## 5b. What must not move

Measured on `acme`'s milestone, the one authored release, on 2026-10-22.

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| The coder | every story carries an audit receipt it can trust | `audit-receipt.json` readers in the planner and story writer | 38 of 38 stories audited | 38 of 38 carry a PM receipt after migration |
| The coder's developer | a mockup for each story that changes a screen | nothing | 34 of 38 stories have a mockup | 100% of stories with a UI service have one, and none lost |
| The coder | stories ordered epic by epic in coding order | the epic order in the milestone | 7 epics, breadth-first | same 7 epics, same order |
| The planner | product questions answered without waiting | the resolve-operator loop in auto mode | answered by the resolve agent | answered by the PM, logged in the ledger |
| `acme`'s books and QA | books at `docs/features/<book>` | ostler path resolution | every book resolves | every book resolves at `docs/services/<book>`, and doctor passes |
| The coder in `acme` | service roots and markers from `agents.yml` `workspace:` | `farrier doctor` warns when empty | read on 4 coder paths | the same values read from `services:` |
| Multi-repo coder runs | one launch over several repos | `checkout_workspace` | launched with a `.code-workspace` file | launched with `--workspace <name>`, same members |
| The planner's budget | an Author run's cost and time | nothing | not measured (A2) | within 1.5 times today's |

The mockup row is enforced by nothing today. The design keeps it on purpose as I5.

## 6. Slices

Each slice lands on its own and re-measures every 5b row on `acme`'s milestone.

1. **One docs home.** Product layout: Workspace, Docs home, Service catalog rename, Docs
   history. The coder migrates to `--workspace`. Done when: stablemate, `acme` and `globex`
   doctor pass under `docs/services`. A coder dry run with `--workspace` resolves the same
   members as its `.code-workspace` file. `docRoots` and `features` appear nowhere outside
   history. 5b rows for books, `services:` and multi-repo hold. The rest are unchanged
   because Author is untouched.
2. **The release folder.** Release contract: Milestone, Decision record, Design link,
   Journey mockup, Readiness check, Release selection. The milestone skill. Author starts at
   the epic split from the folder. `acme` migrates by hand. Done when: `acme`'s folder passes
   the readiness check. An Author dry run selects it. Removing one journey mockup fails
   doctor. All 5b rows hold, because the stages behind intake are unchanged.
3. **Drains.** Progress: Work list, Fill, Drain, Stage target with both variants, Completion
   gate. The engine skill documents the pattern. Author's stages become drains. Done when:
   a run stopped at a random item resumes and ends with every item done and none run twice
   on a settled item. A run with one blocked item ends at a gate naming it. Stage order is
   unchanged in 5b. Cost is within budget (A2).
4. **The PM.** Product judgement, Story mockup made blocking, story services from seeds.
   Done when: the three reviewers and resolve loops are gone. Every `acme` story has a PM
   receipt, and every story with a UI service has an agreeing mockup. Questions inside the
   contract never reach the human, and every answer is in the ledger. All 5b rows hold.

Slice 1 is the thinnest path to an observable outcome for the multi-repo planner. Slice 2 is
the thinnest path for the single-repo planner.

## 7. Assumptions

Ordered by the cost of being wrong.

**A1.** The PM, given the contract, the ledger and the books, answers most product questions
without the human.
- Decided: Gap answer replaces the resolve loop, and the human sees only Amendment requests.
- Basis: none. No real Author run is in groom, so no question count exists.
- If wrong: Gap answer, Amendment request, the planner's 5b row.

**A2.** One PM turn per review costs about what today's reviewer turns cost.
- Decided: Review runs once per stage output, with sub-reviewers per angle.
- Basis: none. Author cost and time were never measured on a real run.
- If wrong: Angle judge's variant choice, the budget row in 5b, slice 4's done-when.

**A3.** A story whose services include a web or mobile service changes what that service
shows.
- Decided: I5 requires a mockup for every such story, and `design: preserve` goes (R2).
- Basis: the grill's "for UI service mockup will be mandated". The 4 `acme` stories without
  a mockup were not checked against it.
- If wrong: I5 regains a preserve exemption, owned by Structural lint.

**A4.** A drain state re-entered within the same run means its target returned.
- Decided: Drain settles its claimed rows on re-entry (I9).
- Basis: a resume re-enters the checkpointed state inside the target, not the drain
  (`driver.py:119-165`). A fresh run gets a fresh work list.
- If wrong: Drain needs an explicit return marker from the target.

**A5.** Seed `services:` tags can be rewritten as catalog book names.
- Decided: story services are the union of seed services (R1).
- Basis: the epic prompt fills them "from evidence" with no fixed vocabulary
  (`write-epic.md:36-37`).
- If wrong: Story split writes the list itself, and lint checks it against the seeds.

**A6.** The agent CLI profile says whether a subagent tool exists.
- Decided: the assembly picks Delegated or Inline judge from the profile.
- Basis: none checked.
- If wrong: the profile gains a flag, or the PM prompt asks the agent to detect it.

**A7.** No repo outside stablemate, `acme` and `globex` uses `docs/features` or `docRoots`.
- Decided: the rename and removal ship with no compatibility reading.
- Basis: no repo sets `docRoots` (L2). The paddock fixtures are in this tree.
- If wrong: doctor's failure message names the move, and the user runs `git mv`.

**A8.** The planner pushes the docs history by hand when they want a backup.
- Decided: Docs history never pushes (I11).
- Basis: the grill.
- If wrong: Docs history gains an opt-in remote.

**A10.** In a workspace, every code reference in a book names its repository.
- Decided: ostler resolves workspace references through the checkout map (R4), with no
  mapping from book name to repo.
- Basis: repository-qualified references already exist (`doctor.py:1555`). No book in a
  workspace exists yet.
- If wrong: Service catalog gains a book-to-repo map.

**A9.** The structure of the author package stays for this change.
- Decided: sub-flows keep their folders, and the PM is a new sibling.
- Basis: the mapping found no structural fault beyond this problem.
- If wrong: `target-architecture` owns the move.
