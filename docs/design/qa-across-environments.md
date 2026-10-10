# QA across environments

**Disclosure.** I wrote this note after a long session inside the existing system. I had
read the node types for environments, runbooks and fixtures, the page compiler, and a client
book's fixtures. Those design decisions are listed as claims in section 1b. I checked each
part and concept below against the question "would I have named this without having seen
the solution?" The checks that failed are named where they occur.

## 1. Problem

A team writes one book of QA journeys for its web app. Today those journeys run only on the
developer's machine. Run on the shared dev deployment or on production, they fail at the
first setup step. They fail because the setup calls a local sign-in emulator with a fake key
and posts to a local address. Nothing tells the tester which journeys are safe to run where,
so pointing the book at production risks changing real customers' data. A journey also sees
only the screen. It cannot tell whether the app published the order event, wrote the invoice
file or called the email provider, so a journey passes while the work behind the screen
never happened.

**Done**, as the tester sees it:

- The tester names the environment when starting a run: local, dev or prod. The book needs
  no edit to switch.
- The QA tool treats every environment as already running, local included. It never starts,
  deploys or provisions one. It only acts on it and watches it.
- Local runs what dev runs. The workflow builds it before the run from the same
  infrastructure code that deploys dev and prod, applied to emulators. A service missing on
  local is a defect in that build, not a reason to skip.
- Each journey that can run there runs. It uses that environment's addresses, its way of
  signing in and its way of getting test data.
- Each journey that cannot run there is reported as skipped, with the reason. It never
  counts as failed. On local, the only reasons are the pieces an emulator cannot stand in
  for, and the environment page names each one.
- Where the environment offers a way to watch, a journey checks what the app did behind the
  screen: the events it published, the records it changed, the calls it made out and the
  files it wrote.
- On production, no journey changes data that the run did not create for itself.
- The local run keeps its current results: the same journeys pass.
- A web app, an HTTP API, a CLI and a desktop app are described the same way. Only the
  ports differ.

**Out of scope:**

- deploying dev and prod, which their pipelines already do;
- the QA tool starting anything: the workflow builds local before the run, and the QA tool
  only checks that it answers;
- storing secrets, which a credential store outside the repository already does;
- cleaning up production data the run did not create;
- native mobile drivers;
- load and performance testing;
- choosing which stories to QA.

## 1b. Claims

These are design decisions that reached me through the existing system before this note.

1. An environment page lists addresses, services, backing stores and whether it is
   local-only. It is descriptive. Its claims compile to nothing. (node type `environment`)
2. A runbook names a driver, an environment, an entry URL, a health path, reuse, secrets and
   steps. Bring-up picks the environment marked local-only. (node type `runbook`)
3. A fixture is one unit holding what it provides and the steps that make it: args,
   provides, needs, secrets, lifetime, and steps of kind seed, run, serve, verify or probe.
   (node type `fixture`)
4. A step refers to other values only as `@fixture.key` or `$captured`. Nothing refers to an
   environment's values. (fixture steps)
5. Each environment page owns its addresses, sign-in, test accounts and how to create and
   retire test data. Fixtures and walks refer to them by name. The run chooses the
   environment. Each fixture declares where it is safe. Unsafe fixtures are skipped on prod,
   not failed. (my own recommendation earlier in this session)
6. The compiler records, per fixture, the screen its browser steps open. A page scenario
   skips the walk only when that screen is its own. (page compiler)
7. A navigation walk to a screen behind sign-in replays the sign-in hop, which fills in the
   seeded account's credentials. (page compiler)
8. A book run brings up its stack from a runbook before it runs scenarios. (workflow
   `bring_up_stack`)
9. An undeclared side effect that a tap observes fails the journey on local and dev. (my own
   recommendation earlier in this session, which the user did not contest)
10. A service the local stack does not run, such as video storage, skips the journeys that
    need it. An `offers:` bullet on the environment names what it runs. (my own first S1)

## 2. Parts and concepts

### Level 1: parts

1. **Describing an environment.** It owns what one place the app already runs offers to a
   tester: where a test acts on the app, where it can watch the app, how a tester gets in,
   what test-data facilities exist, and what a test may do there. It never knows any journey,
   and it never knows how the place was started. It hands its description to *choosing the
   setup*, to *deciding what may run* and to *watching the app*.
