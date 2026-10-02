# Book pages that fit one turn

Disclosure: I wrote this after many hours inside the existing system. I had read the book
checker, the book workflow's repair loop and the client book itself. Sections 1 to 4 use
only the problem and measurements of the books. Design decisions that reached me from that
context are listed as claims in 1b, and each part was tested against "would I have named
this without having seen the solution?". Sections 1 to 4 were revised after section 5's
lookups and after the user's pushback. The revision log at the top of section 5 lists each
change.

## 1. Problem

A person waiting on a book watches the run stall for hours. The API book sat near 1,250
failing checks for four laps. Almost all of them live on one 10,755-line page that
documents the whole API. A repair turn is handed only its failing sections. To check its
fix, though, it runs the whole page: about 2,500 checks, 1,346 of them failing, of which it
sees 20 lines. It cannot tell whether its own sections now pass, so its fixes land blind and
the count oscillates. A person reading the book meets the same wall: one page holds a whole
API, and a change to it is a diff nobody can review.

Done looks like this:

- Each endpoint of an HTTP surface is its own page, beside its server page, and the server
  page keeps the launch, the overview and an inventory of links (revised, R6).
- A writer writes a new endpoint as its own page from the start.
- No page in any book is larger than 64 KiB (A4). Today 11 of 789 pages are, the largest
  at 756 KiB.
- An existing book is brought to that shape by one command, with every link and every
  claim still in place.
- A page of any other kind that a writer grows past the limit is brought back under it
  before the next lap, with no agent doing the cutting.
- A repair turn's check runs only the claims of the pages it repaired, and prints only
  their failures. For an HTTP book that is the endpoints it repaired.
- The API book's failing count falls lap over lap again, instead of oscillating.

Out of scope:

- The app's own server errors and missing secrets. They are a person's problem.
- Fixtures that sign in as the wrong user.
- Shorter claim grammar, such as naming a request body once instead of repeating nine
  fields three times. That would shrink pages but changes the language.
- Choosing which model runs a turn.
- Pages of fewer than 64 KiB whose cited source still overflows a turn. The section-scoped
  repair that exists today keeps serving them.

### Measurements

| Fact | Value |
|---|---|
| Largest page | 756 KiB, about 190,000 tokens, one API server page |
| Its outline | a 14 KiB overview, then `## Endpoints` (140 subsections) and `## Invocations` (89 subsections) |
| Its subsections | median 3 KiB, largest 27 KiB |
| Its invocations | 88 of 89 name exactly one endpoint on the page as their target. One names none |
| Its failing checks | 1,346, spread over 156 subsections; the 20 worst hold 38% |
| Its route families | 10, the largest about 200 KiB |
| Links into it | 597 anchored links from 121 other pages |
| Commented-out text on it | 9 comments, 67 KiB, 9% of the page; at least one hides a failing claim |
| Server pages, four books | 7, from 4 KiB to 756 KiB; 2 over 64 KiB |
| Pages over 64 KiB, four books | 11 of 789: 2 server pages, 9 concept, screen and feature pages |
| Largest `###` subsection, those 11 pages | 37 KiB |
| What the 9 other pages hold | methods (158 on one page), components (35), interactions (25), fields, and embedded `format:` and `concept:` sections (45 formats on one page) |

Every oversized page has a dense heading outline: 47 to 223 `###` subsections each.

## 1b. Claims

1. "Such big page must be split." (the user)
2. "We need a mechanism to either split page or make them smaller." (the user)
3. A repair turn on an oversized page gets one section's failures at a time. (my earlier
   recommendation to the user)
4. "Coherent families are expanded into typed endpoint and invocation nodes by the
   server-surface crawl." (the API page's own text: endpoints are sections of one server
   page)
