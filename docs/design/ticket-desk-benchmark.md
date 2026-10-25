# The ticket-desk benchmark: a work-shaped multi-repo fixture

Date: 2026-10-24. Status: proposed, not built.

## 1. What it answers

The maintainer wants one number per goal that says how far the coder and QA workflows are from
running a work-shaped story unattended. Work is three repositories, a web frontend monorepo, a
Flutter mobile app and a Go microservice monorepo, a DynamoDB with a stream, an event bus, a
third-party messaging provider and an identity provider. Every benchmark so far measured one
service with one screen in front of it. None has made an agent cross a repository boundary, read
a record a handler wrote off a stream, prove that a notification left the system, or keep a web
screen and a mobile screen true to the same backend change.

Who feels this: the QA at work, who today finds the bug a journey passed over because the screen
looked right and the event never fired.

The fixture is a frozen set of repositories. Stories are written by hand, carry a tracker key as
their id, and are never authored by a workflow. That is the work setup, so the benchmark keeps
it.

## 2. The fixture

Topic: IT issue and ticket management. Three product repositories and one artifacts repository,
all neutral names.

### gamma, the frontend monorepo (yarn workspaces)

| Package | What it is |
| --- | --- |
| `customer-ui` | Svelte 5 app where a customer opens a ticket, follows it, and replies |
| `it-portal` | Svelte 5 app where an agent triages, assigns, resolves and closes tickets |
| `common` | shared UI pieces, the typed API client, auth helpers |
| `protobuf` | the generated client stubs, kept in sync with zeta's definitions, as kappa keeps its own |
| `tf` | Terraform plus a Helm chart that deploys both apps to Kubernetes |

### kappa, the mobile app (Flutter, Android and iOS)

The customer side of `customer-ui` on a phone: open a ticket, follow it, reply, get the push the
notification handler sends. One app, one repo, its own generated gRPC stubs from zeta's
definitions. The book's journeys compile to Maestro, as the mobile reference app's do, and run on the Android
emulator. iOS is in the repo and out of every task, since no Linux runner drives it.

### zeta, the backend monorepo (Go, one cobra CLI per service)

| Package | What it is |
| --- | --- |
| `ticket` | gRPC server: create, list, assign, transition, comment; DynamoDB table `tickets` |
| `user` | gRPC server: customers and agents, roles, lookup by identity-provider subject |
| `notifications` | gRPC API that enqueues a notification on the event bus, and a handler that reads the queue and calls the messaging provider |
| `dynamostream` | handler on the `tickets` stream: a status change emits a `ticket.changed` event on the bus |
| `gateway` | gRPC-web or grpc-gateway front for the browsers, validates the identity provider's token |
| `tf`, `charts` | Terraform and one Helm chart per deployable: each API, each handler |

Each service binary is `svc serve` or `svc handle <name>`, one container per server and per
handler, as at work. The same binary carries the fixture commands a QA step needs: `svc seed`,
`svc get`, `svc events tail`, so the book's fixtures and read-backs run the repo's own CLI and
never a vendor SDK from the agent's hand.

The gateway is not in the maintainer's list. Two Svelte apps cannot call a gRPC server from the
browser without one, and work has one. It stays.

### The local stack

`docs/services/ops/stack.yml` in zeta brings up: LocalStack (DynamoDB, its stream, EventBridge,
SQS), a fake messaging provider that records every call it receives on an HTTP endpoint, a local
OIDC issuer standing in for the identity provider, every zeta server and handler, and both gamma
apps. kappa runs on the emulator outside Compose and reaches the gateway through the host, as
the mobile reference app does. gamma's and kappa's books `needs:` zeta's. Secrets come from `secrets: {saddlebag: …}` only; the file
source is refused on this fixture, which is the policy the work repos will carry.

The QA tool starts nothing. The stack is up before a journey runs, local included.

Terraform and the charts are the deployment path and are real, so that the book's environment
pages can cite them. Kubernetes itself is the one thing local does not run, and the environment
page names it as the piece an emulator does not stand in for.