2. **Stating what a journey needs and does.** It owns, per journey, the conditions that must
   hold before it starts and the effects it has on the world. It states both in the domain's
   words, independent of any environment. It never knows how a condition is produced. It
   hands the needs to *choosing the setup* and the effects to *deciding what may run*.
3. **Choosing the setup.** It owns, for one environment, the way each need is satisfied,
   and the giving back of what that way took. It never knows the journeys' steps. It hands
   a ready setup, with its values, to *running and reporting*.
4. **Deciding what may run.** It owns the verdict per journey and environment: run, or skip
   with a reason. It never knows how a setup is made. It hands the verdicts to *running and
   reporting*.
5. **Watching the app.** It owns seeing what the app did behind its surface while a journey
   ran: the events it published, the records it changed, the calls it made out and the files
   it wrote. It never knows the journey's steps, or how the environment was deployed. It hands
   the observed effects to *running and reporting*, which sets them against the journey's
   declared effects.
6. **Running and reporting.** It owns the choice of environment for a run, performing each
   allowed journey, and the report. It never knows any environment's details beyond the
   values it is handed.

**Flow.** At the start of a run, *running and reporting* names the environment and confirms
that it answers. It starts nothing. *Deciding
what may run* reads that environment's allowances and each journey's effects and needs. It
skips the journeys the environment cannot serve or does not allow. For each remaining
journey, *deciding what may run* confirms the facilities its recipes need, and skips the
journey when one does not answer. Then *choosing the setup* picks the way that environment
satisfies each need, performs it, and hands back the values the journey uses. *Watching the
app* opens the taps the environment offers. *Running and reporting* performs the journey,
closes the taps, and compares what they saw with the journey's declared effects. It records
passed, failed or skipped. At the end of each need's lifetime,
*choosing the setup* gives back what it took. That happens after the journey, or after the
run, even when the journey failed.

**Split test.** In plain words: each place the app runs has a page saying where to act on
it, where to watch it, how to get in, how to get test data there, and what is forbidden
there. Each journey says what it needs and what it changes. At the start of a run you name
the place, which is already running. The run skips what that place cannot do or forbids,
gets test data the place's own way, runs the rest while watching what the app does, and
cleans up after itself. Two code bases fit this: one that compiles a plan ahead of time, and
one that decides each journey live. No part carries the name of an existing stage. Part 3
nearly took the name "fixture", which is the existing unit. I named it for the decision it
makes instead.

### Level 2: concepts

**Describing an environment**

| Concept | Owns | Never knows |
|---|---|---|
| Environment | its name and whether it is the reference environment every need must work in | journeys, needs |
| Drive port | where a test acts on one surface: a URL for a web app or an HTTP API, a launch command for a CLI or a desktop app (revised, R5) | how a journey uses it |
| Watch port | where one tap attaches: a proxy the app's outbound calls pass through, an event bus subscription, a change stream, a directory (new, R6) | what a tap does with it |
| Access | how a tester signs in there, naming each credential by its secret name | the secret values |
| Facility | one service or test-data facility the environment runs, such as a sign-in emulator, a pool of test accounts or an inbox the tester can read, read from the environment's own service list (revised, R9) | which need uses it |
| Allowance | one kind of effect a test may have there | which journey has it |
| Health check | confirming the environment answers before a run starts (revised, R1, R5) | how it was started |

**Stating what a journey needs and does**

| Concept | Owns | Never knows |
|---|---|---|
| Need | one condition a journey requires before it starts, the values it promises, and where it leaves the browser | how any environment satisfies it |
| Effect | one change an action causes, by kind and by whose data it touches, declared once on the endpoint or command that causes it. A journey's effects are those of the actions its steps reach. (revised, R10) | which environments allow it |

**Choosing the setup**

| Concept | Owns | Never knows |
|---|---|---|
| Recipe | one way to satisfy one need, with the facilities it requires | other recipes, journeys |
| Recipe choice | which recipe serves a need in the named environment, or that none does | the recipe's steps |
| Reference | turning a name in a recipe or journey into a value: an address, a need's promised value, a captured value or a secret | where the secret is stored |
| Lease | what a recipe took or made, and its giving back at the end of the lifetime | the journey that used it |

**Deciding what may run**

| Concept | Owns | Never knows |
|---|---|---|
| Verdict | run or skip, per journey and environment | how a recipe works |
| Skip reason | the missing facility or the forbidden effect a skip names | the report's layout |
| Facility check | confirming at run time that a facility a chosen recipe requires answers, so a missing one becomes a skip and not a failure (revised, R2) | the recipe's steps |

