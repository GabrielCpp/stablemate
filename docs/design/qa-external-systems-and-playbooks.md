# QA with external systems, faults and playbooks

**Disclosure.** I wrote this note after a long session inside the existing system. I had read
the node types for fixture, step, runbook, environment, concept, cli and format, the check and
act vocabularies, the saddlebag skill, the stack.yml reference, the sandbox port forwarder, the
QA harness authoring concept and the floci.io product page. Two earlier design notes reached me
too: [QA across environments](qa-across-environments.md) and
[Run stack instances](run-stack-instances.md). Neither is built. Their design decisions and the
system's are claims in section 1b. I checked each part and concept below against the question
"would I have named this without having seen the solution?" and name the checks that failed where
they occur. This note extends QA across environments and reuses its parts by name where they
fit.

## 1. Problem

A tester, a person or an agent, holds a book for an app whose behaviour depends on things the
book cannot start on this machine: a real camera behind a booking service on a private network,
a third-party API, a cloud queue or table, and on things going wrong: a dependency that times
out, two writers racing on one record, a message delivered twice. Today the book can describe
the app, bring up its local stack, seed data and check what a screen or a response shows. It
cannot say "borrow the camera, play the video, check the camera caught it, give the camera
back". It cannot make a dependency fail on purpose. It cannot show what a queue consumer did
with a duplicate. And it has no page for the procedures the team keeps elsewhere: the Confluence
playbook, the vendor's Swagger page, the command that mints a test credential. An agent asked in
a chat session "how do I test the camera flow?" has nothing to read, so it re-derives the answer
from source and from the person's memory each time, and gets it a little different each time.

**Done**, as the tester sees it:

- The book names each outside thing the app depends on: how to reach it, how to tell it answers,
  how one run borrows it, how it is given back. A journey that needs one that does not answer is
  reported as skipped with that thing's name. It is never failed and never passed.
- A journey can state "the camera recorded the video" and the run proves it from the camera's
  own records, not from the app's log.
- A journey can state "the payment provider times out" and the run makes that true for the
  journey's length, then checks what the app did about it. On a phone, the same sentence makes
  the app's own outbound calls fail at the device, with no change to the backend.
- On a shared development environment, where a published event or a table change cannot be asked
  for after the fact, the book names the tailing tools the team already runs there, and a journey
  claims the event the app published from what the tail caught since the journey began.
- A journey can state "two callers write this record at once" and the run checks that one won
  and the other was told.
- A journey can state "this message arrives twice" and the run checks the effect happened once.
- A journey can state "it is half past two on the night the clocks go back, and the user sits in
  Tokyo" and the run makes that true for the browser, for the app, or for both, then checks what
  the screen shows and what the app stored.
- A situation no screen can produce, such as an administrator who exists in both the identity
  provider and the users table, is arranged by one recipe that sends a request to the first and
  runs a command against the second, and the journey then signs in as that administrator.
- A local run uses emulators for the cloud services the app calls, declared in one place. The
  same journeys run against the real services on an environment that has them.
- The team's procedures live in the book as pages an agent finds by their plain name. Each step
  of a procedure is either a command the agent runs, with what confirms it, or a sentence a
  person performs, with what they see afterwards.
- In a chat session, an agent asked about any outside thing answers from the book in one fixed
  shape: what it is, how to reach it, how to borrow it, how to check it, how to give it back, and
  which journeys need it. The answer costs a few reads, not a search of the source.

**Out of scope:**

- load and performance testing;
- running journeys on production, which QA across environments owns;
- owning or writing the camera booking service, the vendor API or the emulator;
- the emulator's fidelity: a defect in floci is floci's;
- a server whose own zone changes between scenarios: a copy of the stack runs in one zone, and a
  second zone is a second copy, which Run stack instances owns;
- a graphical player for procedures: the book is read in a terminal or a chat;
- the internals of the stack testing skills (go, python, flutter), which keep their own fakes;
- device farms for mobile.

## 1b. Claims

Design decisions that reached me through the existing system or the two earlier notes.

1. A fixture is the arrangement unit. Its steps are `seed`, `run`, `serve`, `verify` and
   `probe`. A failing probe gaps every claim that needs the fixture as `gapped: <name> absent`.
   (node type `fixture`)
2. A fixture declares secrets as environment-variable names only. Values come from the runbook's
   `secrets:` recipes or from saddlebag, and never reach a page or a transcript. (fixture,
   saddlebag skill)
3. Checks are a closed vocabulary of callables with literal arguments. Each entry excludes one
   defect class and costs one harness callable per driver. (check vocabulary)
4. The one intercept effect is `rewrite(event, find, replace)` on a response on its way to the
   browser. (flow node type)
5. An environment page is descriptive and compiles to nothing. The services a local copy runs
   live in `stack.yml`, brought up one copy per lease. (environment, stack reference)
6. A concept carries `rule:` bullets. A plain feature doc carries prose. A `cli` page holds
   invocable commands. Nothing holds a human procedure. (concept, plain-feature, cli)
7. A `serve` step's process is stopped at scenario end whether the scenario passed, failed or
   timed out. The `teardown` step kind is declared and never run. (fixture, QA across
   environments mapping)
8. A sandboxed run reaches host upstreams through a forwarder configured by a JSON map of local
   port to host and port. (sandbox port forwarding)
9. QA across environments: a Watch port on the environment, a Tap per effect kind, a Facility
   check that yields a skip, a Lease that gives back, an Allowance per effect kind, and a Recipe
   chosen per environment. None of it is built.
10. The library's testing skills state a universal contract and per-stack fakes. None covers an
    event handler, a fault on a dependency, contention on a NoSQL record, or a hardware fake.
11. `data-state` nodes read a record back through an `observe:` link and tell states apart with
    `verify:` checks on that read.

## 2. Parts and concepts

### Level 1: parts

1. **Describing an outside thing.** It owns what the app depends on that the book cannot start
   here: a device, a third party, a cloud service, a service a person operates. For each: how
   it is reached, how to tell it answers, how a run borrows it and gives it back, and what stands
   in for it where the real one is absent. It never knows which journey needs it or what a
   journey checks. It hands a handle, an address and the facts of a borrow, to *arranging a
   situation*.
2. **Arranging a situation.** It owns putting the world in the shape a claim is about, including
   a bad shape: a dependency that misbehaves, a record under contention, a message handed over
   twice. It owns the undoing too. It never knows what is checked. It hands facts it produced
   to *checking from the other side*.