### The artifacts repository

`docs/epics/CASE-<n>/stories/CASE-<m>/story.md`, with `id: CASE-<m>`, written by hand before the
fixture is frozen. Twelve stories across the three repos, each with its spec folder empty. Plus
`defects.yml` and the defect variants the catch task plants, in the shape frozenapp already
reads.

## 3. The tasks

One tasks module, several tasks. Each task answers one of the maintainer's goals and brings
its own ruler.

| Task | Goal it measures | What runs | Score |
| --- | --- | --- | --- |
| `book` | books per service, business context an agent can use | `workhorse-okf-book` on each repo in the sandbox, no stablemate source in sight | doctor errors; every gRPC method, handler, screen and event present in the graph; the operate rubric judged by a pinned model |
| `operate` | an agent works the app from the book alone | one agent, the three books, a browser, the emulator and the CLIs: bring the stack up, seed a customer and an agent, open a ticket on the phone, resolve it in the portal, see the reply land on the phone, prove the notification left | pass or fail per journey, and whether the proof came from a read-back step rather than the screen |
| `catch` | QA finds the defects a dev leaves, including the unrelated ones | frozenapp round: one control trial per story, one trial per planted defect, `workhorse-coder run qa` | caught, missed, false alarms, per defect class |
| `story` | the dev lane fixes at the root, unattended, in budget | `workhorse-coder run` on three hand-written stories, one of which crosses all three repos through a proto change that both frontends must pick up | hours per story, laps, escapes found by a second QA pass the agent never saw, Story trailer carries the CASE id |
| `kill` | a forced stop costs a node, not a story | the `story` task with the agent CLI killed once mid-dev | resumed to a merged story, or not |
| `canary` | no secret reaches a transcript | a fake token planted in a seed file and a service env on every task above | the token never appears in any agent transcript or run log; the redactor count is a near-miss count |

The defect classes the `catch` task plants, so the score says which kind QA is blind to:

1. **On the screen.** The portal shows the wrong status after assignment.
2. **Behind the screen, same service.** `ticket` writes the record and never emits the change.
3. **Behind the screen, other service.** `dynamostream` drops events for one status.
4. **Across the repo boundary.** A proto field renamed in zeta, gamma's stub not regenerated.
5. **Unrelated service.** The story touches `ticket`; the defect sits in `user` role lookup.
6. **Out of the system.** `notifications` calls the provider with the wrong recipient.
7. **One frontend of two.** The proto change lands in gamma's stubs and not kappa's, so the web
   journey passes and the phone shows an empty field.

Classes 2, 3 and 6 are only catchable by a read-back step. Class 7 is only catchable by a QA
that runs both frontends' journeys for a story that names `services: ticket`, not just the one
the dev touched. Their caught rate is the direct
measure of the unbuilt guidance in qa-across-environments part 5.

## 4. How the fixture gets built

stablemate arrives after the fact. The three product repos exist, run, and have been shipped by
a team that never heard of a book, an epic or a story. So the bootstrap must leave no trace of
stablemate in them: no `docs/services/`, no `docs/epics/`, no `.agents/`, no skill ever read by
the agent that wrote the code. What a real team leaves instead is what the fixture carries: a
README per repo that is partly stale, a Makefile, a CI file, a `docker-compose.yml` someone wrote
for local dev, Go tests on some services and none on others, a Svelte component library with two
naming conventions, three env vars that no document names.

### The bootstrap, in order

1. **A product brief**, one page, `brief.md` beside `tasks.py`. The operator's own expectations
   per repo, the checks to run and the ageing changes are in `shape.md` next to it, which the
   build agents never read. It names the
   actors, the ticket lifecycle, the two web apps, the phone app, the notification rule, and the
   deploy shape. It is a brief, not a milestone: no release boundary, no journeys, no acceptance
   bullets. It is what a founding engineer was told.