**Watching the app** (new, R6)

| Concept | Owns | Never knows |
|---|---|---|
| Tap | recording one kind of side effect from its watch port between open and close | the journey, the other taps |
| Observed effect | one thing a tap saw, in the same effect kinds a journey declares | which tap saw it |
| Effect match | pairing the observed effects with a journey's declared effects, and naming the undeclared and the missing | how a tap records |

**Running and reporting**

| Concept | Owns | Never knows |
|---|---|---|
| Run target | the one environment a run is aimed at | any environment's details |
| Journey run | performing one allowed journey with its resolved values | how the values were made |
| Report | each journey's outcome, passed, failed or skipped, with the run target named | why a journey was skipped beyond its reason |

Starting the local stack is not a concept here. The workflow builds it before a run from the
infrastructure code a deploy pipeline applies to dev. The QA tool sees the result through the
Health check (R5, R8).

**Shared values.** Two vocabularies cross parts. Each is a read-only catalog every part
consults, not a sign the split is wrong:

- **Facility kinds** cross *describing an environment* and *choosing the setup*.
  Environments offer them and recipes require them.
- **Effect kinds** cross *describing an environment*, *stating what a journey needs and
  does* and *watching the app*. Environments allow them, journeys have them and taps observe
  them.

## 3. Invariants

1. **A journey never runs where one of its effects is not allowed.** Owner: Verdict. Effect
   and Allowance uphold it by being declared.
2. **On a non-reference environment, a journey only changes data its own needs created or
   leased in this run.** Owner: Verdict, which refuses an effect on shared data where the
   environment does not allow it. This depends on declared effects being honest (A2).
3. **Every need has a recipe in the reference environment.** The book therefore always runs
   in full locally. Owner: Recipe choice. It detects the gap when the book is checked, not
   when a run starts.
4. **Every recipe of a need delivers what the need promises:** the same values, and the
   browser left in the same place. Owner: Need. It checks the promised values and the
   landing after any recipe runs. Recipe upholds it.
5. **The book carries no secret values.** Owner: Access, which only names secrets.
6. **Switching the run target changes no page of the book.** Owner: Reference. It refuses a
   literal address or credential in a recipe or a journey when an Address or Access already
   names it.
7. **Everything a recipe took is given back at the end of its lifetime, even after a
   failure.** Owner: Lease.
8. **A skipped journey counts as neither passed nor failed.** Owner: Report. Every count a
   later step reads, such as the failures the writer is sent, excludes skips. (revised, R4)
9. **The QA tool never starts, deploys or stops an environment.** Owner: Health check, which
   is the only thing the run does to an environment before its journeys. (R5)
10. **On an environment that is not prod, a side effect a tap observes and the journey did
    not declare fails that journey.** Owner: Effect match. Prod decides what may run from
    declarations these environments have already confirmed. (R7, A2)
11. **A tap only reads.** It changes nothing the app sees, apart from the latency of a
    proxy. Owner: Tap.

## 4. Forces and patterns

### Forces

1. **F1.** The way to satisfy a need varies by environment. It varies independently of the
   need and of the journey. For example, a fresh customer account comes from the sign-in
   emulator locally, from a test-account pool on dev, and from that pool on prod.
2. **F2.** Addresses and sign-in vary by environment. They are values, not behaviour.
3. **F3.** What a test may do varies by environment. Production forbids touching shared
   data, sending real email and spending money.
4. **F4.** The set of environments grows. A staging or a per-change preview deployment
   arrives without anyone revisiting the journeys.
5. **F5.** A test of the run must aim it at a fake environment.
6. **F6.** Secrets stay out of the book. Their values arrive at run time.
7. **F7.** The local run must stay complete and cheap. Partial coverage on prod is
   acceptable.
8. **F8.** Getting past sign-in varies by environment, like any other need.
9. **F9.** How a side effect can be seen varies by the app's stack, not by the journey: an
   outbound HTTP call, an event bus, a database change stream, a file. The set of stacks
   grows.
10. **F10.** Every environment is already running when a run starts. Local is built by the
    workflow, dev and prod by their deploy pipelines. The QA tool must work the same on all
    three.
11. **F11.** The surface a test drives varies by the kind of app: a browser, an HTTP client, a
    process with arguments and output.