3. **Checking from the other side.** It owns observing an effect where it lands rather than
   where the app claims it: the camera's list of recordings, the consumer's ledger, the record's
   version. It owns waiting for an effect that lands late. It never knows how the situation was
   arranged.
4. **Keeping the know-how.** It owns the procedures people follow and the specifications the app
   depends on, as pages: where each came from, when it was last checked, which steps a machine
   runs and which a person performs. It never knows how the harness runs a journey.
5. **Answering in a session.** It owns how an agent asked in a chat finds the pages above, the
   fixed shape its answer takes, and which steps it may run on the spot. It never knows the
   content of any page.

The flow. People and agents write pages of parts 1, 2 and 4 when they write the book. When a
run starts, part 1 asks each outside thing whether it answers and borrows what the run's
journeys need. Part 2 arranges each journey's situation, good or bad, from the handles part 1
gave it. The journey acts on the app. Part 3 reads the outside thing's own record of what
happened, waiting where the effect lands late, and gives its verdict. At scenario end, part 1
gives back what it borrowed and part 2 undoes what it arranged, whatever the verdict. Part 5
acts at another moment entirely: a person asks in a chat, and part 5 walks from the name they
used to the pages of parts 1, 2 and 4 and answers in its shape, running the steps the person
asks it to run.

The test. In one paragraph with no technical vocabulary: the book lists the outside things the
app needs and how to borrow, check and return each; a test can arrange a bad situation on
purpose; a test proves an effect from the far side; the team's procedures are pages with
runnable and manual steps; and an agent asked about any of it answers from those pages. Two
codebases fit it: this one, and a plain pytest suite with a resources YAML and a docs folder.
No part carries the name of a module. "Fixture", the existing unit, is not a part here on
purpose: it is one shape part 2 takes.

### Level 2: concepts

**Describing an outside thing**

| Concept | Owns | Never knows |
|---|---|---|
| Resource | one outside thing by its plain name and the environments it exists in | the journeys that need it |
| Reach | the one way a run talks to the resource: an HTTP interface at a base address presenting a named credential, or a command-line tool with its binary and the environment it needs | what any step says to it |
| Reachability probe | the question "does it answer now" and its yes or no | why it does not |
| Borrow | how one run takes exclusive use of a resource and how long it may keep it | what the run does with it |
| Return | giving back what was borrowed, at scenario end or lap end, success and failure alike | the verdict |
| Stand-in | a local substitute for a resource: an emulator, a mock the book starts, or none | what a journey checks |
| Residence | where the resource lives: this machine, a private network, the public internet, and the path a sandboxed run takes to it | the resource's protocol |

Borrow and Return together are the **Lease** of QA across environments. That note's Lease owns
both the taking and the giving back. Here they are two concepts because the giving back has an
owner the taking does not: it must run when the scenario failed or timed out, which is a
harness moment and not a recipe step (invariant 1).

Reach is a role with two variants, *HTTP interface* and *command-line tool*. Every step aimed at
a resource, a probe, a borrow, a return or an observation, speaks through its reach, so the step
grammar has one form per variant and nothing else varies with the resource's kind (R6).

Resource is a catalog: a read-only reference every other part consults by name. That is the
first of the three allowed shapes for a concept two parts need.

**Arranging a situation**

| Concept | Owns | Never knows |
|---|---|---|
| Recipe | the ordered steps that produce one situation and the facts they print | checks |
| Fault | one way a dependency misbehaves for the length of a scenario: a timeout, a refusal, a cut connection, a slow answer, a truncated body | what the app does about it |
| Contention | several actions on one record issued at once | which one should win |
| Redelivery | the same message handed to the consumer more than once | the consumer's code |

| Clock | the instant and the zone one party of the journey lives in for the scenario's length: the browser, the app, or both | what the app computes from the time |
| Proxy | a stand on a path the app's traffic takes, where rules act on what passes: the forwarder between a stack and its upstreams, or a proxy the device's outbound calls pass through | which fault is installed, and what a journey reads of the traffic |

Proxy is a role with two variants, *stack forwarder* and *device proxy* (R7). Interception on a
path is always a proxy, whatever it then does with the traffic. Fault names a misbehaviour the
proxy performs; a proxy's own `caught` observation, read from a Mark, is the tap on an outbound
call. The environment page says which proxy a party has.

Recipe is the Recipe of QA across environments, unchanged. Fault, Contention, Redelivery and
Clock are the four arranged shapes the problem names. Clock was dropped once and brought back
(R1, R5): a daylight-saving boundary and a user in a foreign zone are behaviours of the composed
app, which its unit tests' injected clock never exercises.

**Checking from the other side**

| Concept | Owns | Never knows |
|---|---|---|
| Side observation | one named way to read a resource's own record of what happened, and the JSON it prints | the app's log |
| Eventual read | re-reading a subject until a deadline, and the last value it saw | why the effect was late |
| Winner count | how many of a set of contending actions the record accepted | the actions' bodies |
| Idempotent effect | the count of an effect after a redelivery | the message bus |
| Mark | the position a tail stood at when the scenario began, so an observation on it reads only what came after | the events themselves |

Side observation covers what QA across environments called a Tap. A tail tool the team runs on
an environment, one that catches events a bus delivered or changes a table streamed, is a
Resource with a reach like any other, and "what it caught" is one of its observations. The one
thing a tail adds is the Mark, because its record is a stream and not a state (R7). An outbound
call to a vendor that keeps no readable log is caught the same way, by a tail on the path.

**Keeping the know-how**

| Concept | Owns | Never knows |
|---|---|---|
| Playbook | a human procedure as ordered steps, each runnable with a confirmation or manual with an observable, with its purpose and preconditions | the harness |
| Reference | a specification the app depends on but does not own, such as a vendor's OpenAPI document, and the part of it the app uses | journeys |
| Credential procedure | how a test credential for a resource is minted and the name it is stored under | the value |
| Provenance | where a page came from, its source address and version, and when it was last checked against that source | the page's content |

Provenance is a shared value type carried by Playbook and Reference. That is the second
allowed shape.

**Answering in a session**

| Concept | Owns | Never knows |
|---|---|---|
| Question | which of the fixed questions was asked about a name: what is it, how do I reach it, how do I borrow it, how do I check it, how do I give it back, which journeys need it, how do I run this procedure | the answer |
| Answer shape | the fixed order an answer takes: resource, probe, borrow, stand-in, procedures, observations, return, journeys | how the pages were found |
| Runnable step | a step the agent may run now, and the confirmation it reads back | manual steps |

