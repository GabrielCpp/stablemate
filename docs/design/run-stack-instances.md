# Run stack instances

**Disclosure.** I wrote this note after reading the existing solution. I had read the
runbook node type and its stack selection, the coder workflow's story branching, its pull
request step and its teardown, the QA plan contract, and one client's Compose file,
environment page and Makefile. The design decisions they carried are claims in section 1b.
I checked each part and concept below against the question "would I have named this without
having seen the solution?" The checks that failed are named where they occur. This note
extends [QA across environments](qa-across-environments.md) and reuses its parts by name.

## 1. Problem

A developer starts two agent runs on one machine against one client repository: a book run
that has been testing the web app for days, and a coder run that implements a story. Today
both runs drive the same local stack. The coder's build replaces the containers the book run
is testing, and the coder's teardown stops them at the end of its story. If the developer
gives the coder a separate stack instead, its journeys still open the fixed address the book
names, so the coder tests the other run's code and passes or fails for the wrong reason.

**Done**, as the developer sees it:

- Two runs on one machine, each built from its own checkout, each pass the journeys they
  pass alone.
- Neither run's build, restart or teardown changes a container the other run uses. The
  container ids and start times of the other run are the same before and after.
- Each journey reaches its own run's stack. The run's report names the addresses it used.
- The book names no host port for a per-run environment. It names each address, and says
  that a run assigns its value at bring-up.
- The same journey text runs against a deployed environment, where the addresses are fixed.
- A second stack comes up in under five minutes (A5).
- A run's end removes its stack and the data it created, and nothing else, also when the run
  failed. A run that died without cleanup is cleaned up before the next stack is made.

**Out of scope:**

- how many stacks one machine can hold;
- per-run deployed environments, such as preview deploys;
- two runs sharing one stack on purpose;
- reloading the production copy of the database;
- the facilities, taps and allowances of [QA across environments](qa-across-environments.md),
  which this note uses unchanged.

## 1b. Claims

1. A runbook declares one entry URL and one health path. Bring-up picks the environment
   marked local-only. (node type `runbook`, stack selection)
2. The client's Compose file pins one project name, and its comment says renaming it is a
   deliberate migration. (client Compose file)
3. Every client service publishes a fixed host port. Bring-up refuses to start when another
   process holds one. (client Makefile)
4. The web image bakes the sign-in emulator's host and port at build time. (client Compose
   build argument)
5. One sign-in emulator serves the whole repository, on purpose. (client Compose comment)
6. The QA plan holds the base URL as a literal, and the coder's QA plan contract tells the
   agent to write `http://localhost:3000`. (page compiler, coder QA prompt)
7. The coder's story mode stops the stack after it commits, through the runbook's stop
   command. (coder workflow)
8. The coder checks out the story branch in the repository's main checkout. (coder workflow)
9. Each run leases its own instance. The environment page names its addresses. Docker
   assigns host ports. The browser reaches everything through one address. Each run's
   database is a clone of a snapshot. (my own recommendation earlier in this session)
10. Ports assigned by the workflow from numbered slots are rejected. (my own, earlier)

## 2. Parts and concepts

### Level 1: parts

1. **Describing an environment.** The part of [QA across
   environments](qa-across-environments.md), extended. It now also owns whether the
   environment is one place every run shares or a kind of place each run gets its own copy
   of, and the names of the addresses a tester reaches there. It never knows any run. It
   hands the names to *resolving addresses* and the copy rule to *holding a lease*.
2. **Holding a lease.** It owns which stack belongs to which run, from the run's start to
   the giving back at its end, and the reclaiming of stacks whose run is gone. It never knows
   what runs inside a stack. It hands a lease to *making an instance*.
3. **Making an instance.** It owns bringing up one copy of an environment for one lease,
   isolated from every other copy, and reporting where that copy answers. It never knows
   journeys or other leases. It hands the copy's addresses to *resolving addresses*.
4. **Giving an instance its data.** It owns the starting data of a new copy, taken from a
   source that no copy writes. It acts at two moments: once per machine, when it takes the
   source, and once per copy. It never knows the app's journeys. It hands a data store to
   *making an instance*.
5. **Resolving addresses.** It owns turning an address name into the value for this run,
   wherever a name appears: a journey, a recipe, a plan, an agent's prompt, a report. It
   never knows how the value was assigned.

*Running and reporting* from the other note consumes the resolved values and is unchanged.