12. **F12.** Local differs from dev only by the settings of one infrastructure program and by
    the pieces an emulator cannot run. Those pieces are few and named. (R8)

### Between parts

- **One value handed along (F5).** The run target is an input to the run. Every later
  decision reads it from the value it is handed, so a test hands in a fake environment.
- **A sequence of decide, set up, run, give back (F3, F7).** The verdict comes before any
  setup, so a forbidden journey never touches the environment at all.
- **Values fixed per run target (F2, F5).** Reference resolves addresses when the plan is
  built for one run target, so the built plan stays literal and readable. A shell step
  receives the addresses as environment variables, the way it already receives its
  arguments and secrets. (revised, R3)

### Inside a part

- **Need is a role, Recipe a variant, Recipe choice made by the run target (F1, F4).** The
  role is named for what the journey asks for: "a customer account, signed in". The local
  emulator recipe is one variant among others. It is not the base the others extend.
- **Choice by facility, not by environment name (F4).** A recipe declares the facilities it
  requires. An environment's service list names the facilities it runs. Recipe choice takes
  the book's preferred recipe among those whose facilities the environment runs. A new
  environment that runs a test-account pool picks up every pool recipe with no edit. No
  second list of offers exists to disagree with the first. (R9)
- **Address and Access are plain values looked up by name (F2, F6).** No pattern is
  needed. Reference resolves `env.<name>` from the run target's environment, and secret
  names from the credential store.
- **Verdict is a plain function (F3).** It compares two sets: the journey's effects against
  the environment's allowances, and the needs' required facilities against those it runs.
- **Lease is a scoped resource (F7).** Giving back runs when the lifetime ends, whatever the
  outcome.
- **Sign-in is a Need (F8).** A walk to a screen behind sign-in states the need "signed in
  as a tester". Each environment satisfies it through its own recipe.
- **Tap is a role, each tap kind a variant (F9).** The role is named for what Effect match
  asks of it: open, close, and the effects seen in between. HTTP proxy, event bus, change
  stream and filesystem are variants. The environment's watch ports choose which variants a
  run opens. A new stack adds one variant and changes no journey.
- **Drive port is a plain value with a kind (F11).** The kind picks the driver that already
  exists for it: the browser, the HTTP client or a process runner. A CLI or a desktop app
  needs only the launch command and the filesystem tap, which makes it the simpler case.
- **Health check is a plain function (F10).** It asks each drive port whether it answers.

### Claims

1. Rejected. Under F2 an environment must be operative, not descriptive.
2. Rejected. Under F5 the run names its target. The local environment stays the default.
3. Reshaped. Under F1 a fixture's "provides" becomes the Need, and its steps become one
   Recipe: the reference environment's.
4. Extended. Under F2 a step may also refer to an environment's addresses.
5. Re-derived, except for "each fixture declares where it is safe". That would be a list of
   environment names on every fixture, edited each time an environment arrives, which F4
   forbids. Safety follows from effects against allowances and facilities against the services it runs
   instead.
6. Out of scope. Invariant 4 makes it moot across environments, because every recipe of a
   need leaves the browser where the need promises.
7. Rejected. Under F8, credentials in a navigation hop tie the walk to one environment.
8. Rejected. Under F10 the workflow builds the local stack before the run, and the QA tool
   only checks that it answers.
9. Re-derived from F9 and invariant 2: without a tap that checks them, declared effects rest
   on the writer's honesty, and the prod verdict rests on those declarations.
10. Rejected. Under F12 a service local lacks is a gap in its build, and the build closes it.
    The prototype served video from emulator storage the infrastructure program seeded (R8).
    A skip stays only for a piece no emulator runs, and Facility reads it from the existing
    service list (R9).

### SOLID check

- **Single responsibility.** Each concept owns one responsibility, with no "and". Need owns
  one promise: its values and its landing are parts of the same promise. Effect match pairs
  and names in one pass, and the names are the result of the pairing.
- **Open/closed.** A new environment adds one environment page and, where needed, a recipe.
  A new recipe adds one recipe and nothing at the choice. Either passes.
- **Liskov substitution.** Each recipe is a kind of Need fulfilment only. The emulator recipe
  is not a parent of the pool recipe. Each tap kind is a Tap only. This passes.
- **Interface segregation.** The journey asks a Need only for its promised values. This
  passes.