## 3. Invariants

1. **Every Borrow has a Return that runs on success, failure and timeout.** Owner: Return. The
   harness runs it at scenario end as it already stops a `serve` process. Recipe upholds it by
   naming the return step.
2. **A journey that needs a Resource whose probe says no is skipped with the resource's name,
   never failed and never passed.** Owner: Reachability probe.
3. **A Fault changes what the app receives and never what a real Resource receives.** Owner:
   Fault. A fault answers in the resource's place, holds the request, or alters the reply on its
   way back; it never forwards an altered request. The compiler refuses a fault on a party that
   has no Proxy in the run's environment.
4. **A Side observation reads the resource's own record, never the app's.** Owner: Side
   observation. A resource page with no observation offers no side check, and a journey claiming
   one against it is a doctor finding.
5. **A secret value appears in no page, no compiled plan and no transcript.** Owner: Credential
   procedure, which holds names only. Upheld by saddlebag at run time.
6. **A Playbook step is runnable with a confirmation, or manual with an observable. Never both,
   never neither.** Owner: Playbook.
7. **A Reference states what the app uses of a specification and points at the whole. It never
   copies the whole.** Owner: Reference. Provenance keeps the pointer current.
8. **Every Resource, Playbook and Reference is found by `ostler search` under its plain name,
   and is linked from at least one page of the app.** Owner: Answering. A page nothing links is
   a doctor finding.
9. **An Eventual read has a deadline the book states. Passing on the last read before the
   deadline passes. Failing reports the last value seen.** Owner: Eventual read.
10. **A Contention claim names how many winners the record accepts. "All succeeded" on a
    record that allows one is a failure.** Owner: Winner count.
11. **A Stand-in and the real Resource are reached by the same name in a journey.** Owner:
    Resource. The environment chooses which one the name resolves to; the journey never does.
12. **A Clock step names the party it moves, and a party it does not name runs on real time.**
    Owner: Clock. The report states both, so a passing journey never hides a skew between the
    browser's time and the app's that the writer did not ask for.

## 4. Forces and patterns

### Forces

- **Resource kinds vary**: a device behind a booking API, a vendor HTTP API, a cloud queue, a
  cloud table, a service a person operates. Their protocols vary independently of how they are
  borrowed and returned.
- **Outside things speak HTTP or a command line, and one situation often takes both.** An
  identity provider has a management API; a table has a vendor CLI. The administrator no screen
  can create is a request to the first and a command to the second, bound by the id the first
  returned.
- **Stand-ins vary per environment**: local has an emulator or a mock, a shared dev environment
  has the vendor's sandbox, production has the real thing. The journey is one text.
- **Faults vary and must be swapped per scenario**: timeout, refusal, cut connection, slow
  answer, truncated body. A new one appears when a new outage does.
- **A sandboxed run must reach a private network.** The path varies: a forwarder on the host
  that is a node of that network, or a network client inside the sandbox.
- **The check vocabulary must stay small.** Each new check costs a callable per driver and a
  writer's understanding (claim 3).
- **Know-how comes from outside sources that change.** A playbook copied from a wiki drifts the
  week after.
- **A chat agent's context is small.** The answer must be reachable in a handful of reads and
  relayed in a shape the person recognises each time.
- **Hardware is scarce and shared.** One run holds the camera at a time, and a leaked borrow
  blocks the whole team until someone notices.
- **Observed effects land late.** A camera writes its recording seconds after the video ends; a
  consumer drains a queue on its own schedule.
- **A shared development environment cannot be asked after the fact.** An event delivered to a
  bus and consumed is gone; a table change is in the table with no history. The team runs tailing
  tools there for this reason, and the book must use them rather than redo them.
- **A phone's outbound calls leave the device.** They never pass the stack's forwarder, so a
  fault for a mobile journey must sit where the device sends its traffic.
- **Time lives in three places.** The browser computes what the user sees from its own clock and
  zone. The app computes deadlines and dates from its process clock. A stand-in has a clock of
  its own. The three can be moved independently, and some apps' runtimes let none of them be
  moved from outside.

### Between parts

- **A catalog of resources, referenced by name.** Resource pages are read-only references that
  Arranging, Checking and Answering consult by name. Journeys declare the resources they need
  the way they declare fixtures today. Force: resource kinds vary, chat context is small.
- **Ports and adapters for what varies per environment.** Stand-in, Residence and Fault are
  roles. Each variant is its own concept. The choice sits with the environment page, the part of
  the book that assembles a run's world. Force: stand-ins vary per environment.