**Flow.** At the start of a run, *holding a lease* reads whether the target environment is
shared or copied. For a shared one, the lease holds nothing and nothing starts. For a copied
one, *holding a lease* first reclaims any stack whose run is gone, then takes a lease named
for the run. *Giving an instance its data* hands the lease a data store. *Making an
instance* brings the copy up under the lease's name and reports where each named address
answers. *Resolving addresses* binds the run's names to those values, from the environment
page for a shared environment and from the copy's report for a copied one. The run performs
its journeys. At the end, also after a failure, *holding a lease* gives the copy back, and
everything that carries the lease's name goes.

**Split test.** In plain words: some places the app runs are shared, and some are made fresh
for each run. The book names the addresses a tester uses, and says which kind of place each
environment is. A run that targets a made-fresh place gets its own copy, with its own data,
and is told where that copy answers. The run uses those addresses and removes its copy when
it ends. Two code bases fit this: one that starts copies as containers on one machine, and
one that starts them as preview deploys. The part names avoid the existing stages. *Making
an instance* nearly took the name "bring-up", which is the existing stage; I named it for
what it produces instead.

### Level 2: concepts

**Describing an environment** (additions)

| Concept | Owns | Never knows |
|---|---|---|
| Sharing | whether the environment is one shared place or copied per run | how a copy is made |
| Address | one named place a tester or the app's browser reaches, with its fixed value on a shared environment and no value on a copied one (revised, R6) | how a copy assigns its value |
| Browser entry | the one address the browser is given, behind which every browser-facing service answers on the same origin | the services behind it |

The other note's Drive port becomes an Address with a role. Its Health check is unchanged.

**Holding a lease**

| Concept | Owns | Never knows |
|---|---|---|
| Lease | one run's claim on one copy, with the run that owns it | what the copy contains |
| Lease name | the identity that scopes every container, network, volume and host port of one copy | the run's work |
| Give-back | removing exactly what carries one lease name | other leases |
| Reclaim | finding leases whose run is gone, and giving each back | why the run ended |

**Making an instance**

| Concept | Owns | Never knows |
|---|---|---|
| Instance maker | bringing up one copy under a lease name, from the run's own checkout (role) | journeys |
| Port assignment | letting the host pick a free port for each published address, and reading back which | which journey uses it |
| Address book | the values of one copy's addresses, written where the run reads them | how they were assigned |
| Readiness | confirming the copy answers at its addresses, sign-in included, through the browser entry | how it was started |

Two variants of Instance maker: a Compose copy on this machine, and a fake for tests that
writes an address book and starts nothing. The Compose variant is the client's own recipe,
which takes the lease name and writes the address book. The toolchain names the lease and
checks the book (revised, R3).

**Giving an instance its data**

| Concept | Owns | Never knows |
|---|---|---|
| Data source | the starting data every copy begins from, which no copy writes | the copies |
| Data store | the data one copy reads and writes (role) | the journeys |
| Overlay | the idempotent test-data changes applied to a new data store | how the store was made |

Two variants of Data store: a **shared store**, where the copy points at one database
server that every copy shares, and a **cloned store**, a copy-on-write clone of the source
for one lease. The choice is made by *holding a lease* from the run's story (A1).

**Resolving addresses**

| Concept | Owns | Never knows |
|---|---|---|
| Reference | turning `{name}` into a value, wherever a name appears | where values come from |
| Address source | the values a run's references read (role) | how they were assigned |

Two variants of Address source: the environment page's fixed values, and a copy's Address
book. Bring-up picks one from Sharing and writes an address book either way, so every
Reference reads a book and none falls back to the page (revised, R5). Reference is the other
note's concept, now covering addresses in prose and plans as well as in recipes.

**Shared values.** Address names cross *describing an environment*, *making an instance*
and *resolving addresses*. They are a read-only catalog the environment page holds. Lease
names cross *holding a lease* and *making an instance* as a plain value handed along.

## 3. Invariants

1. **No two live copies share a container, a network, a volume or a host port.** Owner:
   Lease, which refuses a lease name already live. Upheld by Lease name and Port assignment.
2. **Give-back removes only what carries its lease name.** Owner: Give-back. A shared
   environment's lease holds nothing, so no run stops a shared place.