- **Dependency inversion.** Journey run's never-knows names how values were made, so it
  depends on the Need alone. Effect match's never-knows names how a tap records. This
  passes.

### Open lookups

- **L1.** Do the environment, runbook and fixture node types already carry any of Address,
  Access, Facility or Allowance in an operative form? This decides whether those concepts
  are Exists, Reshape or New.
- **L2.** How does a run pick its environment today, and can a run be pointed elsewhere?
  This decides Run target.
- **L3.** How are fixture references and secrets resolved at run time? This decides
  Reference.
- **L4.** Where do the sign-in hop's credentials come from? This decides claim 7's
  migration.
- **L5.** Does the report know "skipped"? This decides Report and invariant 8.
- **L6.** Which fixture lifetimes exist, and is there any giving back? This decides Lease.
- **L7.** Does anything declare a journey's effects today? This decides Effect.

## 5. Mapping onto the existing system

### Revision log

- **R1.** Section 2, *describing an environment*: added **Readiness**. Local starts its
  stack from a runbook, while dev and prod are already up and only need a health check. The
  runbook's bring-up exists and assumes a stack it can start (`ostler/qa/runbook.py:259-264`).
- **R2.** Section 2, *deciding what may run*: added **Facility check**. The probe step kind
  already classes a missing capability apart from a defect
  (`ostler/qa/harness/ostler_qa.py:1013`). A facility that is declared but absent at run time
  must become a skip, not a failure.
- **R3.** Section 4, *between parts*: Reference fixes addresses per run target when the plan
  is built. The built plan carries the base URL as a literal (`ostler/qa/compile_page.py:217`,
  `ostler/reach.py:238-247`). Shell steps get no substitution, only environment variables
  (`ostler/qa/harness/ostler_qa.py:976-1016`).
- **R4.** Section 3, invariant 8: every count a later step reads excludes skips. The
  workflow counts every status other than passed as failed
  (`workflows/.../okf_book/shared/scenarios.py:180`).
- **R5.** Section 2, *describing an environment*: Readiness became **Health check**, and
  Address became **Drive port**, from the user's direction that an environment is something
  already deployed. Starting the local stack moves to the workflow, which already does it as
  its own state (`workflows/.../okf_book/main/exercise_book_flow.py:37`). Invariant 9 added.
- **R6.** Section 2: added the part *watching the app*, with Tap, Observed effect and Effect
  match, and the concept **Watch port**, from the user's direction to hook in as a proxy on
  HTTP calls, an event bus, a change stream or the filesystem. Nothing records a side effect
  today. The harness intercepts no request (no `route(` in `ostler/qa/harness`).
- **R7.** Section 3: invariant 10, from claim 9. The user did not contest it, and the prod
  verdict depends on it (A2).
- **R8.** Section 1, F12 and S1: local runs what dev runs. A prototype on a client stack
  applied the client's own infrastructure program to a single-container cloud emulator as a
  `local` stack. It created the buckets, service accounts and IAM bindings, and uploaded the
  test videos as objects the program declares. The app's own code then listed those videos
  where it had answered 503. A fresh apply takes about 20 seconds. A refresh against an
  emulator that restarted and forgot everything takes over 4 minutes, so the build wipes its
  state on every apply. Two pieces stayed out: the emulator answers 404 for identity
  platform config, and it runs container services only through the host's Docker socket.
  Each is a setting that defaults to prod's behaviour and is turned off on local.
- **R9.** Section 2, Facility, and claim 10: the `offers:` bullet is dropped. The
  environment's existing `services` and `backing` lists already name what it runs, and a
  second list could disagree with them. A skip is reported with the reason "local runs no
  <facility>" and opens no gate.
- **R10.** Section 2, Effect: effects move from the flow to the endpoint or command that
  causes them, because what an action causes varies per action, not per flow. Endpoints
  already carry an `emits` bullet. One client book uses it for a 503 status, so its meaning
  is fixed to "event" before S3.
- **R11.** Section 5, Drive port: every drive key moves, not only the web ones. A mobile
  app's bundle id and launch screen and a CLI's command carry the same variable as an entry
  URL. The registry reads both the runbook and the environment for one migration and flags
  the old place.

### Parts