5. A repair turn batches up to five files from sibling folders. (my session memory)
6. A section that lives on one page type appears on no other. (the checker's module map)
7. The API page splits along its route families. (the inventory's ten bold group headings)
8. "We should make an endpoint page in okf. Probably a fragment page too." (the user)
9. "The api page is conceptually specific." (the user, rejecting one generic fragment
   page for every kind)

## 2. Parts and concepts

### Level 1: parts

1. **Page kinds** owns which kinds of page a book holds and how pages of related kinds
   point at each other: an endpoint at its server, a fragment at its host (added, R6). It
   never knows sizes or how a page was cut. It hands its catalog to every other part and to
   the writers.
2. **Measuring** owns the size limit and the size of a page. It never knows how a page is
   cut. It hands a verdict, over or under, to Guarding.
3. **Dividing** owns which parts of a page leave it, and as what. An endpoint always
   leaves as an endpoint page. Whatever remains on an oversized page leaves as fragments.
   It produces a plan and never touches a file or a link. It hands the plan to Relocating.
4. **Relocating** owns carrying a plan out so the book reads the same afterwards. It
   writes the new pages and the slimmed parent, and moves every address that pointed into a
   moved section. It never knows why the cut was chosen.
5. **Guarding** owns the moment a page must be back in shape, and the rule against hidden
   claims. It asks Page kinds and Measuring at each book check, and sends a page out of
   shape through Dividing and Relocating. It never knows how a cut is made.

Flow:

- A writer writes each endpoint as its own page, because Page kinds has no other place for
  one.
- At a book check, which ends every writer and repair turn, Guarding asks about each page.
  A server page that still holds an endpoint, or any page over the limit, goes to
  Dividing, then the plan goes to Relocating. The book is checked again afterwards.
- On an existing book, a person or the operator runs the same sequence once by command.
- Commented-out claims are reported by Guarding as a book problem for the writer.

In plain words: an API is a set of doors, and each door gets its own page, with the notes
on who knocks at it. The building's page keeps the address, the opening hours and a list
of its doors. Other long pages, such as a page about a storage layer with 158 methods, have
no doors. Their chapters cannot stand alone, so a too-long one is continued on fragment
pages that say whose continuation they are. A ruler says which pages are too long, a
planner decides what leaves, a mover makes the pages and fixes every cross-reference, and a
gatekeeper runs all of this after each piece of writing.

### Level 2: concepts

**Page kinds** (added, R6)

| Concept | Owns | Never knows |
|---|---|---|
| Kind catalog | the kinds of page, the folder each lives in, and the sections each must carry | sizes |
| Endpoint page | one endpoint's address and claims, and the invocations that target it | the other endpoints |
| Server membership | an endpoint page's link to its one server, and the server inventory's link back | the endpoint's claims |
| Fragment page | more sections of one host page, under the host's rules | why the host overflowed |
| Host link | a fragment's link to its one host, and the host's link to each fragment | the fragment's sections |

**Measuring**

| Concept | Owns | Never knows |
|---|---|---|
| Size limit | the largest page a turn may be given, one number for every book | which model runs the turn |
| Page size | the byte size of one page | the limit |

**Dividing**

| Concept | Owns | Never knows |
|---|---|---|
| Outline | a page's headings as a tree, each with the text it spans | what a section means |
| Promotion | picking each section that is a page kind in its own right, together with the sections whose target it is (added, R6) | the size limit |
| Unit | a group of the remaining subsections that link to each other, so they leave together when one fragment holds them (revised, R2, R7) | the size limit |
| Fragment cut | packing the units of an oversized page, in order, into fragments under the limit (revised, R6) | files, links |
| Division plan | every page to write, each addressed by its kind's folder and its name, plus what the parent keeps (revised, R5, R6) | how the plan is written to disk |

**Relocating**

| Concept | Owns | Never knows |
|---|---|---|
| New page | the text of one new page: its kind's header, its link to the parent, the moved text (revised, R6) | the other new pages |
| Slimmed parent | the parent's text: its overview, each section's own introduction, and a link to each new page in place of what left | the new pages' bodies |
| Address map | old address to new address for every moved anchor | how a link is spelled in a page |
| Reference rewrite | rewriting every link in the book through the address map | why anything moved |
| Carve receipt | comparing the book before and after: claims conserved, every link resolving | how the plan was chosen |

**Guarding**

| Concept | Owns | Never knows |
|---|---|---|
| Shape finding | a page out of shape, over the limit or holding an endpoint inline, reported as a book problem with a deterministic fix (revised, R6) | how the fix cuts |
| Hidden-claim finding | a claim written inside a comment, reported as a book problem for the writer | the size limit |

**Shared values.**

- A page's address is its kind's folder and its name. An endpoint page is named after the
  endpoint, such as `get-invoice`, and sits in the folder of server pages beside its
  server. A fragment is named after its host and the section it continues, such as
  `storage-layer-methods`, and sits beside its host. When one section needs several
  fragments, each also carries the anchor of the first unit it holds (A11). No folder is
  created for a carve (R5, R6).
- A unit whose heading declares a page kind, such as `format: Invoice row`, leaves as a
  page of that kind in that kind's folder, not as a fragment (R5).

## 3. Invariants

1. **A carve conserves the book's claims.** The same claims, with the same text, exist
   before and after. Only their addresses change. Owner: Carve receipt. Upheld by New page
   and Slimmed parent.
2. **A carve leaves no dangling link.** Every link that resolved before resolves after.
   Owner: Carve receipt. Upheld by Address map and Reference rewrite.
3. **At the end of a turn every page fits the limit and no endpoint is written inline.**
   Owner: Shape finding (revised, R6).
4. **A cut never splits inside a subsection.** A unit one fragment holds leaves whole. A
   larger unit leaves subsection by subsection, and its links and check locators follow
   each subsection to its fragment. When one subsection alone exceeds the limit, the plan
   reports that page instead of cutting text. Owner: Division plan (revised, R7).
5. **A carve of a page in shape changes nothing.** Owner: Division plan.
6. **A new page sits in its kind's folder, under a name no other page there holds, and
   passes its kind's required sections.** Owner: Division plan, which assigns each
   address and refuses the carve on a name already taken (revised, R5).
7. **Every endpoint page names exactly one server page, and that server's inventory links
   it.** An endpoint page never names another endpoint page as its server. Owner: Server
   membership (added, R6).
8. **A fragment names exactly one host, its host is not itself a fragment, and it carries
   only sections its host's kind may carry.** Owner: Host link (added, R6).

## 4. Forces and patterns

### Forces

- **F1. Many references move together.** 597 links from 121 pages point into the one
  page. They must all follow, all at once. No agent can be trusted with that edit.
- **F2. Writers keep growing pages during a run.** A page cut once grows again when the
  next writer adds an endpoint the way it always has.
- **F3. The limit tracks the smallest turn window**, which changes when models change.
- **F4. The cut must be testable without a real book.** A plan from text alone, applied
  to a temporary tree.
- **F5. Running books exist.** The API book is mid-run, so the carve must work on a
  finished book at a resume point, not only at write time.
- **F6. Some sections stand alone and some do not** (revised, R6). An endpoint has its own
  address, a client calls it alone, and a test exercises it alone. 88 of 89 invocations
  name exactly one endpoint, so its callers travel with it. A method, a component or an
  interaction exists only inside its host: it shares the host's code, its screen or its
  type.
- **F7. A check runs per page** (added, R1). The proof that a fix works is the page's
  whole run, so a page's size sets the cost and the noise of every check on it.

### Between parts

**A catalog every part reads** (F6). Page kinds is data, consulted by the writers, by
Dividing to decide what is promoted, by Relocating to write a new page's header, and by
Guarding to check a page's shape.

**A plan value handed along** (F1, F4). Dividing returns a plan as a plain value.
Relocating applies it. The plan can be printed for a dry run and asserted in a test with
no disk.

**One trigger at the book check** (F2, F5). Guarding runs at the check that already ends
every turn, and the same sequence is a command for an existing book.

### Inside a part

- **Endpoint page** and **Fragment page**: two entries in the kind catalog, not code
  (F6). Endpoint is a kind because it stands alone. Fragment is a kind because the other
  sections do not, and a fragment page borrows its host's rules instead of declaring its
  own.
- **Server membership** and **Host link**: a link bullet on the child, checked against the
  parent's inventory. A link is what the checker already resolves, so a folder convention
  is not needed (F1).
- **Size limit**: a configured number (F3). Plain value.
- **Promotion**: a plain function. It takes each section whose type the catalog lists as a
  page kind, plus every section whose target link names it (F6). It runs whatever the
  page's size, because an inline endpoint is out of shape at any size.
- **Unit**: the connected groups of same-page links among the remaining subsections
  (revised, R2). A group past what one fragment holds splits back into its subsections
  (revised, R7).
- **Fragment cut**: a plain function over the outline and its units. It keeps whole `##`
  sections together when they fit, and otherwise packs that section's units in order.
  Promotion and the cut run in sequence on the same page, so neither is a variant of the
  other, and there is no role.
- **Address map** and **Reference rewrite**: a table built once, then applied to every
  page in one pass (F1).
- **Carve receipt**: a before-and-after comparison that refuses and restores the tree on
  a breach (F1).
- **Shape finding**: a book problem whose fix is the carve, so no agent cuts by hand
  (F2).
- **Hidden-claim finding**: a book problem without an automatic fix. The commented-out
  400 check on the signup endpoint shows a writer hiding a failure, so deleting the
  comment silently would erase evidence. The writer restores the claim or deletes it.

### Claims

1. Re-derived from F1, F2 and F7: split, deterministically.
2. Both halves kept. Splitting carries the size. Trimming commented-out claims is 9% at
   most, so it becomes the hidden-claim finding instead of a size mechanism.
3. Rejected (revised, R1). The workflow already does this, and the API book stalled
   under it. F7 is why: the turn's check still runs the whole page.
4. Rejected (revised, R6). An endpoint is a page, not a section of its server.
5. Rejected (revised, R4). Repair batches are packed by token cost today, not five
   siblings at a time. New pages need no batching change.
6. Reshaped (revised, R6). An endpoint no longer is a section. A fragment's sections are
   judged against its host's kind, so a server's fragment may hold what a server may hold.
7. Rejected. The largest family is about 200 KiB, three times the limit, and an endpoint
   page needs no family.
8. Re-derived from F6 and F7: an endpoint page because an endpoint stands alone, and a
   fragment page because the other sections do not.
9. Re-derived from F6. The API page is the one case where the overflowing sections are
   domain things with their own address.

### Open lookups

- **L1.** Does the checker or the workflow already measure page size or cap what a turn
  reads? Decides whether Size limit and Shape finding are new.
- **L2.** Which page kinds may host endpoint and invocation sections, and is there any
  notion of a page that continues another? Decides the work in Page kinds.
- **L3.** How a claim's address is built, and whether a command already moves a section
  and rewrites links. Decides whether Address map and Reference rewrite are new.
- **L4.** Where writers learn where an endpoint goes. Decides whether the catalog alone
  holds F2.
- **L5.** How a repair turn is scoped and batched. Decides whether new pages need any
  change to batching.
- **L6.** Whether the QA plan has one scenario per page, and how an endpoint finds its
  server's address. Decides whether endpoint pages need QA changes.
- **L7.** Whether claims inside comments are parsed, stripped or flagged. Decides the
  Hidden-claim finding.

## 5. Mapping onto the existing system

### Revision log

- **R1.** Section 1 and F7, claim 3. The workflow already sends an oversized page's
  failing sections alone (`workflows/src/workhorse_workflows/okf_book/main/nodes/repair_batches.py:80-106`).
  The turn's check is still the whole page, though. `exercise` runs every scenario on the
  named pages and knows no sections (`main/nodes/exercise.py:44`), and the writer sees 20
  lines of its output (`main/nodes/writer_commands.py:22-28`). The stall comes from the
  check, not from reading the page.
- **R2.** Unit added to Dividing. Endpoints must sit on server pages and invocations may
  sit anywhere (`ostler/ostler/registry.py:612, 664`). Cutting every `###` alone would
  leave invocation-only server pages.
- **R3.** Shared reference added: the page-kind catalog. Superseded by R6, which makes it
  a part.
- **R4.** Claim 5 rejected. Batches are packed by token cost
  (`main/nodes/repair_batches.py:109-128`). My memory of a five-sibling cap is stale.
- **R5.** Shared values, Division plan and invariant 6 changed. The user rejected a folder
  named after each carved page. The books already sort pages into one folder per kind, and
  the registry names that folder per type (`ostler/ostler/registry.py:478` for server
  pages, `:508` for formats). A new page joins its kind's folder.
- **R6.** Part 1 Page kinds added, with Endpoint page, Server membership, Fragment page
  and Host link. Promotion added to Dividing and Fragment cut replaces Cut. Child page
  became New page, Oversize finding became Shape finding, F6 rewritten, invariants 3, 7
  and 8, claims 4, 6, 8 and 9. The user named an endpoint page and a fragment page, and
  then held that the API page is conceptually specific. The measurement behind it: 88 of
  89 invocations name exactly one endpoint, so an endpoint and its callers stand alone,
  while methods and components on the other pages do not.
- **R7.** Unit, invariant 4 and assumption 4. Two client pages link their subsections
  into runs no fragment holds: a query section of 46 subsections in one 78 KiB run, and a
  components section of 35 subsections in one 144 KiB run. Keeping a unit whole refused
  both pages, so a unit past the limit now splits along its subsections. The same carve
  showed that a check's locator points into the book the way a link does, so the carve
  rewrites and checks both. It also showed that a component on a screen's fragment
  navigates from that screen.

### Lookups resolved

- **L1.** Nothing measures a page. The checker limits one bullet to 700 characters
  (`ostler/ostler/doctor.py:1771`). The workflow has a 180,000-token turn budget
  (`main/nodes/turn_budget.py:26`) and blocks with "split the page/section" when one
  section still overflows it (`main/nodes/repair_batch_models.py:61-88`).
- **L2.** Endpoint is a section type hosted only by server pages (`registry.py:612`,
  enforced at `ostler/ostler/section_hosts.py:9-26`). Invocation has no host restriction
  and a required `on:` link (`registry.py:664-667`). A server page requires a filled
  `## Endpoints` (`registry.py:478-479`). A book may hold several server pages, and the
  run's launcher is the first by id with a `launch:` bullet
  (`ostler/ostler/qa/runbook.py:320-324`). No page continues another.
- **L3.** A node's id is `<page path>#<anchor>` (`ostler/ostler/model.py:966`), with
  anchors made unique per file (`model.py:913-929`). Every claim id, verdict and cached
  review carries the page path. `ostler edit migrate-context` moves whole pages and
  rewrites the links to them, keeping anchors (`ostler/ostler/edit.py:122-204`). Nothing
  moves one section.
- **L4.** No crawl exists. One writer turn writes the whole book, and the HTTP branch of
  the prompt asks for "every endpoint with its method and path" with no file per endpoint
  (`main/prompts/write-book.md:38-39`). The writer chose one page. The prompt does not
  render the registry, so the catalog alone does not reach the writer.
- **L5.** See R1 and R4.
- **L6.** One HTTP scenario per book page (`ostler/ostler/qa/compile_http.py:102-130`,
  grouped by `by_source` in `qa/plan_source.py:188-192`). The base URL comes from the
  obligation's surface (`compile_http.py:124-126`), and the surface is the feature folder
  the page sits under (`qa/context.py:448`). An endpoint page beside its server keeps the
  same surface, so it needs no QA change and gets its own scenario. Claims on one page run
  in order in one working directory (`write-book.md:90-91`), so a claim that relied on an
  earlier endpoint's side effect may fail after the move (A2).
- **L7.** The checker's parser treats a comment block as opaque, so commented claims are
  invisible to it (`ostler/ostler/markdown.py:19`). The workflow's section regex reads
  inside comments (`main/nodes/page_sections.py:16-17`). The checker also writes comments
  itself (`ostler/ostler/templates.py:128-129`, `ostler/ostler/qa/fixtures.py:198`).

### Parts

- **Page kinds: reshape** of the registry (`ostler/ostler/registry.py`). Endpoint moves
  from a section type to a file type in the server folder `http`, with a required
  `server:` link. Fragment is new. The mismatch is the folder: the registry gives each
  file type one fixed folder (`context`, `registry.py:478`), and a fragment's folder is its
  host's. The fragment type takes its folder from its `host:` link instead.
- **Measuring: new**, in the checker, beside the bullet length limit in `doctor.py`. The
  limit is a book rule, so the checker owns it and the workflow trusts it.
- **Dividing: new**, as one checker module for the outline, promotion, units, fragment cut
  and plan. It reads headings from the checker's own parser, not a line regex, so a
  heading inside a comment never starts a section.
- **Relocating: reshape** of `edit migrate-context`. That command owns moving pages and
  rewriting links to them. The carve needs the same rewrite keyed by anchor, not by page.
  The mismatch is the key: `migrate-context` maps page to page (`edit.py:122-204`), and
  the carve maps page and anchor to a new page and anchor. The rewrite generalizes to an
  anchor map, and `migrate-context` becomes one caller of it.
- **Guarding: new finding, existing moment.** The workflow already stops at an oversized
  section (`repair_batch_models.py:61-88`). That moment becomes: carve the page, then
  repack. The blocker remains only for a single unit over the limit (invariant 4). The
  writer prompt's HTTP branch names one page per endpoint, because the prompt does not
  render the catalog (L4).

### Concepts

| Concept | Verdict | Where |
|---|---|---|
| Kind catalog | exists | `registry.py`, the `UINodeType` entries |
| Endpoint page | reshape | `registry.py:612`, from `kind="section"` hosted by server to `kind="file"` in `http` |
| Server membership | new | a `server:` link bullet on the endpoint type, checked in `doctor.py` against the server's `## Endpoints` |
| Fragment page | new | a `fragment` file type in `registry.py` |
| Host link | new | a `host:` link bullet, checked in `doctor.py`. `section_hosts.py:14` judges a fragment by its host's type (claim 6) |
| Size limit | new | `doctor.py`, next to the bullet limit |
| Page size | new | the same |
| Outline | exists | the checker's sections from its markdown parser (`markdown.py:546`) |
| Promotion | new | the carve module |
| Unit | new | the carve module |
| Fragment cut | new | the carve module |
| Division plan | new | the carve module, a plain value |
| New page | new | the carve module |
| Slimmed parent | new | the carve module |
| Address map | reshape | `edit.py`, generalized from page moves to anchor moves |
| Reference rewrite | reshape | `edit.py`, the link rewrite `migrate-context` already does |
| Carve receipt | new | the carve module, reusing the checker's link resolution (`ostler/ostler/links.py:46-55`) |
| Shape finding | new | `doctor.py` |
| Hidden-claim finding | new | `doctor.py`, firing only on a comment that holds a claim bullet, so the checker's own markers stay quiet |

### What the existing system has that the design lacks

- **Section-scoped repair** (`repair_batches.py:80-106`). Not waste. It still serves a
  page under the limit whose cited sources overflow a turn, which section 1 leaves out of
  scope.
- **The turn budget** (`turn_budget.py`). Not waste. It sizes a turn, while the size limit
  sizes a page. The two stay separate, and the page limit stays well under the budget.
- **Cached reviews and verdicts keyed by page path.** A concept the design chose not to
  carry (A3).
- **The misplaced-section finding** (`section_hosts.py:9-26`). Not waste. It keeps an
  endpoint section off a screen page today. Once endpoint is a page kind, the Shape finding
  takes over for endpoints, and the misplaced-section finding keeps serving the other
  section types.

## 6. Slices

1. **Endpoint pages for the API book.** Endpoint page and Server membership in the
   catalog, Promotion, and Relocating, run by hand on the API book at a resume point.
   Done when: the API server page is under 64 KiB and lists 140 endpoint pages, each
   endpoint page holds its endpoint and the invocations that target it, the receipt shows
   every claim conserved, the checker reports no new link problem, the QA plan has one
   scenario per endpoint page, and the next two laps each end with fewer failing checks
   than the lap before the move.
2. **Writers write endpoint pages.** The writer prompt's HTTP branch, and the Shape
   finding for an endpoint written inline, carved at the book check. Then the command on
   the other six server pages. Done when: a test book's writer turn produces one page per
   endpoint, an inline endpoint is moved before the next lap with no operator gate, and no
   server page in the four books holds an endpoint inline.
3. **Fragments at the book check.** Fragment page and Host link in the catalog, Unit,
   Fragment cut, and the Shape finding for size, with the workflow carving instead of
   blocking. Done when: a test book whose writer grows a concept page past the limit gets
   fragments before the next lap, with no operator gate.
4. **Hidden claims.** The hidden-claim finding. Done when: the 9 comments on the API page
   are reported, and the checker's own comments are not.
5. **The other oversized pages.** Carve the 9 remaining pages, each at its book's resume
   point. Done when: no page in the four books exceeds 64 KiB.

## 7. Assumptions

1. **Assumption**: moving endpoints to their own pages lets the failing count fall again.
   **Decided**: slice 1 moves the API book's endpoints first and measures before any other
   slice.
   **Basis**: R1. The check a turn runs is the whole page, and the turn sees 20 lines of
   1,346 failures. After the move a repaired endpoint's check runs about 10 claims. The
   causal link is not measured.
   **If wrong**: section 1's last outcome, and slice order. The next suspect is the
   page's shared working directory (A2).
2. **Assumption**: few claims depend on side effects left by another endpoint on the same
   page.
   **Decided**: each endpoint page is its own scenario, with no state carried between
   them.
   **Basis**: the page's claims arrange their state through fixtures, as the signup
   endpoint does. Not counted.
   **If wrong**: slice 1's lap count rises, and those claims need an `arrange:` or
   `fixture:` of their own. The fix is in the book, not in Promotion.
3. **Assumption**: every server page moves its endpoints out, the small ones too.
   **Decided**: one shape for every HTTP book. Endpoint is a page kind and never a
   section.
   **Basis**: one shape is one rule for writers, the checker and the QA plan, and claim 9.
   The smallest server page holds 4 endpoints in 4 KiB, so it gains 4 short pages.
   **If wrong**: Endpoint page allows both forms, Promotion runs only on an oversized
   server page, and invariant 3 drops its endpoint clause.
4. **Assumption**: 64 KiB is small enough for any turn and large enough for every
   subsection (revised, R7).
   **Decided**: Size limit is 64 KiB.
   **Basis**: 64 KiB is about 32,000 tokens at the workflow's own costing (twice the page
   at 4 bytes a token), under a fifth of its 180,000-token turn. The largest subsection
   on an oversized page is 36 KiB. The largest endpoint with its invocations is under
   that. Linked units are not bounded: two reach 78 and 144 KiB (R7).
   **If wrong**: Size limit, Fragment cut, invariant 4.
5. **Assumption**: one re-run of moved claims is acceptable.
   **Decided**: no carried verdicts. Claims whose address changed run again.
   **Basis**: the move runs once per page, and a lap already runs every check.
   **If wrong**: add a concept that moves cached verdicts through the address map.
6. **Assumption**: an endpoint page beside its server keeps the server's address in QA.
   **Decided**: no QA change. The `server:` link serves readers and the checker.
   **Basis**: the base URL comes from the feature folder (L6).
   **If wrong**: the QA plan resolves an endpoint's base URL through its `server:` link,
   which matters for a feature with two servers, as one book has.
7. **Assumption**: one link-and-heading rule fragments every non-server page well.
   **Decided**: no per-kind fragment rule.
   **Basis**: the 9 measured pages all fit at `###` or above.
   **If wrong**: Fragment cut becomes a role with per-kind variants, and the catalog
   chooses.
8. **Assumption**: a typed section moved to its own page is a valid page of that kind.
   **Decided**: `format:` and `concept:` sections leave for the formats and concepts
   folders, not as fragments.
   **Basis**: those folders already hold 129 and 182 pages of the same kinds. The heading
   levels shift up by one when a section becomes a page. The checker's rules for that are
   unread.
   **If wrong**: typed sections leave as fragments of their host.
9. **Assumption**: an endpoint's anchor names a page uniquely in the server folder.
   **Decided**: the endpoint page takes the endpoint's anchor as its name, and a name
   already taken refuses the carve instead of inventing a suffix.
   **Basis**: across the 11 oversized pages, 0 of about 1,100 candidate names match a page
   already in the target folder.
   **If wrong**: Division plan prefixes the server's name on a collision.
10. **Assumption**: about 140 endpoint pages in one folder stay navigable.
    **Decided**: no subfolders by route family.
    **Basis**: the server page keeps the inventory, grouped by family, with a link to each
    endpoint page. Batches are packed by cost, not by folder (R4).
    **If wrong**: Division plan places endpoint pages in family folders named by the
    inventory's family headings.
11. **Assumption**: a fragment named after its host and section reads well enough.
    **Decided**: `storage-layer-methods`, plus the first unit's anchor when a section
    needs several fragments.
    **Basis**: none. The user asked for relevant names and no generic folders.
    **If wrong**: Division plan's naming only.