3. **A journey reaches only its own run's copy.** Owner: Reference, which fails on a name
   the Address source lacks. Upheld by the book check that refuses a literal address an
   environment names (the other note's invariant 6).
4. **No built artifact of a copied environment holds an address.** Owner: Readiness, which
   signs in through the browser entry and fails when the app calls any other origin.
5. **No copy writes the Data source.** Owner: Data store. A shared store is allowed only for
   a run whose story changes no schema (A1).
6. **Every lease is given back.** At the run's end, also after a failure. A lease whose run
   is gone is reclaimed before the next lease on the machine. Owner: Reclaim.
7. **An address book names every address the environment page names.** Owner: Readiness.

## 4. Forces and patterns

### Forces

- **F1.** Runs overlap in time on one machine, from different checkouts. A book run lasts
  hours, and a parked one lasts days.
- **F2.** Which host ports are free is known only at bring-up. Any process may hold one.
- **F3.** An address varies per run on a copied environment and is fixed on a shared one.
  The journey text must not vary.
- **F4.** The starting database is 26.6 GB, built from a production read that must not be
  repeated. The machine has 46 GB free. One table alone is 12.5 GB.
- **F5.** Runs die without cleanup: killed, parked, crashed.
- **F6.** The browser runs on the host and is handed URLs. Built front-end assets carry
  whatever addresses they were built with.
- **F7.** Agents write addresses into prose, plans and code, from what the book says.
- **F8.** Unit tests must run with no container engine.
- **F9.** A story may change the schema. Most do not.

### Between parts

- **One value handed along**: the address book, written by *making an instance* into the
  run's directory and read by *resolving addresses*. F2 and F3 make the value known only at
  bring-up, and a file outlives the process that wrote it.
- **A scope named by the lease**: every resource the copy creates carries the lease name,
  and give-back removes by that name. F1 and F5 need removal that finds everything without a
  list kept by a process that may be dead.

### Inside a part

- **Address source** is a role with two variants (F3).
- **Instance maker** is a role with a Compose variant and a fake (F8).
- **Port assignment** asks the host for any free port and reads it back (F2). No slot table.
- **Browser entry** is one reverse proxy on one origin (F6). Sign-in, the API, reports and
  stored files are paths behind it, so the built app needs only relative addresses.
- **Data store** is a role with a shared and a cloned variant (F4, F9). A full copy per run
  does not fit the disk. A file-level copy-on-write copies the 12.5 GB table on its first
  written row, so the cloned variant needs block-level copy-on-write.
- **Reclaim** sweeps at lease time and asks whether each lease's run is alive (F5). No
  daemon.
- **Reference** is text substitution of `{name}` at the moment of use: a recipe as it runs, a
  plan as it runs, a prompt as it is built (F5, F7). Plans keep the name, so a resumed run
  whose copy was remade reaches the new one. Prompts carry the name and its current value,
  so an agent never invents a port. The run's report records each value it used (revised,
  R4).

### Claims

1. Entry URL on the runbook: rejected. It moves to the environment as named addresses (F3),
   as the other note's S3 already moves it.
2. A pinned project name: kept as the default for the developer's own commands. A run passes
   its lease name instead (F1).
3. Fixed host ports: rejected for copies (F2). The port check at bring-up disappears for
   runs.
4. The baked emulator address: rejected (F6). Sign-in moves behind the browser entry.
5. One emulator for the repository: rejected for copies. Emulator users live in memory and
   each convergence reseeds them, so a shared emulator lets one run's seeding overwrite the
   other's.
6. The literal base URL: rejected. A plan carries `{gateway}`, resolved each time it runs
   (F5, F7, R4).
7. The coder's teardown: kept, scoped to its lease (invariant 2).
8. The story branch in the main checkout: rejected. A copy builds from its run's own
   checkout, so two runs in one checkout build each other's code (A4).
9. My own recommendation: re-derived piece by piece above, except the per-run clone, which
   F4 moves behind the Data store role.
10. Workflow-assigned slots: rejected. F2 lets any process take a slot's port, and a slot
    table needs a registry that F5 leaves stale.

### SOLID check

- Single responsibility: each Owns reads without "and". Readiness checks sign-in as part of
  answering at the browser entry, which is one check.
- Open/closed: a preview-deploy maker adds one Instance maker variant and one line where the
  run picks it. A third store adds one Data store variant.
- Liskov: the fake maker and the Compose maker are each a kind of Instance maker only.
- Interface segregation: Instance maker declares make and give back. Address source declares
  one lookup.
- Dependency inversion: Reference never knows which Address source it reads, and Lease never
  knows which maker runs.

### Open lookups