| Part | Verdict | Where, and the mismatch |
|---|---|---|
| Describing an environment | Reshape | The `environment` node type (`ostler/registry.py:554-568`). Only `local-only` is read at run time. `services` and `backing` are read only by one doctor lint (`ostler/doctor.py:2237-2250`). |
| Stating what a journey needs and does | Reshape | Needs exist as a fixture's `provides`. Effects do not exist. |
| Choosing the setup | Reshape | The fixture unit fuses the need with its one recipe (`ostler/registry.py:739-755`, `ostler/qa/book_fixtures.py:92-138`). |
| Deciding what may run | New | Nothing decides per journey today. The compiler refuses one case, an HTTP delete on a shared fixture (`ostler/qa/compile_http.py:436-449`). |
| Watching the app | New | Nothing observes a side effect. The harness records the browser's own network, which is the app's front end, not its effects. |
| Running and reporting | Reshape | The harness runs journeys (`ostler/qa/harness/ostler_qa.py`). The run never names a target, and the report has no skipped status. |

### Concepts

| Concept | Verdict | Where, and the mismatch |
|---|---|---|
| Environment | Reshape | Exists as a node type, but descriptive. It has no reference flag. Local-only is the nearest thing. |
| Drive port | Reshape | Lives on the runbook's `entry-url` (`ostler/reach.py:238-247`), not on the environment. The environment's `services` bullet lists the same addresses as prose. The workflow passes no base URL (`workflows/.../book_compilation.py:111`). The runbook's bundle id, launch screen and CLI command move with it (R11). |
| Watch port | New | On the environment page. |
| Access | Reshape | Sign-in hops carry literal credentials from the book's acts (`ostler/qa/compile_playwright.py:144`). Secrets come from the process environment, minted by the runbook's `secrets:` recipes (`workflows/.../kit/qa/runner.py:194-221`). |
| Facility | Reshape | `services` and `backing` already name what the environment runs. They become the list a recipe's required facilities are checked against (R9). |
| Allowance | New | On the environment page. |
| Health check | Reshape | The runbook's `health-path` and `identity` bullets are the probe. They move to the environment. The runbook keeps only how to start the stack, which the workflow runs. |
| Need | Reshape | The fixture's `provides` and `provides-keys`. Its landing is inferred from the screen a step opens (`fixture_screens`), not declared. |
| Effect | Reshape | The endpoint's `emits` bullet, fixed to mean an event (R10). A journey's effects are collected from the endpoints its steps reach. The compiler's delete refusal becomes a check on a declared effect. |
| Recipe | Reshape | Today a fixture's steps. A need gets one recipe per facility set, the current steps being the reference recipe. |
| Recipe choice | New | In the harness, at fixture time. |
| Reference | Reshape | `_resolve_ref` handles `@node.key` and `$name` (`ostler/qa/harness/ostler_qa.py:883-917`). It gains an environment-address form. |
| Lease | New | Lifetimes `scenario` and `lap` exist (`ostler/qa/book_fixtures.py:136`). Nothing gives back. The `teardown` step kind is declared (`ostler/registry.py:186`) and never run. |
| Verdict | New | A plain function the harness calls before a journey's fixtures. |
| Skip reason | New | Carried on the scenario outcome. |
| Facility check | Reshape | The probe step is the mechanism. It needs to yield a skip instead of a capability fault. |
| Tap | New | One adapter per kind in `ostler/qa`. The HTTP proxy comes first: the app's outbound calls already pass through configurable upstream URLs on the client stacks. |
| Observed effect | New | Carried on the scenario's log, beside its asserts. |
| Effect match | New | In the harness, when a journey ends. |
| Run target | Reshape | `select_stack` (`ostler/qa/runbook.py:274-307`) prefers local-only, then the first name alphabetically. The only override is `ostler qa stack up --runbook`. The workflow never passes one (`workflows/.../kit/qa/runner.py:81,237`). |
| Journey run | Exists | The Qa harness. Its owns and never-knows match. |
| Report | Reshape | Scenario statuses are passed, failed and errored. `QaStatus` has no skipped (`workflows/.../kit/qa/schemas.py:10`). |

**Placement.** Node types and their bullets go in `ostler/registry.py`. Verdict, Recipe
choice, Reference and Lease go in `ostler/qa`. Run target and the report's statuses go in
`workflows/.../kit/qa` and the okf book workflow.

### What the existing system has that the design lacks

- **Environment `fixture` and `capture` bullets.** They mark arrange and capture steps on an
  environment page. They are unrelated to Facility. Waste for this problem (A10).