- **One value handed along.** A Borrow produces facts (the camera's id, its stream address) that
  Recipe steps and Side observations read by name, the way `provides:` facts travel today.
  Force: none new. This is a plain value.

### Inside a part

- **Resource**: a file-level node type, one page per outside thing. Plain bullets: `reach:`
  (protocol and address, with `{name}` for an environment address), `residence:`, `probe:`,
  `borrow:`, `return:`, `stand-in:` per environment, and a `## Observations` section. No
  variation inside it, so it is a value type. Force: catalog.
- **Reach**: a role with two variants. *HTTP interface*: `base:` (an address, `{name}` allowed),
  `credential:` (a secret name presented as a bearer or header), and the Reference that
  specifies it. Its step form is `request: <METHOD> <path>` with the existing `body` and
  `header` acts, and `provides:` facts read from the response by JSON path. *Command-line tool*:
  `binary:`, `secrets:` (names put in its environment), and an `install:` check. Its step form
  is the existing `run:`. A step says which resource it speaks to with `on: <resource>`, and the
  harness puts that reach's address, credential and secrets in the step's environment under the
  resource's name, so a recipe mixes a `request:` on one resource with a `run:` on another and
  binds them by `provides:` facts, as fixtures bind steps today. Force: outside things speak HTTP
  or a command line. A probe is a `request:` or a `run:` like any other step.
- **Residence**: a role with three variants, *this machine*, *private network*, *internet*. The
  harness picks the path from the variant: a private-network resource is reached through the
  host forwarder, the others directly. Force: sandbox must reach a private network. Claim 8
  re-derived: the forwarder is the private-network adapter.
- **Reachability probe**: the existing `probe` step semantics, with one change of outcome: a no
  yields a skip, not a capability fault. Force: hardware is scarce, so absence is routine and
  must read as routine. Claim 1 re-derived in part: the probe stays, the wording of the outcome
  is QA across environments S2 (A6).
- **Borrow and Return**: two steps of a scenario-lifetime recipe, `kind: borrow` and
  `kind: release`. The harness runs the release step at scenario end regardless of verdict, as
  it stops a `serve` process today. Force: hardware is scarce, invariant 1. Claim 7 re-derived:
  the never-run `teardown` kind is this, renamed to say what it does.
- **Stand-in**: a role with three variants, *emulator* (a service in stack.yml, floci for AWS,
  Azure, GCP and OCI services), *mock* (a `serve` step the book starts), *none*. The environment
  page names which variant each resource has there. Force: stand-ins vary per environment.
  Claim 5 reshaped: the environment page gains one bullet the harness reads at run time.
- **Fault**: a role whose variants are rules on a Proxy: *timeout* (hold the request past
  the app's deadline), *refuse* (answer a status), *cut* (close the connection), *slow* (forward,
  then delay the reply), *truncate* (forward, then cut the reply's body). One recipe step,
  `kind: fault on=<resource> mode=<variant>`. Force: faults vary and are swapped per scenario,
  and the check vocabulary must not grow for them: a fault is an arrangement, not a check. Claim
  4 re-derived and widened: `rewrite` edits a response to the browser; a fault edits the app's
  own dependency. The two sit on different paths and both stay.
- **Proxy**: a role with two variants. *Stack forwarder*: the sandbox forwarder that already
  relays a stack's upstream ports, which gains the rules and a record of what passed. *Device
  proxy*: an HTTP proxy on the host that the emulator or device is pointed at for the scenario's
  length, with the host's certificate trusted by the test build (A15); the existing device steps
  set and clear the proxy setting. Either variant is also a Resource with one observation,
  `caught`, which a journey reads from the Mark like a tail. The environment page's `proxies:`
  bullet names which variant each party has. Force: a phone's outbound calls leave the device,
  and interception on a path is always a proxy.
- **Contention**: one act on the http driver, `race(count=<n>)`, that sends the claim's request
  n times at once. Force: contention. One act, http only.
- **Redelivery**: a recipe step that publishes the same message twice to the stand-in queue. No
  new grammar: a `kind: run` step with the emulator's own CLI. Force: none new.
- **Clock**: a role with one variant per party. *Browser clock*: the browser context is created
  with the zone and locale, and its clock is installed at the instant, so `Date`, timers and
  rendering all agree. *Process clock*: the app's container carries a time-faking preload that
  reads its instant from a file the step writes, for runtimes on the C library; a Go or Java
  service does not take it (A12). *App seam*: the app's own override, a header or an environment
  variable it documents, named on the environment page. One recipe step,
  `kind: clock on=browser|app at=<instant> tz=<zone>`, and a `clocks:` bullet on the environment
  page naming which variant each party has there. A party with no variant makes the step a gap,
  not a fault. Force: time lives in three places and the scenario must say which it moves. The
  server's own zone is fixed per stack copy by `TZ` in its template, so "the server in UTC and the
  user in Tokyo" is one copy and a browser clock, and two server zones are two copies.
- **Side observation**: a named entry under a resource page's `## Observations`, a `run:` that
  prints JSON. A claim points at one with `observe: @<resource>.<observation>` and its `verify:`
  checks read that JSON instead of the response. Force: the check vocabulary must stay small: the
  existing `count`, `json_path`, `created` and `absent` read the observation unchanged. Claim 11
  re-derived: `observe:` already means "read it back here" on data states.
- **Mark**: a tail resource's observation declares `cursor:`, a `request:` or `run:` that prints
  the tail's current position. The harness reads it when the scenario begins and passes it as
  `since=` to every observation on that tail in the scenario. No grammar on the journey: a
  claim on a tail observation reads from the mark by construction. Force: a shared environment
  cannot be asked after the fact.
- **Eventual read**: one keyword parameter, `within=<seconds>`, accepted by every check that
  reads a subject. The harness re-reads until the deadline. Force: effects land late, and a new
  check per subject would multiply the vocabulary. Invariant 9 is its owner.
- **Winner count**: one new check, `winners(count=<int>)`, over the responses a `race` act
  produced: the number with a success status. The existing `conflict_on_stale` checks the loser's
  answer. Force: contention. One callable, http only.
- **Idempotent effect**: the existing `count` check on a Side observation with `within=`. No new
  grammar.
- **Playbook**: a file-level node type under a `playbooks/` folder, with `## Steps` reusing the
  step grammar. A runnable step carries `run:` and `verify:`. A manual step carries `do:` (a
  sentence) and `see:` (what the person observes). `purpose:` and `before:` bullets. It compiles
  to no scenario; `ostler playbook run <name>` walks it, running runnable steps and stopping at
  each manual one. Force: know-how must be communicable and partly runnable. Claim 6 widened:
  a procedure is neither a concept nor a feature doc.
- **Reference**: a file-level node type under a `references/` folder: `source:` (the
  specification's address), `file:` (a vendored copy, owned), and a `## Uses` section listing
  each operation the app calls, linking the resource it belongs to. Force: freshness, invariant
  7. Not a `format`: a format is the shape of this app's own data.
- **Credential procedure**: a playbook whose runnable step carries `secret: <NAME>`: the harness
  pipes the step's stdout into `saddlebag secret set <NAME>` and the value never reaches the
  caller. Force: invariant 5. Claim 2 re-derived.
- **Provenance**: two bullets, `source:` and `checked: <date>`, on Playbook and Reference. A
  doctor warning when `checked:` is older than the window (A9). Force: know-how drifts.
- **Question and Answer shape**: one command, `ostler explain <name>`, that resolves the name to
  a resource, playbook or reference and prints the fixed shape by walking the graph: the page,
  its probe, borrow, stand-in per environment, the playbooks and references that link it, its
  observations, its return, and the journeys whose `needs:` name it. A skill section tells the
  agent to run it before reading source. Force: chat context is small.
- **Runnable step**: `ostler playbook run <name> --step <n>` runs one step and prints its
  confirmation. The chat agent runs a step only when the person asks. Force: none new.

### Claims

| Claim | Fate |
|---|---|
| 1 fixture as arrangement unit, probe gaps | kept; the probe's outcome becomes a skip (A6) |
| 2 secrets as names | re-derived from invariant 5; Credential procedure writes through saddlebag |
| 3 closed check vocabulary | kept; the design adds one check (`winners`), one act (`race`), one parameter (`within=`) |
| 4 `rewrite` as the one intercept | kept for the browser path; Fault is a second path, not a second effect on the same path |
| 5 descriptive environment | reshaped: one bullet, `stand-ins:`, read at run time |
| 6 concept, feature doc, cli | kept; Playbook and Reference are new types because none of the three holds a procedure or a borrowed spec |
| 7 serve stopped at scenario end, teardown never run | re-derived: `release` is the teardown kind with a reason to run |
| 8 forwarder as JSON map | re-derived as the private-network Residence adapter; it also hosts Fault rules |
| 9 QA across environments | Recipe and Facility check reused; Lease split into Borrow and Return; Tap kept beside Side observation; Watch port, Allowance untouched |
| 10 testing skills lack the four topics | one new library skill, resilience testing, sits beside testing-design and points at the stack skills for fakes |
| 11 `observe:` on data states | re-derived: the same key points at a Side observation |

### SOLID check

- Single responsibility: every Owns above reads without "and", except Playbook, whose "ordered
  steps, each runnable or manual" is one responsibility with two step kinds. Kept.
- Open/closed: a new Fault variant is one rule class in the proxy and one word in the step's
  vocabulary. A new Stand-in variant is one adapter and one word on the environment page. A new
  Residence is one path and one word.
- Liskov: each Fault variant is a rule; none extends another. Emulator, mock and none are each a
  Stand-in, not a kind of each other.
- Interface segregation: a Recipe step asks a Resource for its address and its borrow facts. It
  never sees the probe or the observations.
- Dependency inversion: Recipe's Never-knows names checks, and Fault's names the app. Neither
  names a variant.

### Open lookups

1. Does the sandbox forwarder sit on the path of every call the app makes to a host upstream, or
   only on ports the run configured? Decides whether Fault rules on the forwarder reach the
   app's dependency without a second proxy. Resolved in section 5.
2. Does `conflict_on_stale` already express "the loser was told"? Decides whether Winner count
   needs a companion check. Resolved in section 5.
3. Does the harness have a scenario-end hook that runs for a timed-out scenario? Decides whether
   Return rides on the `serve` stop or needs a new moment. Resolved in section 5.
4. Does floci expose a fault or chaos control plane? Decides whether Fault rules may delegate to
   the emulator for cloud services. Could not resolve from the product page (A4).
5. Can the sandbox container reach the host's private network interface? Decides Residence's
   private-network path (A1).

## 5. Mapping onto the existing system

### Revision log

- **R8.** Section 5 claims table, section 5b, S1: the `ostler checks` count the note carried was
  27, measured before the vocabulary grew; `uv run ostler checks` on main lists 33, and the slice
  adds none. The S1 done-when named the count check's parameter `count=`; the vocabulary's is
  `equals=`. Section 3 Borrow and Return: a release registers when the borrow succeeds and reads
  the fixture's facts as they stand when the scenario ends, so a scenario that dies between the
  borrow and the release step still releases, which is invariant 1's point.
- **R7.** Section 1, section 2 Arranging and Checking, invariant 3, section 4 Proxy and
  Mark, S9, S10: added Proxy as a role after the reviewer named faults on a mobile app's
  outbound calls, which never pass the forwarder; and folded the earlier note's Tap into Side
  observation with a Mark after the reviewer named the tailing tools a team runs on a shared
  development environment. Invariant 3 is restated so a fault may sit in front of a real resource
  as long as nothing altered reaches it.
- **R6.** Section 1, section 2 Describing, section 4 Reach, S8: split Reach out of Resource as a
  role with HTTP and command-line variants after the reviewer named the administrator no screen
  can create, which takes a request to one resource and a command against another in one recipe.
  The design had folded the protocol into the Resource bullet and gave a step only `run:`.
- **R5.** Section 1, section 2 Arranging, invariant 12, section 4 Clock, S7: brought Clock back
  after the reviewer named daylight saving and foreign-zone users. R1 had dropped it on the
  ground that the app's unit tests inject a clock; that clock never runs the composed app through
  a boundary, so the ground was wrong. A7 is replaced.

- **R1.** Section 2, Arranging a situation: dropped the concept Clock. The app's own tests
  inject a clock (stack skills, `python-architecture` injected clocks). A book that moved time
  would be testing the stand-in. Reversed by R5.
- **R2.** Section 4, Fault: placed the fault rules on the existing sandbox forwarder after
  lookup 1 showed it already proxies host upstreams per port. The design had a separate proxy.
- **R3.** Section 2, Describing an outside thing: split QA across environments' Lease into
  Borrow and Return after lookup 3 showed the harness's scenario-end moment stops `serve`
  processes and nothing else, so the giving back needs its own owner at that moment.
- **R4.** Section 4, Reachability probe: kept the `probe` step and its gap wording for this
  change (A6) because the skip status is QA across environments S2 and that slice is unbuilt.

### Parts

| Part | Verdict | Where, and the mismatch |
|---|---|---|
| Describing an outside thing | Reshape | Nearest is the `fixture` with a `probe` step (`fixture.md` lines 97 to 105): a capability off this machine, named by the fixture's stem. It owns the probe and nothing else: no address, no borrow, no return, no stand-in. The environment page's `services` and `backing` bullets name backing stores as prose (`environment.md`). |
| Arranging a situation | Reshape | The fixture's `## Steps` with `seed`, `run`, `serve`, `verify`. No step kind misbehaves on purpose, issues actions at once or hands a message over twice. `intercept: rewrite` edits a response to the browser only (`flow.md`). |
| Checking from the other side | Reshape | Every check reads the response, the page, the DOM or the working directory (`ostler/ostler/checks.py`). `emitted` reads the requests the page sent (`checks.py:400`), the app's front, not its effects. `observe:` exists on `data-state` and links an endpoint or command of the app (`data-state.md`). No check waits. |
| Keeping the know-how | New | No node type holds a procedure or a borrowed specification. `concept` holds rules and rationale, `plain-feature` holds narrative prose, `format` holds this app's own data shapes, `cli` holds this app's commands. |
| Answering in a session | Reshape | `ostler search`, `trace` and `reach` exist (AGENTS.md, "The book comes first"). `trace` walks the graph from a node but prints the graph's shape, not a tester's answer. The `ostler-okf` skill tells an agent to read the book before source and says nothing about outside things. |

### Concepts

| Concept | Verdict | Where, and the mismatch |
|---|---|---|
| Resource | New | `docs/services/<service>/resources/<name>.md`, file-level like `fixture`, registered in `ostler/ostler/registry.py` beside it. |
| Reach | Reshape, revised (R6) | The command-line variant is the fixture's `run:` step, bash with secrets and facts in its environment (`fixture.md`, Steps). The HTTP variant has no step form: a fixture today reaches an API through `curl` inside `run:`, so its response is parsed by hand and no check reads it. The http driver's `body` and `header` acts (`acts.py`) and `plan_reads` serve `request:` unchanged. `on:` is new in `registry.py`. |
| Reachability probe | Exists, revised (R4) | The `probe` step kind and the gap it yields (`fixture.md:97-105`, `step.md:16`). Owns and never-knows match. `fixture-probe-local` already refuses a probe of localhost, which is invariant 3's neighbour. |
| Borrow | Reshape | A `seed` or `run` step today, with its facts under `provides:`. It needs its own kind so Return can find its partner. |
| Return | New, revised (R3) | The `teardown` kind is declared in `registry.py:186` and never run. The scenario-end moment that stops `serve` process groups (`fixture.md:83-91`) is where `release` steps run. |
| Stand-in | Reshape | `stack.yml` services already are the emulator variant (`ostler-cli/references/stack.md`). A `serve` step already is the mock variant. Nothing names which a resource has in which environment; the environment page gains `stand-ins:`. |
| Residence | Reshape | The forwarder (`ostler/docker/sandbox/forwarder.py`, `OSTLER_SANDBOX_FORWARD`) is the private-network path. The book never states a residence, so a run configures the map by hand. |
| Recipe | Exists | A fixture's `## Steps` (`fixture.md:77-114`). Owns and never-knows match. |
| Fault | New, revised (R2, R7) | A `kind: fault` step in `registry.py`; the rules live on the Proxy. The compiler refuses it on a party with no proxy. |
| Proxy | Reshape, revised (R7) | The forwarder variant is `forwarder.py`, which already relays one local port to one host and port per entry (lookup 1: it is on the path only for ports the map names, so a resource's reach must name the forwarded port, and the stack's upstream URL must point at it); it gains the rules. The device proxy variant is new; its set and clear steps reuse the device steps fixtures already run (`fixture.md`, device sign-in). |
| Contention | New | `race` act in `ostler/ostler/acts.py`, http driver only, beside `body` and `header`. |
| Redelivery | Exists | A `kind: run` step calling the emulator's CLI. No change. |
| Clock | New, revised (R5) | The browser context is created with viewport, permissions and video only (`ostler/ostler/qa/harness/ostler_qa_browser.py:239`): no `timezone_id`, no `locale`, no clock install. A stack service's `environment:` is fixed at bring-up per copy (stack reference, "Services"), so a per-scenario instant needs the preload's timestamp file or the app's seam. A `kind: clock` step in `registry.py`. |
| Side observation | Reshape | `observe:` on `data-state` links an endpoint or command of the app. It gains the `@<resource>.<observation>` target. Checks `count`, `json_path`, `created`, `absent` read the printed JSON through the same `plan_reads` they use for a response. |
| Eventual read | New | A `within` keyword on every `CheckSpec` whose `observes` is `subject` or `subject-pair` (`checks.py`), and a retry loop in the harness's read. |
| Winner count | New | One `CheckSpec`, `winners`, http only. Lookup 2: `conflict_on_stale` (`checks.py:482`) reads one response for the stale-write refusal; it is the loser's check, so Winner count stays. |
| Idempotent effect | Exists | `count` with `within=` on a Side observation. |
| Mark | New | `cursor:` on an observation and the `since=` binding in the harness's observation read. A tail tool itself needs nothing: it is a Resource page with an HTTP or command-line reach. |
| Playbook | New | `docs/services/<service>/playbooks/<name>.md`, file-level, `## Steps` grammar extended with `do:` and `see:` for manual steps. `ostler playbook run` in the ostler CLI. |
| Reference | New | `docs/services/<service>/references/<name>.md`, file-level, `## Uses` section. |
| Credential procedure | Reshape | The runbook's `secrets: NAME: <shell>` recipe mints at bring-up (`runbook.md`) and saddlebag holds values by name (saddlebag skill, "Register a secret"). A playbook step with `secret:` is the same recipe, invocable on demand. |
| Provenance | New | `source:` and `checked:` bullets, a `stale-source` doctor warning. |
| Question, Answer shape | New | `ostler explain <name>` in the ostler CLI, over the graph `trace` already walks. |
| Runnable step | New | `ostler playbook run <name> --step <n>`. |

### What the existing system has that the design lacks

- **`intercept: rewrite`** on flows. Not waste: it proves a screen computed a figure, a browser
  path claim. Fault is the dependency path. Both stay.
- **Tap and Watch port** of QA across environments (unbuilt). A concept the design had missed
  and now holds (R7): a Tap is a Side observation on a tail resource, read from a Mark, and the
  Watch port is the set of tail resources the environment page says exist there. Neither needs a
  concept of its own.
- **The runbook's `secrets:` mint-at-bring-up.** Not waste: a run's secret. Credential procedure
  is the same recipe run by a person on demand. The design missed nothing; it reuses the recipe
  shape.
- **`fixture-probe-local`.** A concept the design missed: Residence *this machine* and a probe
  are contradictory, and the doctor already says so. Invariant 3 gains its sibling: a probe on
  a resource whose residence is this machine is the same finding.

### Claims against the existing system

| Claim | Existing system | Design |
|---|---|---|
| 1 | follows | follows, outcome wording per A6 |
| 2 | follows | follows |
| 3 | follows, 33 checks | follows, 33 checks and one shared parameter `within=` |
| 4 | follows | follows and adds a second path |
| 5 | follows | one run-time bullet added |
| 6 | follows | two new node types |
| 7 | serve stopped, teardown dead | release runs at the serve-stop moment |
| 8 | a hand-written map | the map derived from resource pages' residence |
| 9 | not built | Recipe, Facility check reused; Lease split; Tap and Watch port folded into Side observation, Mark and Resource |
| 10 | four topics absent | one skill added |
| 11 | app targets only | resource targets too |

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A book writer reading a gapped claim | the wording `gapped: <capability> absent` and no writer action on it | harness tests on the gap kind | wording as in `fixture.md:99-103` | unchanged until QA across environments S2 renames it (A6) |
| A book run on an existing book | every current fixture compiles and runs with no edit | the ostler test suite, client book runs | the client books pass today | no new doctor error on an untouched page; same pass count on the reference books |
| A writer reading `ostler checks` | 33 entries, each excluding one defect class | the vocabulary test | 33 | 33, and `within=` documented once in the vocabulary preamble, not per entry |
| A run on a sandbox with forwarded upstreams | relay latency and the 900 s idle timeout | nothing | unmeasured (A8) | a scenario with no `fault` step sees no added hop |
| A browser scenario today | the machine's zone and real time in the browser | nothing | the context options at `ostler_qa_browser.py:239` | unchanged when the journey has no `clock` step; a journey that has one states the parties it moved in its report |
| A stack bring-up | its duration | nothing | unmeasured (A8) | unchanged when stack.yml lists no emulator |
| `ostler doctor` on a client book | about 20 s (memory, 264cb1d6) | nothing | about 20 s | under 22 s with the new node types registered and no resource page present |
| An agent reading `ostler-okf` | one skill, its references loaded on demand | nothing | the skill's current length | the resource and playbook material is a new reference file, not SKILL.md growth |

The sandbox latency and bring-up rows are enforced by nothing and kept on purpose: they become
the "no added hop" clause of invariant 3's neighbour, owned by Fault: a fault rule exists only
while a scenario that declared it runs.

## 6. Slices

1. **S1. Borrow the camera, play the video, prove it from the camera.** The walking skeleton.
   - Touches: Resource, Residence (private network), Reachability probe, Borrow, Return, Recipe,
     Side observation, Eventual read; `ostler explain` in its first form (print the page and its
     journeys).
   - Done when: a book holds `resources/camera.md` and `resources/camera-booking.md`; a journey
     needs the camera, posts to the app's play endpoint, and claims
     `observe: @camera.recordings` with `count(subject="items", equals=1, within=30)`. On a
     machine whose host reaches the booking service the journey passes and the release step ran.
     On a machine that does not, the journey is gapped with the resource's name. A scenario
     forced to fail after the borrow still releases, shown by the booking service's lease list
     being empty afterwards. 5b rows: gapped wording unchanged, reference books' pass count
     unchanged, `ostler checks` at 33 entries plus the `within=` preamble, doctor under 22 s.
     Landed 2026-10-28 on the http and cli compilers. The playwright and maestro compilers still
     refuse a `verify:` row held on an `observe:` as unobservable, so a browser journey's side
     observation lands with S2. The doctor budget was measured by profile on a machine at load
     average 18: the slice's checks cost 0.36 s of a run, wall time was not comparable that day.
2. **S2. Stand-ins and the emulator: a duplicate message, one effect.**
   - Touches: Stand-in (emulator, mock, none), environment `stand-ins:`, Redelivery, Idempotent
     effect.
   - Done when: `stack.yml` lists a floci service, the environment page names it as the queue's
     stand-in, a recipe publishes one message twice to it, and the journey's
     `count(..., within=)` on the consumer's side observation reads one. On an environment with
     no stand-in and no real queue, the journey is gapped. 5b: bring-up unchanged on a stack
     with no emulator listed.
3. **S3. A dependency that times out.**
   - Touches: Fault with the timeout, refuse and cut variants; Proxy's stack forwarder variant;
     the compiler's refusal of a fault on a party with no proxy.
   - Done when: a journey with `kind: fault on=payment-provider mode=timeout` sees the app's
     documented behaviour (its retry state or its 503 body), the rule is gone when the scenario
     ends, and a scenario with no fault step shows no added hop (5b: measured by comparing one
     request's latency through the forwarder before and after this slice).
4. **S4. Two writers, one winner.**
   - Touches: Contention (`race`), Winner count (`winners`), `conflict_on_stale` as the loser's
     check, on a table stand-in with conditional writes.
   - Done when: a journey races two writes and claims `winners(count=1)` and the loser's
     `conflict_on_stale`, passing on the emulator and gapped where no table exists. 5b: `ostler
     checks` at 28 entries.
5. **S5. The team's know-how: playbooks, references, a minted credential.**
   - Touches: Playbook, Reference, Credential procedure, Provenance, `ostler playbook run`,
     the `stale-source` warning.
   - Done when: a Confluence procedure is a playbook page with runnable and manual steps that
     `ostler playbook run` walks, stopping at the manual ones; a vendor OpenAPI document is a
     reference page whose `## Uses` link the resource; a credential playbook mints a test token
     into saddlebag by name and the transcript holds no value. 5b: the existing runbook
     `secrets:` recipes still mint at bring-up.
6. **S6. Answering in a session.**
   - Touches: Question, Answer shape, Runnable step, `ostler explain` complete; the `ostler-okf`
     reference file for resources and playbooks; the library skill for resilience testing
     (event handlers, faults, contention on a NoSQL record, hardware fakes) that points at the
     stack skills for the fake mechanics.
   - Done when: in a fresh chat session on a client repo, an agent asked "how do I test the
     camera flow" answers in the fixed shape, and its transcript shows `ostler explain` and page
     reads only, no source read. 5b: `ostler-okf` SKILL.md length unchanged.

7. **S7. The night the clocks go back, seen from Tokyo.**
   - Touches: Clock with the browser and process variants, the environment page's `clocks:`,
     invariant 12.
   - Done when: a journey sets the browser to Tokyo at an instant inside the server zone's
     repeated hour, books a slot through the screen, and claims the screen's rendered time and
     the app's stored instant from the API; a second journey moves the app's process clock across
     the boundary and claims a deadline the app computes. On an environment whose app has no
     clock variant, the second journey is gapped. 5b: a journey with no clock step runs with the
     context options it has today.

8. **S8. The administrator no screen can create.** After S2.
   - Touches: Reach with both variants, `on:`, `request:`, a `data-state` reached by fixture,
     Credential procedure for the identity provider's management token.
   - Done when: a recipe sends `request: POST /api/v2/users` on the identity provider, binds the
     returned id, runs the table vendor's CLI `on:` the users table stand-in to insert the
     administrator row, and the journey signs in as that user and reaches the administrator
     screen. The management token comes from saddlebag by name and the transcript holds no
     value. On an environment with no identity provider tenant, the journey is gapped with the
     provider's name. 5b: existing fixtures with `run:` compile unchanged.

9. **S9. What the app published, caught by the tail on the development environment.**
   - Touches: Mark, Side observation on a tail resource, Reach (HTTP for a tail that serves,
     command line for one that prints), Resource's environments.
   - Done when: the development environment page lists the event tail and the table tail as
     resources that exist there and nowhere local; a journey acts on the app and claims
     `observe: @event-tail.caught` with `count(subject="$[?(@.detail-type=='OrderPlaced')]",
     equals=1, within=20)`, which reads from the mark taken when the scenario began; run twice in
     a row the count is still one. Locally the journey is gapped under the tail's name. 5b:
     reference books' pass count unchanged.
10. **S10. The phone's backend refuses.**
    - Touches: Proxy's device proxy variant, Fault's refuse and cut variants on it, the
      environment page's `proxies:`, and the proxy's `caught` observation, so the same journey
      also claims the request the app sent.
    - Done when: a mobile journey with `kind: fault on=api mode=refuse` sees the app's documented
      offline screen, the device's proxy setting is cleared when the scenario ends whatever the
      verdict, and a scenario with no fault step leaves the device's network settings untouched.
      On a build that pins certificates the journey is gapped (A15).

## 7. Assumptions

1. **Assumption:** the machine that runs the harness is a node of the private network, so the
   host forwarder reaches the booking service and the camera.
   **Decided:** Residence's private-network variant is the forwarder, not a network client in
   the sandbox.
   **Basis:** the request says the API is reached through a tailnet; nothing on the sandbox path.
   **If wrong:** section 4 Residence, section 5 Residence, S1. A client inside the sandbox
   replaces the forwarder for that variant.
2. **Assumption:** the camera or its booking service can be asked what it recorded.
   **Decided:** the camera journey checks a Side observation.
   **Basis:** none.
   **If wrong:** S1's done-when, and the camera journey takes a Tap instead, which is QA across
   environments S4.
3. **Assumption:** the app reaches each dependency through a configurable upstream address, so a
   stand-in and a fault proxy can sit in its place.
   **Decided:** Stand-in and Fault need no change in the app.
   **Basis:** QA across environments A-list, which states the same about client stacks.
   **If wrong:** invariant 11 and S2, S3. The app gains a configuration seam first.
4. **Assumption:** floci's emulated SQS and DynamoDB accept the AWS CLI with an endpoint URL, and
   floci offers no fault control plane.
   **Decided:** Redelivery uses the AWS CLI; Fault never delegates to the emulator.
   **Basis:** the floci.io page lists 126 AWS services and a CLI; it says nothing of chaos.
   **If wrong on the second half:** section 4 Fault gains a fourth variant source. Nothing else
   moves.
5. **Assumption:** `conflict_on_stale` is the right loser's check for a conditional write that
   lost a race.
   **Decided:** Winner count is the only new check for contention.
   **Basis:** `checks.py:482` names the stale-write refusal.
   **If wrong:** S4 adds one check for the loser's refusal, and the vocabulary count in 5b moves
   to 29.
6. **Assumption:** the `gapped: <name> absent` wording stays until QA across environments S2
   introduces the skipped status.
   **Decided:** this design reports an absent resource as gapped.
   **Basis:** the status change belongs to that note.
   **If wrong:** invariant 2's wording and the first 5b row.
7. **Assumption:** the pinned Playwright carries the clock API and the context's zone and locale
   options, and what the user sees of time comes from the browser.
   **Decided:** the browser clock is the first Clock variant and covers S7's first journey with
   no change to the app.
   **Basis:** Playwright has shipped `clock` since 1.45 and `timezone_id` for years; the harness
   already drives it (`ostler_qa_browser.py`).
   **If wrong:** section 4 Clock loses its browser variant and S7 needs the app seam first.
8. **Assumption:** the forwarder's added latency and a bring-up's duration are small enough that
   nobody measured them.
   **Decided:** 5b keeps them as "no added hop" and "unchanged with no emulator".
   **Basis:** none.
   **If wrong:** S3's done-when measures them first.
9. **Assumption:** a playbook or reference not checked against its source for 90 days is stale.
   **Decided:** the `stale-source` warning fires at 90 days.
   **Basis:** none.
   **If wrong:** one number in Provenance.
10. **Assumption:** the chat agent has `ostler` on its path in the client repository, because
    farrier installs the skills that tell it to run `ostler explain`.
    **Decided:** Answering is a CLI command plus a skill sentence, not a chat-only text.
    **Basis:** the stablemate install and the `ostler-okf` skill both assume it today.
    **If wrong:** S6's done-when, and the skill carries the answer shape as prose for a session
    without the CLI.
11. **Assumption:** resource, playbook and reference pages belong to the service whose app
    depends on them, under that service's folder.
    **Decided:** the three folders sit under `docs/services/<service>/`.
    **Basis:** `service-spans-repositories` already binds a service to one repository.
    **If wrong:** a shared `docs/resources/` root, and invariant 8's search is unchanged.
12. **Assumption:** the app's runtime takes a C-library time preload, and its container image
    can carry it.
    **Decided:** the process clock variant exists and reads its instant from a file.
    **Basis:** none for any given client app; Go and Java runtimes are known not to take it.
    **If wrong:** the app has no process clock variant; S7's second journey is gapped there until
    the app documents a seam, which is the third variant and the app's own change.
13. **Assumption:** the identity provider exposes a management API over HTTP whose token a
    command-line procedure can mint, and offers a test tenant the run may write to.
    **Decided:** S8 reaches it through the HTTP variant with a Credential procedure, and treats a
    missing tenant as a gap.
    **Basis:** the request's own words; the common hosted providers work this way.
    **If wrong:** S8's recipe uses the provider's CLI as its reach, and nothing else moves.
14. **Assumption:** each tail tool can report its current position and read from a given one.
    **Decided:** Mark is a `cursor:` plus a `since=` the harness passes.
    **Basis:** none; the request names the tools and not their interfaces.
    **If wrong:** Mark becomes a timestamp the harness takes, and the observation filters on the
    event's own time field, which is one `json_path` filter more per claim.
15. **Assumption:** the mobile test build trusts a user-installed certificate authority and does
    not pin the backend's certificate.
    **Decided:** the device proxy variant terminates TLS with the host's authority.
    **Basis:** none; a release build normally pins.
    **If wrong:** S10 is gapped on that build until the app ships a test flavour that trusts the
    proxy, which is the app's own change.