- **L1.** Can the client web app reach the sign-in emulator through the browser entry? This
  decides invariant 4 and the browser entry's paths.
- **L2.** How does the current code run the stack: by runbook steps, by `ostler qa stack`,
  or by the workflow? This decides where Lease name is threaded.
- **L3.** Can a block-level copy-on-write clone be made on this machine without root? This
  decides whether the cloned store ships in the first slice.

## 5. Mapping onto the existing system

### Revision log

- R1. Section 2, Data store: became a role with two variants. Finding: the source volume is
  26.6 GB with 46 GB free, and the largest table is 12.5 GB (F4). A clone per run was my
  earlier recommendation and does not fit.
- R2. Section 3, invariant 5: a shared store is allowed for a run whose story changes no
  schema. Finding: R1.
- R3. Section 2, Instance maker: the Compose variant is the client's recipe, which reads the
  lease name and writes the address book. Finding: the toolchain runs recipes it does not
  own, and reading ports back from Compose would tie it to one engine.
- R4. Section 4, Reference: resolves at the moment of use, not when a plan is built.
  Finding: a parked run resumes days later, after Reclaim may have remade its copy on other
  ports (F5).
- R5. Section 2, Address source: bring-up writes an address book for a shared environment
  too, from the page. Finding: a reader that falls back to the page when a book is missing
  reaches the shared stack, which is the failure of section 1.
- R6. Section 2, Address: a copied environment's page gives no value. Finding: R5, and S2's
  done-when that the book names no host port for a copied environment.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Describing an environment | Reshape | node type `environment` (`ostler/ostler/registry.py`). It has no named addresses. Its service bullets hold literal URLs in prose. |
| Holding a lease | New | ostler, beside the stack code (`ostler/ostler/qa/stack.py`). |
| Making an instance | Reshape | `ostler/ostler/qa/stack.py` brings a runbook's stack up and down, and the runbook carries the entry URL (`ostler/ostler/qa/runbook.py:32`, `:211`). No lease name, no port readback. |
| Giving an instance its data | New | the client's bring-up target, with the shared store as its first variant. |
| Resolving addresses | Reshape | the entry URL flows as one value from the runbook manifest (`ostler/ostler/qa/stack.py:450`). No `{name}` resolution exists. |

### Concepts

- **Sharing**: new, an `environment` bullet. Local-only today stands in for it, and the two
  differ: a local environment can be shared, as the developer's own stack is.
- **Address**: new, nested bullets under the environment. Replaces the runbook's
  `entry-url`, which doctor checks today (`ostler/ostler/doctor.py:2184`, `:2201`).
- **Browser entry**: exists in the client as the gateway service. Reshape: sign-in and
  stored files answer on other ports (claim 4).
- **Lease, Lease name, Give-back, Reclaim**: new. The coder's teardown
  (`workflows/src/workhorse_workflows/coder/qa/nodes/qa.py:184`) calls the stack's down
  command (`ostler/ostler/qa/runbook.py:497`), which becomes Give-back.
- **Instance maker**: reshape of the stack bring-up, which passes no project name.
- **Port assignment, Address book**: new, in the client's recipe (R3). Compose publishes a
  container port on a free host port when the host side is omitted, and reports it back per
  service and port.
- **Readiness**: exists as the health check. Reshape: it reads the address book.
- **Data source, Data store, Overlay**: Overlay exists in the client. The other two are new.
- **Reference, Address source**: Reference exists for fixture values only. Address source is
  new.

### What the existing system has that the design lacks

- The port check at bring-up refuses a stack when another process holds a fixed port. Waste
  for copies, since F2 removes the fixed ports. It stays for the developer's own stack.
- The reuse flag on a runbook adopts a stack already running. A concept the design missed
  for shared environments only: a shared place is always adopted, so Sharing covers it.

### Claims against the existing system

| Claim | Existing system | Design |
|---|---|---|
| 1 entry URL on runbook | follows | rejects |
| 2 pinned project | follows | keeps as default only |
| 3 fixed ports | follows | rejects for copies |
| 4 baked emulator address | follows | rejects |
| 5 one emulator | follows | rejects for copies |
| 6 literal base URL | follows | rejects |
| 7 coder teardown | follows, unscoped | keeps, scoped |
| 8 branch in main checkout | follows | rejects |
| 9, 10 | not built | re-derived, R1 |

### Lookups