- **`serve` steps with `lifetime: scenario`.** A recipe step kind. The design covers it as
  part of Recipe.
- **`lap` lifetime.** A lease that outlives one journey. The design's Lease covers it.
- **The compiler's delete refusal.** A partial, inferred Effect. The design keeps the
  inference as a check that a declared effect is present, not as the only source.

### Claims against the existing system

| Claim | Existing system | Design |
|---|---|---|
| 1. Environment page is descriptive | Follows | Rejects |
| 2. Bring-up picks local-only | Follows | Rejects. Local stays the default (A8). |
| 3. Fixture fuses provides and steps | Follows | Reshapes into Need and Recipe |
| 4. Only `@fixture.key` and `$captured` | Follows | Extends with environment addresses |
| 5. My earlier recommendation | Not built | Re-derived, except per-fixture safety lists |
| 6. Landing from the opened screen | Follows | Out of scope here |
| 7. Sign-in hops replay seeded credentials | Follows | Rejects |
| 8. The book run brings up its stack | Follows, inside the QA tool's runbook code | Rejects for the QA tool. The workflow keeps starting local. |
| 9. An undeclared observed effect fails on local and dev | Not built | Re-derives as invariant 10 |
| 10. Skip what local does not run | Not built | Rejects. Local is built to run it (R8). |

The open lookups L1 to L7 are resolved by the rows above. None is left open.

## 6. Slices

1. **S1. Local runs what dev runs.**
   - Touches: the workflow's bring-up, which applies the client's infrastructure program to
     emulators as a `local` stack before the run. No QA concept changes.
   - Done when: the web book's local run passes its video journeys, because local serves the
     videos from emulator storage the program seeded. Every other journey's result is
     unchanged, and bring-up stays under one minute.
   - This is the thinnest path that shows local standing in for dev. It answers a failure
     group the web book has today. The prototype proved the build on its own (R8).
2. **S2. Skip what no emulator runs.**
   - Touches: Facility read from the environment's service list, a Need that names a
     facility, Verdict, Skip reason, Report.
   - Done when: a journey whose need names a facility the environment's list omits is
     reported as skipped, "local runs no <facility>". It opens no gate and does not reach the
     writer. A facility the list names but that does not answer still fails.
3. **S3. Point a run at an already running dev.**
   - Touches: every drive key, Health check and Access on the environment page, Run target.
     The registry reads the runbook and the environment for one migration and flags the old
     place (R11).
   - Done when: the web book run against dev passes its public and read-only journeys, and
     reports every other journey as skipped with its reason. The local run's results are
     unchanged, and the QA tool starts nothing on either.
   - Built after one attended session has pointed QA at dev by hand. This slice is a
     stand-in for the promised value (A9). Most journeys sign in, so most are skipped until
     S5.
4. **S4. The first tap: the app's outbound HTTP calls.**
   - Touches: Watch port, Tap (HTTP proxy), Observed effect, Effect match, Effect on the
     endpoint.
   - Done when: on local, a journey that makes the app call an outside service none of its
     endpoints declare fails, and names the call. A journey whose endpoints declare it
     passes.
   - Built after two attended sessions have checked effects by hand, and after the `emits`
     bullet means an event in every book (R10).
5. **S5. Sign-in as a Need.**
   - Touches: Need, Recipe, Recipe choice, Access, Reference. A pool account per
     environment.
   - Done when: the signed-in, read-only journeys run on dev.
6. **S6. The other taps: event bus, change stream, filesystem.**
   - Touches: Tap variants, Watch port.
   - Done when: each kind confirms one declared effect on a client stack that has it.
7. **S7. Effects and Allowances, then prod.**
   - Touches: Effect, Allowance, Verdict.
   - Done when: a run against prod skips every journey that touches shared data, sends mail
     or spends money, and passes the rest.
8. **S8. A second recipe for a fresh customer account, with give-back.**
   - Touches: Recipe, Recipe choice, Lease.
   - Done when: a writing journey runs on dev against a pool account, and the account is
     returned to the pool after the run, also when the journey failed.
9. **S9. Addresses in shell steps, and invariant 6.**
   - Touches: Reference.
   - Done when: the book check refuses a literal address in a recipe or journey that an
     environment's Drive port already names, and the client book carries none.

## 7. Assumptions

Most expensive first.