2. **zeta first.** One plain agent session, Opus through a plain `claude` run with no stablemate
   skills installed, builds the proto definitions, the five services, the compose file, the tf
   and the charts from the brief. The operator checks that `docker compose up` brings the stack
   up and that one ticket can be opened and resolved over grpcurl.
3. **gamma, then kappa.** Each in its own plain session, from the brief plus zeta's proto folder
   and its README. The operator opens a ticket in `customer-ui`, resolves it in `it-portal`, and
   repeats on the emulator.
4. **Age it.** A second short session per repo, told it is a different engineer six months later:
   rename a service's internal package, add the `user` role lookup, change a status name in the
   proto and regenerate only gamma's stubs, leave the README describing the old name. This is
   where the stale document and the two conventions come from, and it is what makes the `book`
   task a measurement rather than a transcription.
5. **Freeze.** Nothing moves. Each repo was built in place under `data/<name>` as its own git
   repository, and the fixture is the four HEADs at the end of the ageing pass.

The operator attends every session and never writes code by hand. What the agent leaves wrong and
the operator does not fix is part of the fixture, as long as the stack still runs.

### Then the stories

After the freeze, the maintainer writes the twelve `CASE-<m>` stories by hand into the artifacts
repo, against the frozen apps. They are brownfield stories: a new ticket priority that crosses
all three repos, a reminder notification, an agent-reassignment rule, a customer-visible SLA
clock. None asks for a book, and none presumes one exists. The `story` task runs them with a
book already written by a prior `book` trial, which is the order work will follow: book first,
story second.

`defects.yml` is written last, each variant a diff against the frozen commit, so the `catch`
task plants it with frozenapp as today.

A greenfield build as the measured task itself would conflate three things and run for six
hours per trial. The build stays a bootstrap, not a task.

## 5. What this fixture forces in stablemate

Each item below is a gap the first attended round will hit. None needs vendor knowledge in the
tree.

1. **A benchmark with several repositories.** paddock cloned one `data/` repository to the
   stage, and a nested repository would have arrived as an empty gitlink. `data/` may now be a
   folder of repositories: each child is cloned under its own name, remotes stripped, and the
   run's data commit is a digest of the children's HEADs. Steps reach a repo as
   `run.stage / "zeta"`. Done 2026-10-24.
2. **The read-back rule in the writing skill.** A claim about an event, a record or an outbound
   call is proven by a step that runs the repo's CLI and compares the JSON. One paragraph in the
   okf skill plus a doctor check that a side-effect claim names a `verify:` with a command.
   Written after the first `book` round shows a writer not doing it.
3. **A redactor hit fails the run loudly.** One function in the workhorse process runner.
4. **A doctor refusal of `secrets: {file}` on a book that declares it off.** One key in the stack
   schema, one check.
5. **Resume after a kill is measured, not assumed.** No code expected. The `kill` task is the
   measurement.
6. **An emulator inside the sandbox.** The paddock sandbox image carries tools and no tree. An
   Android emulator with KVM is a heavier image and a `--device /dev/kvm` on `paddock sandbox
   run`. the mobile reference app's attended runs did this on the host, never in the container, so this is the one
   item with no attended precedent.

## 6. Assumptions and decisions parked

- The gateway is grpc-gateway over REST for the browsers. gRPC-web through Envoy is the other
  road, and the choice changes nothing in stablemate.
- Local runs Compose from stack.yml, not a kind cluster. If a later round shows the k8s gap
  hides defects, kind becomes a stack service.
- The identity provider is one local OIDC issuer. Firebase at work is the mobile book's case and
  is already covered by the mobile reference app.
- kappa is Android only in every task. The repo builds for iOS so the book can cite it, and no
  task runs it.
- kappa joins the first attended round. If the emulator in the sandbox (gap 6) is not ready by
  then, the first round runs kappa's journeys on the host, as the mobile reference app's did, and the sandbox gets
  it before the first unattended trial.
- Models: Opus for the agents, a pinned Opus for the rubric judge, as the other benchmarks.
- Budget per `story` trial: four hours, the story-throughput target. A trial past it is a
  measurement, not a failure.