- L1: resolved. The emulator's API paths start with fixed prefixes that a proxy can route,
  and the client SDK takes a URL. A copy signed in through its own gateway (A3).
- L2: resolved. The stack's up and down commands (`ostler/ostler/qa/runbook.py:471`,
  `:497`) run the runbook's steps, and the coder calls the down command from its story flow
  (`workflows/src/workhorse_workflows/coder/main/flow.py:103`, `:274`). The lease name
  threads through those two commands as one argument.
- L3: unresolved. The disk is ext4 with no reflinks, and Docker uses overlay2, which copies
  whole files (A2).

## 6. Slices

1. **S1. One copy beside the shared stack.**
   - Touches: Lease, Lease name, Give-back, Instance maker (Compose), Port assignment,
     Address book, Readiness, Data store (shared), Address source (address book), Reference
     for `{gateway}` only. Client: a project name per run, published ports with no host
     side, sign-in and stored files behind the gateway, a web build with no baked address.
   - Done when: with the other run's containers live, one run built from a worktree brings
     up its own copy, the book's sign-in and report journeys pass at its assigned gateway
     address, and its teardown leaves the other run's container ids and start times
     unchanged.
   - This is the thinnest path that shows isolation. It answers the coder run that waits on
     it.
2. **S2. Named addresses in the book.**
   - Touches: Address, Sharing, Address source (page), Reference everywhere, the book check.
   - Done when: the client's web and API books name no host port for local, and the local
     run passes the same journeys at an assigned port.
3. **S3. The coder runs on its own copy.**
   - Touches: the coder's lease per story, its QA plan reading `{gateway}`, Give-back.
   - Done when: an attended coder run on one story passes QA against its own copy, and the
     book run's stack is untouched.
4. **S4. Reclaim.**
   - Touches: Reclaim.
   - Done when: a copy whose run was killed is removed at the next lease, and a live run's
     copy is not.
5. **S5. A cloned store for schema-changing stories.**
   - Touches: Data source, Data store (cloned).
   - Done when: a story that adds a migration runs on a clone, the shared store's schema is
     unchanged, and the clone's disk cost stays under 2 GB.
   - Built after L3 is resolved.

## 7. Assumptions

Most expensive first.

1. **A1. Most stories change no schema, and journeys write only data they create or
   idempotent overlays.**
   - Decided: copies share one database server until S5. A run whose story adds a migration
     waits for S5.
   - Basis: the other note's rule that a journey changes only data it created. The disk
     measurement (F4).
   - If wrong: invariant 5, Data store, S1. Every run would need a clone, and S5 moves first.
2. **A2. Block-level copy-on-write can be had on this machine.**
   - Decided: the cloned store waits for S5.
   - Basis: none. Ext4 has no reflinks. A loop-mounted filesystem with reflinks needs a mount
     that Docker's daemon would have to make.
   - If wrong: S5 becomes a trimmed source holding only the data the books use, made once.
3. **A3. The client web app signs in through the gateway when the emulator's paths are
   routed there.**
   - Decided: sign-in moves behind the browser entry in S1.
   - Basis: measured on 2026-10-10. A copy on assigned ports passed the sign-in and report
     journeys through its gateway, and its bundle resolved the emulator from the page
     origin.
   - If wrong: invariant 4, Browser entry. The web app reads the emulator's address from a
     config file the gateway serves at run time.
4. **A4. Each run has its own checkout.**
   - Decided: the coder runs from a worktree.
   - Basis: book runs use worktrees today. The coder branches in place.
   - If wrong: two runs build each other's code, and claim 8 needs a code change in the
     coder.
5. **A5. A copy comes up in under five minutes.**
   - Decided: S1's done-when holds bring-up to that.
   - Basis: applying the infrastructure program to the emulator took about 20 seconds. Image
     builds and readiness are unmeasured.
   - If wrong: S1's done-when.
6. **A6. The client's host-side tools can read addresses from the address book.**
   - Decided: seeders and readiness checks take addresses as arguments.
   - Basis: the client's API Makefile names fixed ports in 28 places.
   - If wrong: S1 grows, or those tools run inside the copy's network.
7. **A7. Memory holds a second copy of the stack.**
   - Decided: no limit on live copies.
   - Basis: none.
   - If wrong: Lease gains a cap per machine.
8. **A8. Runs and their copies live on one machine.**
   - Decided: Reclaim asks the local process table whether a run is alive.
   - Basis: every run today starts from this machine.
   - If wrong: Reclaim, Lease.