1. **A1. Dev and prod offer test accounts that exist without the app's own sign-up.**
   - Decided: sign-in on dev and prod comes from a pool of accounts, not from creating one.
   - Basis: none.
   - If wrong: S3 and S5, Facility, Recipe. A run on prod would have to create accounts
     through the app, which collides with invariant 2.
2. **A2. Declared effects are honest.**
   - Decided: Verdict trusts the book's effects. The compiler's delete refusal remains the
     only cross-check.
   - Basis: invariant 10 checks them on local and dev wherever a tap can see the effect.
     Writers are agents, and they have dodged checks before.
   - If wrong: invariant 2, Effect. Effects would need inference from the journey's acts.
3. **A3. The owners want prod QA, and allow test accounts on prod.**
   - Decided: S7 targets prod.
   - Basis: the user's words, "The same QA should apply locally, or on dev or on prod".
   - If wrong: S7 shrinks to dev only.
4. **A4. Secret values for dev and prod reach the harness's process environment.**
   - Decided: Access names secrets, and the run reads them from the environment as today.
   - Basis: secrets come from the process environment (`ostler_qa.py:1248-1257`). The
     credential store is not wired to the harness.
   - If wrong: S3, Reference. A credential-store lookup would be needed.
5. **A5. One run targets one environment.**
   - Decided: Run target is a single value.
   - Basis: the user's words name one environment at a time.
   - If wrong: Run target, Report.
6. **A6. An address is fixed per run target when the plan is built.**
   - Decided: a plan is built per run target (R3).
   - Basis: the plan holds the base URL as a literal (`compile_page.py:217`).
   - If wrong: Reference would resolve at run time, and the built plan would carry names.
7. **A7. A first dev run shows its value within one run.**
   - Decided: S3's done-when is one run.
   - Basis: none. A local run of 278 scenarios took 18 minutes. Dev adds network latency.
   - If wrong: S3's done-when, and how often the slice can be checked.
8. **A8. Local stays the reference environment and the default target.**
   - Decided: a run with no target behaves as today.
   - Basis: the local book is the only complete one, and invariant 3 needs a reference.
   - If wrong: invariant 3, Run target.
9. **A9. S3 is a stand-in, not the value.**
   - Decided: S5 follows S3 at once.
   - Basis: most of the web book's journeys sign in first.
   - If wrong: the slice order.
10. **A10. The environment page's `fixture` and `capture` bullets are unrelated to
    Facility.**
    - Decided: Facility is a new bullet, and they stay as they are.
    - Basis: they are registry bullet flags read by no run-time code.
    - If wrong: Facility, which would reuse them.
11. **A11. Each client stack lets a tap attach without a redeploy.**
    - Decided: a watch port is an address the environment already exposes: an upstream URL
      the app reads from its environment, a bus the tester may subscribe to, a stream the
      tester may read, a directory the tester may list.
    - Basis: the web app reads its API and report upstreams from variables
      (`DEV_API_UPSTREAM_URL`, `DEV_REPORT_UPSTREAM_URL`). Nothing is known about dev and
      prod.
    - If wrong: S4 and S6, Watch port. A tap would need the deploy to route through it, which
      section 1 puts out of scope.
12. **A12. The first noisy lap after S4 is acceptable.**
    - Decided: invariant 10 holds from the first lap a tap is open. No journey declares
      effects yet, so the first lap fails every journey with an outbound call.
    - Basis: my recommendation, uncontested.
    - If wrong: invariant 10 gains a warn-only lap.
13. **A13. An emulator covers every cloud service a client app calls, apart from a few named
    pieces.**
    - Decided: S1 builds local from the client's own infrastructure program, and S2's skips
      cover only the named pieces.
    - Basis: one client stack. The emulator ran its buckets, service accounts, IAM, secrets
      and scheduler. It did not run identity platform config, and it runs container services
      only through the host's Docker socket (R8).
    - If wrong: S1 and S2. A client on a cloud the emulator covers less would skip more, and
      F12 would weaken.
14. **A14. The local build's state lives exactly as long as the emulator.**
    - Decided: the build wipes its state and applies fresh every time.
    - Basis: the emulator keeps everything in memory. A fresh apply took about 20 seconds,
      and a refresh against an emptied emulator took over 4 minutes (R8).
    - If wrong: S1's one-minute bring-up. A persistent emulator would let the build refresh
      instead.
