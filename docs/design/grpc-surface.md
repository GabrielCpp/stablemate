# A gRPC surface for the book

Disclosure: before this note was started, its author had read the book workflow's surface
declaration (four kinds: cli, http, web, mobile), its README, and the reference pages of the
`server`, `endpoint` and `method` node types. Every design decision those carried is a claim
in section 1b.

## 1. Problem

An operator who wants a book for a backend that speaks only gRPC cannot get one. The book
workflow accepts no way to say "this service is reached over gRPC", the book format has no
place for an RPC, and no QA scenario can call one. A team whose backend is gRPC, as the
ticket-desk benchmark's zeta and the operator's own work backend are, gets books for its web
and phone apps and none for the ten services those apps call.

Done looks like this to the operator:

- One launch line declares a zeta service as a gRPC surface, and the run writes its book.
- The book has one node per RPC the service's contract declares: 20 for `ticket`, 84 across
  zeta's nine domain services. Doctor reports none missing and none invented.
- The phone's REST gateway gets an HTTP book with one endpoint per route its proto annotates:
  22 for `mobile-gateway`. Doctor checks those endpoints against the same proto, with none
  missing and none invented (revised, R9).
- Each RPC's claims about what it does, what it returns and which status it fails with are
  proven by a QA scenario that calls it on the running service and reads the effect back
  through another RPC.
- The ticket-desk milestone's four zeta journey services have books: sla, ticket and
  notifications as gRPC books, mobile-gateway as an HTTP book (revised, R9), so doctor's milestone-journey-services rule passes and the
  author run can start.

Out of scope:

- Client-streaming and bidirectional RPCs. zeta has none. Server-streaming is in scope
  because zeta has two (`audit.v1` `ExportAuditEvents`, `notifications.v1`
  `StreamNotifications`).
- Background handlers that read a queue or a table stream (sla's clock and escalate,
  dynamostream, notifications' dispatch). They are not reached by a call. Their effect is
  proven through an RPC that reads it back. Booking a handler as its own node is a separate
  problem.
- TLS, mutual TLS and load-balanced addresses. Local QA runs plaintext against one address
  per service.
- gRPC-Web and Connect protocols. zeta serves plain gRPC only.
- Generating client stubs or checking that gamma's and kappa's generated clients match the
  contract.

## 1b. Claims

1. A surface is a service slug, a kind and an entry folder, and the writer reads nothing
   outside the entry folder. (okf-book README)
2. The kind picks the writer's branch of the skill and the driver the scenarios run on.
   (okf-book README)
3. A `server` is an HTTP service filed under `docs/services/<service>/http/`, with each route
   an `endpoint` under its `## Endpoints`. (server.md)
4. A `method` is a code-level callable whose claims are context, never live evidence. Its
   proof belongs on the surface that reaches it. (method.md)
5. A server node carries a fallback launch contract (launch, entry-url, health-path,
   identity, stop, boot-timeout) that a runbook supersedes. (server.md)
6. A QA tool is opted into per repo in `agents.yml` and defined in the stablemate config.
   (benchmark agents.yml files)
7. Under a workspace, books land in the docs home's `docs/services/<service>`. (ticket-desk
   memory)

## 2. Parts and concepts

### Level 1: parts

1. **Declaring the surface.** The operator says a service is reached over gRPC, where its
   source is, and where its contract is. Owns the declaration. Never knows how a book is
   written or proven. Hands the declaration to Writing and to Proving.
2. **Describing the service.** The vocabulary a book uses for a gRPC service: the server it
   runs as, each RPC, the messages they carry, and the statuses they fail with. Owns what a
   valid gRPC book looks like. Never knows how a claim is proven. Every other part reads it.
3. **Reading the contract.** Turns the service's proto definitions into the list of services,
   RPCs, streaming shapes and message types they declare. Owns what the contract says. Never
   knows the book. Hands the list to Checking coverage and to Writing.
4. **Checking coverage.** Compares the book's RPCs with the contract's. Owns "nothing missing,
   nothing invented". Never knows how either side was produced. Acts at doctor time.
5. **Writing the book.** Guidance and inputs for the agent that writes a gRPC book. Owns what
   the writer is told and what it may read. Never knows how scenarios run.
6. **Proving claims.** Brings the service up, calls an RPC, and observes the reply. Owns the
   observation. Never knows how the book was written. Acts at QA time.

Flow: the operator's declaration reaches Writing, which reads the contract's RPC list and the
vocabulary and writes one node per RPC. At doctor time, Checking coverage compares the book
with the contract. At QA time, Proving brings the server up, turns each claim into calls, and
records each reply as evidence against the claim.

Plain-words test: the operator says "this one is gRPC, its code is here, its proto is there".
The writer gets the list of calls from the proto and writes a page per call. A checker makes
sure the pages and the proto list the same calls. QA starts the service, makes each call the
way a client would, and writes down what came back.

### Level 2: concepts

**Declaring the surface**

| Concept | Owns | Never knows |
|---|---|---|
| gRPC reach | naming gRPC as one way a user reaches a service | the node vocabulary it implies |
| Contract location | where the service's proto definitions and their import root live, for a gRPC surface or an HTTP surface whose routes are proto annotations (revised, R9) | how they are parsed |
| Home repo | which repo of a multi-repo workspace holds the entry and the contract (revised, R1) | where the book lands |

**Describing the service**

| Concept | Owns | Never knows |
|---|---|---|
| gRPC server | the running service: the address it listens on and the proto services it serves | each RPC's behaviour |
| RPC | one callable's contract: its full name, streaming shape, request and reply messages, and its does, returns and fails-with claims | how a call is made |
| Message | the fields of one request or reply message as a client sees them | which RPCs use it |
| Status vocabulary | the fixed set of gRPC status codes a fails-with claim may name | any service |
| Call metadata | what a call must carry besides its message, such as the bearer token | where the token comes from |
| Launch contract | how to start, stop and reach one service, shared by every launchable server kind (revised, R3) | the protocol the service speaks |

Status vocabulary is a read-only catalog every part consults.

**Reading the contract**

| Concept | Owns | Never knows |
|---|---|---|
| Contract | the parsed list of services, RPCs, streaming shapes, message names, and the HTTP route an RPC is annotated with (revised, R9) | the book |
| Contract reader | turning proto files into a Contract | which tool the book was written with |

**Checking coverage**

| Concept | Owns | Never knows |
|---|---|---|
| Coverage finding | one RPC or annotated route missing from the book, or one RPC or endpoint node the contract lacks (revised, R9) | how either list was built |

**Writing the book**

| Concept | Owns | Never knows |
|---|---|---|
| gRPC writing branch | what the writer is told about booking a gRPC service | how scenarios run |
| Reading scope | which folders the writer may read: in a workspace the whole repo that holds the entry, else the entry and the contract location (revised, R11) | the writer's turn mechanics |

**Proving claims**

| Concept | Owns | Never knows |
|---|---|---|
| Call | one invocation: target address, full method name, request as JSON, metadata, deadline | how it is sent |
| Reply | what came back: status code, status message, and the reply messages as JSON | the claim it will be judged against |
| Caller | sending a Call and returning a Reply (a role) | the claim |
| Open stream | holding a server-streaming Call open for its listening window while one trigger Call is sent (revised, R10) | which messages the claim counts |
| Reply check | judging one Reply against one claim: a status, a field value, a field's presence, a message count | how the Call was sent |
| Readiness probe | saying a launched server is up and is ours (a role) | what the server serves |
| Credential mint | turning a declared credential name into a value at bring-up, by running its recipe (revised, R7) | which call uses it |

### Variants

- **Caller** has two variants. The live caller sends the call with the gRPC client tool
  against the running service. The recorded caller returns canned Replies, for tests. The
  choice belongs to the part that assembles a QA run.
- **Readiness probe** has two variants. The existing HTTP probe asks a health path. The gRPC
  probe asks the standard gRPC health service. The surface's reach makes the choice.

## 3. Invariants

1. Every RPC the contract declares for a booked service has exactly one RPC node, and every
   RPC node names an RPC the contract declares. Owner: Coverage finding. Upheld by: the
   gRPC writing branch.
2. An RPC node's name is the full method name exactly as the contract spells it,
   `package.Service/Method`, case kept. Owner: RPC.
3. A fails-with claim names a code from the status vocabulary. Owner: Status vocabulary.
4. Every Reply carries a status code. A Reply with status OK carries one reply message for a
   unary RPC and zero or more for a server-streaming one. Owner: Caller.
5. The scenario that proves a claim on an RPC calls that RPC. Owner: Reply check, which
   refuses to judge a claim against a Reply from a different method.
6. The writer reads no folder outside the repo that holds its entry, and outside a workspace no
   folder beyond the entry and the contract location (revised, R11). Owner: Reading scope.
7. A launched gRPC server counts as ready only when the gRPC health service answers SERVING on
   the declared address and the server lists the proto service its book names. Owner:
   Readiness probe. (revised, R5)
8. No credential value reaches the book, the scenario source or the evidence. A Call names its
   credential by reference, and its Reply records no metadata. Owner: Caller. (added, R7)
9. Adding the gRPC kind leaves the writer's prompt for every other kind byte-identical. Owner:
   gRPC writing branch. (added, 5b row 3)
10. A book run writes nothing in a workspace's product repos. Its writes land in the docs home.
    Owner: Home repo. (added, 5b row 6)
11. A trigger Call is sent only after its stream is open, and a stream that its listening
    window closes replies OK with every message it received before the close. A stream that
    fails before the window closes replies with that failure's status and the messages that
    came before it. Owner: Open stream. (added, R10)

## 4. Forces and patterns

Forces:

- F1. Surface kinds grow: cli, http, web, mobile, and now gRPC. Adding one should add its own
  concepts and one line where the kind is chosen, and change nothing else.
- F2. Tests must run without a live service, so the way a call is sent must be swappable.
- F3. The contract is the source of truth for what exists. It must be readable without a
  running server, because doctor runs offline.
- F4. Readiness differs by reach: an HTTP server has a health path, a gRPC server has the
  health service.
- F5. Most calls need a bearer token. The token is a credential the agent must not hold in
  the book.
- F6. Cost. A QA scenario makes a handful of calls. A process per call (about 50 ms) is
  acceptable. A compile step per call is not.

Patterns between parts:

- One value handed along: the Contract, read once, consumed by Writing and Checking coverage
  (F3). No part re-parses proto files.
- Each choice is made once, by the thing that knows it (F1, revised R2). The surface kind
  picks the writing branch. The node type picks the QA lane, and with it the Caller. The
  address scheme of the launch contract picks the Readiness probe.

Patterns inside parts:

- Caller is a port with two adapters, live and recorded (F2).
- Readiness probe is a role with an HTTP and a gRPC variant, chosen by reach (F4).
- Contract reader is a plain function. Nothing about it varies today (F3).
- Status vocabulary is a constant catalog (no force for anything else).
- Call metadata names the token by reference, never by value. The Caller resolves the
  reference at call time (F5).
- The live Caller uses server reflection when the server offers it and the contract location
  otherwise, so no per-call compile is needed (F6).

Claims:

- Claim 1 is reshaped. A gRPC surface needs a contract location in addition to the entry
  folder, because a monorepo's protos sit outside each service's source folder (zeta keeps
  them in `proto/`). The writer may read both.
- Claim 2 is reshaped (R2). The kind picks the writing branch only. The driver follows from the
  node types the book holds, which is where the code already makes that choice.
- Claim 3 is rejected for gRPC. A gRPC server is not an HTTP server. It gets its own node type
  and its own folder, `grpc/`.
- Claim 4 is kept, and it is why an RPC is not a `method`. An RPC is a surface a client drives,
  so its claims are live evidence. A `method` stays the code-level callable behind it.
- Claim 5 is re-derived from F4, with readiness through the gRPC health service in place of a
  health path.
- Claim 6 is kept. The gRPC client tool is opted in like any other QA tool.
- Claim 7 is kept unchanged.

Open lookups L1 to L7 are resolved in section 5.

## 5. Mapping onto the existing system

Revision log:

- R1. §2 Declaring the surface gains **Home repo**. Under a workspace, the book flow's root is the
  docs home (`okf_book/shared/book_flow.py:35`), and the entry, the source copy, the citation
  checks and the stack bring-up all resolve against it (`okf_book/main/flow.py:56-59`, `:144`,
  `:167-170`, `shared/book_run.py:222`). A book run in a workspace cannot reach the product
  repo at all, for any kind. This blocks all seven milestone books, not only zeta's.
- R2. §4 claim 2 and the between-parts pattern are reshaped. The kind reaches only the writer's
  prompt (`main/nodes/writer_request.py:56`, `main/prompts/write-book.md:42-196`). The QA lane
  is chosen by node type (`ostler/qa/dispatch.py:5-11`). The okf-book README line 22 says
  otherwise and is wrong.
- R3. §2 Describing the service gains **Launch contract**. The launch keys are declared on
  `server` only (`ostler/registry.py:518-534`), and four places treat `server` as the one
  launchable type (`ostler/qa/runbook.py:374-379`, `ostler/qa/context.py:1495-1504`,
  `ostler/reach.py:21`, `ostler/qa/runbook.py:210-228`). The design lacked the concept that
  those sites share.
- R4. §2 Message keeps its row, mapped onto the existing record bullet (below). No new node type.
- R5. §3 invariant 7 adds the identity half. HTTP identity is a body substring on the health
  reply (`ostler/qa/stack.py:162-165`). The gRPC health reply has no body to search, so
  identity becomes "reflection lists the named proto service".
- R6. §2 Coverage finding is confirmed new. No check reads `openapi:` (`ostler/registry.py:522`,
  `:676` declare it, nothing reads it).
- R7. §2 Proving claims gains **Credential mint**, and §3 gains invariant 8. A runbook's
  `secrets:` children parse to `{NAME: recipe}` (`ostler/qa/runbook.py:138-150`, `:203-205`),
  and nothing runs the recipe. zeta's login mock hands a token to `GET /tokens/<login>`
  (`zeta/devtools/smoke/smoke.go:156-176`), so a recipe is one `curl`.

- R9. The operator reported that at work the phone calls the mobile gateway over REST through
  grpc-gateway, and gRPC stays inside the cluster. The benchmark was reworked to match
  (benchmark shape §8, ecosystem §1 and §4.10). This changes §1 done-looks-like and out of
  scope, §2 Contract location, Contract and Coverage finding, the Reading scope mapping, §5b
  row 6 and §6. The REST gateway is an HTTP book, which exists today. What is new is that its
  endpoints are checked against the routes its proto annotates.
- R10. §2 Proving claims gains **Open stream**, and §3 gains invariant 11. zeta's
  `StreamNotifications` never closes, and it sends only what is created after it opens
  (`zeta/notifications/service/service.go:169-175`, `notifications/server/server.go:123-158`).
  A claim about what a stream delivers therefore needs a second call made while it is open,
  and a reply that ends when the client stops listening. The act vocabulary had no way to say
  either (`ostler/acts.py:110-145`), and the caller dropped every message on a non-zero
  grpcurl exit (`ostler/qa/harness/ostler_qa_grpc.py:127-137`).
- R11. §2 Reading scope and §3 invariant 6 are widened in a workspace, and A5 is settled
  false. The first ticket book ran with the entry and the contract as its only added
  folders, and its writer could not load the book format skill: a confined turn loads skills
  only from its project and its added folders, and the docs home it starts in carries none.
  The same writer reported that its runbook needed zeta's compose file, config, auth package
  and seed data, all outside `ticket/`. In a workspace the writer now reads the whole member
  repo (`main/nodes/writer_request.py` `add_dirs`). Source coverage stays on the entry.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Declaring the surface | Reshape | `okf_book/main/nodes/surface.py`. Gains a kind, a contract location and a home repo. |
| Describing the service | Reshape | `ostler/registry.py` `UI_TYPES`. Gains two node types and a value kind. |
| Reading the contract | New | `ostler/proto_contract.py`. |
| Checking coverage | New | `ostler/rpc_coverage.py`, wired into doctor beside `check_server_membership` (`ostler/doctor.py:122`). |
| Writing the book | Reshape | `okf_book/main/prompts/write-book.md` and `main/nodes/writer_request.py`. |
| Proving claims | Reshape | `ostler/qa/compile_grpc.py` (new), the harness `ostler/qa/harness/ostler_qa.py`, `ostler/qa/stack.py`. |

### Concepts

**Declaring the surface**

- gRPC reach: **New**. `SurfaceKind.GRPC = "grpc"` in `surface.py:11-17`.
- Contract location: **New**. `Surface.contract: str = ""`, a folder relative to the home repo.
  Required for kind grpc, refused for the others.
- Home repo (R1): **New**. `Surface.repo: str = ""`, a workspace member name. Required under a
  workspace and refused outside one. The flow resolves `entry` and `contract` against the
  member's path from `kit/workspace.py:31-40`. A citation into a member is written
  `repo://<member>/<path>`, which ostler's doctor already resolves through
  `effective_checkouts` (`ostler/provenance.py:332-343`). Three okf-book checks skip qualified
  refs today and must read them: `shared/citations.py:33`, `shared/source_coverage.py:82` and
  `main/nodes/stale_citations.py:101`.

**Describing the service**

- gRPC server: **New** node type `grpc-server`, folder `grpc/`. Bullets: the launch contract,
  `contract:` (a code link to the proto folder), `serves:` (one or more full proto service names)
  and a required `## RPCs` section linking each `rpc` page. It is not a reshaped `server`,
  because `server` requires `## Endpoints` and its identity check reads a body (claim 3).
- RPC: **New** node type `rpc`. Identity `name:`, value kind `rpc-name`, which accepts
  `package.Service/Method`. `streaming:` is `unary` or `server`. Normative bullets mirror
  `endpoint` (`ostler/registry.py:664-673`): `does`, `status`, `errors`, `auth`, `response`.
- Message (R4): **Exists** as the record bullet `endpoint` already carries
  (`ostler/registry.py:668-669`). `rpc` takes `request:` and `response:` records of the same
  shape. A `field:` member stays a name, since no resolver exists for endpoints either.
- Status vocabulary: **New** value kind `grpc-code` in `ostler/values.py`, the 17 canonical
  names (OK to UNAUTHENTICATED), upper snake case as the gRPC spec spells them.
- Call metadata: **Reshape**. HTTP header rows already become a `headers=` literal whose values
  are `$name` references (`ostler/qa/compile_http.py:240-250`). The gRPC lane reuses the row
  grammar and emits `metadata=`.
- Launch contract (R3): **Reshape**. The keys move from the `server` entry into a shared
  bullet set that both `server` and `grpc-server` declare. Each site that names `server` as
  the launchable type reads one `LAUNCHABLE_TYPES` set instead.

**Reading the contract**

- Contract and Contract reader: **New**, one module. A plain function reads `.proto` files
  under a folder and returns the services, their RPCs, each RPC's streaming shape and message
  names. It parses only `package`, `service` and `rpc` declarations, after stripping comments,
  with no protobuf dependency (A4).

**Checking coverage**

- Coverage finding: **New**. For an HTTP book (R9), a `server` gains the same optional
  `contract:` bullet. When it is set, two more rules compare its endpoints with the annotated
  routes: `route-missing` and `route-phantom`, matching on method and on the path with
  variable names ignored (A10). A `server` without `contract:` is checked as today.
  For a gRPC book, two doctor rules: `rpc-missing` (the contract declares an RPC of
  a served service and no `rpc` page names it) and `rpc-phantom` (an `rpc` page names an RPC
  the contract lacks). Membership between `rpc` pages and the server's `## RPCs` list reuses
  the shape of `ostler/server_membership.py:44-77`, extended to the new pair.

**Writing the book**

- gRPC writing branch: **Reshape**. A `grpc` arm in `write-book.md` beside the
  cli/http/mobile/web arms (`:42-66`, `:148-196`). Without it, grpc falls to the web arm.
- Reading scope: **Reshape**. The writer reads the entry folder in place, as an added
  directory (`main/nodes/writer_request.py` `source_dir`, `main/write_book_flow.py` `add_dirs`).
  The contract folder becomes a second added directory, for any surface that declares one,
  HTTP included (R9). Source coverage stays on the entry folder
  (`shared/source_coverage.py:41-45`). The contract is covered by `rpc-missing` and
  `route-missing`. In a workspace the added directory is the member repo root, which holds
  both and the repo's rendered skills (revised, R11).

**Proving claims**

- Call and Reply: **New** value types in the harness, beside `Response` and `ToolResult`
  (`ostler/qa/harness/ostler_qa.py:480-499`, `:2105`).
- Caller: **New** role in the harness. The live variant runs `grpcurl -plaintext
  -format-error` with the request on stdin and reflection for the schema. It reads the status
  from grpcurl's exit code and error JSON. The recorded variant returns canned Replies for
  tests. The existing `Http` has no such seam (`ostler_qa.py:572-600`). That is a reason to
  give the new role one, not to copy its absence.
- Reply check: **Reshape**. A new check `grpc_status` in `ostler/checks.py`, beside
  `http_status` (`:81`). `json_path` (`:107`) judges reply messages unchanged. A
  `message_count` check judges a server stream. The lane registers in
  `ostler/qa/dispatch.py:5-11` (rpc to grpc) and gets a compiler `compile_grpc.py` that
  mirrors `compile_http.py:120-528`.
- Readiness probe: **Reshape**. `health_probe` is HTTP only and says on purpose that it has
  one seam (`ostler/qa/stack.py:136-185`). It becomes a role with two variants chosen by the
  `entry-url` scheme: `http(s)://` keeps today's probe unchanged, `grpc://` runs the health
  check and the reflection list.
- Credential mint (R7): **New**. At bring-up, each runbook `secrets:` recipe runs once and its
  stdout becomes that name's value in the scenario environment, where `qa.secret(name)`
  already reads it (`ostler_qa.py:215-222`, `:1763-1767`).

### What the system has that the design lacks

- A per-kind QA tool list goes to the writer only for cli (`write-book.md:196-203`). The gRPC
  writer needs it too, because its `exercise` runs grpcurl. Missed concept: the grpc arm shows
  the list.
- Redaction exists for browser captures (`ostler_qa_browser.py:825-827`) and a JWT-shaped regex
  for HTTP excerpts (`ostler_qa_responses.py:14`). Both are waste for the Caller, which never
  records metadata (invariant 8). The regex stays as the guard for a token echoed in a reply.
- `data_states.py`, `data_state_ledger.py` and `doctor.py:1929` hard-code `endpoint` tuples.
  Concept missed: a "callable surface" set like `LAUNCHABLE_TYPES`. It is added for `rpc` in
  the same slice that needs it, and each site is listed in that slice.

### Claims

| Claim | Existing system | Design |
|---|---|---|
| 1. Writer reads only entry | Follows (`writer_request.py`) | Reshaped: entry plus contract, both in the home repo |
| 2. Kind picks branch and driver | Branch yes, driver no (R2) | Reshaped to match the code |
| 3. server is HTTP under `http/` | Follows (`registry.py:518`) | Kept for HTTP, rejected for gRPC |
| 4. method is never live | Follows (`dispatch.py:53`) | Kept |
| 5. server carries a launch contract | Follows | Shared by both server kinds (R3) |
| 6. QA tools opt in per repo | Follows | Kept. grpcurl joins zeta's `qa.tools` and the home config |
| 7. Workspace books land in the docs home | Follows, and cannot read source (R1) | Kept, with Home repo |

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| 1. Every existing HTTP, CLI, web and phone book | the same QA plan from the same book | ostler tests | 4034 passed, 170 s | same pass count, no new failure |
| 2. A single-repo book run | the same flow with no `repo` on its surface | okf-book tests | 191 passed | 191 passed, plus the new tests |
| 3. The writer of a cli, http, web or phone book | the same prompt | nothing, so invariant 9 | byte hash per kind, taken at slice 4 start (A8) | each hash unchanged |
| 4. An HTTP stack's readiness | probe on entry-url plus health-path, identity substring | ostler stack tests | inside row 1 | inside row 1 |
| 5. The doctor of stablemate's own books | the same findings, at the same speed | nothing for the count | 2558 errors, 1499 warnings, 13.3 s | same counts, at most 15 s |
| 6. The frozen product repos of the benchmark | no change from a book run | nothing, so invariant 10 | clean trees at gamma c79c105, kappa 77a9c72, zeta d0bd0ba | clean, and HEAD changed only by the third-edition rework, which carries the grpcurl opt-in (R9) |

## 6. Slices

1. **One RPC proven by hand.** A hand-written two-page book in a scratch docs home: one
   `grpc-server` for zeta's ticket service and one `rpc` page for its read call, with a
   NOT_FOUND claim and a read-back. Touches gRPC server, RPC, Status vocabulary, Launch
   contract, Call, Reply, Caller, Reply check, the gRPC Readiness probe and Credential mint.
   Done when `ostler qa` against zeta's local stack passes both claims, and fails the
   NOT_FOUND claim when the book says INVALID_ARGUMENT. Re-measures rows 1, 4 and 5.
2. **Contract coverage.** Contract reader and Coverage finding. Done when doctor on that
   book reports 19 `rpc-missing` for ticket's 20 RPCs, then zero after the stubs are added,
   and one `rpc-phantom` for a misspelt name. Re-measures rows 1 and 5.
3. **A book run in a workspace.** Home repo, for every kind. Done when an okf-book test runs a
   two-repo workspace end to end, its book lands in the docs home, its citations are
   `repo://` refs that doctor accepts, and the product repo's tree is unchanged. Re-measures
   rows 2 and 6.
4. **The gRPC writer.** gRPC reach, Contract location, gRPC writing branch, Reading scope.
   grpcurl joins the benchmark's home config. zeta's `qa.tools` already has it from the
   third-edition rework. Done when the attended
   ticket book run ends with 20 `rpc` pages, zero coverage findings and its QA claims proven,
   and rows 2, 3 and 6 hold.
5. **Server streaming.** `message_count` and the stream half of Reply. Done when
   `StreamNotifications` has a proven claim in the notifications book. Re-measures row 1.
6. **A REST face read from its proto** (R9). Contract reader reads `google.api.http` options,
   `server` gains `contract:`, and doctor gains `route-missing` and `route-phantom`. Done when
   the attended mobile-gateway HTTP book ends with 22 endpoints, zero route findings and its QA
   claims proven, and doctor on stablemate's own books still reports row 5's counts.
7. **The remaining books.** sla and notifications from zeta, customer-ui and it-portal from
   gamma, kappa from kappa, each attended through groom on Opus. Done when
   doctor in the artifacts repo reports no `milestone-journey-services` finding. Re-measures
   row 6.

## 7. Assumptions

1. **Assumption:** a book run in a workspace has never worked for any kind, so the ticket-desk
   books need slice 3 whatever happens to gRPC. **Decided:** slice 3 is part of this change.
   **Basis:** R1, every site cited there. **If wrong:** slice 3 shrinks to a test.
2. **Assumption:** zeta answers health and reflection without a token. **Decided:** the gRPC
   readiness probe and the live Caller use reflection, with no proto import path.
   **Basis:** `zeta/internal/auth/interceptor.go` skips `/grpc.health.` and
   `/grpc.reflection.`. **If wrong:** Caller passes the contract folder to grpcurl as
   `-import-path`, F6 holds.
3. **Assumption:** each call's token can be minted once per bring-up and reused for the run.
   **Decided:** Credential mint runs at bring-up, not per call. **Basis:** zeta's smoke caches
   one token per login (`smoke.go:61`, `:176`). Token lifetime not measured. **If wrong:**
   Credential mint re-runs on UNAUTHENTICATED, once.
4. **Assumption:** the service and RPC lines of a proto file parse reliably by hand.
   **Decided:** no protobuf dependency in ostler. **Basis:** zeta's protos are `buf lint`
   clean, so they follow standard style. Not tested on another repo. **If wrong:** the reader
   shells out to `buf build`, and doctor needs buf.
5. **Assumption:** the writer can state the UNAUTHENTICATED claims from the entry and contract
   alone, though the auth interceptor sits in `zeta/internal/auth`. **Settled false** (R11):
   the first ticket book's writer asked for the compose file, config, auth package and seed
   data. Reading scope in a workspace is the whole member repo.
6. **Assumption:** zeta's whole stack boots on this machine within the boot timeout.
   **Decided:** one runbook brings up the compose stack for every zeta book. **Basis:** the
   builder's smoke passed at the freeze. Boot time not measured. **If wrong:** the runbook
   sets `boot-timeout` from a measurement.
7. **Assumption:** the latent ticket write race shows only while the sla handler runs.
   **Decided:** the ticket book's QA stack leaves the sla handler down. **Basis:** the freeze
   record's note on the race (about one write in four). **If wrong:** a ticket does-claim
   flakes, and the scenario retries once like the smoke.
8. **Assumption:** the four existing kinds' prompts render deterministically, so a hash
   compares them. **Decided:** row 3 measures by hash at slice 4 start. **Basis:** the prompt is
   a Jinja template over a frozen request. **If wrong:** compare rendered text with the request
   fixed.
9. **Assumption:** an attended 20-RPC book run fits in one working day on Opus. **Decided:**
   slice 4 runs one book, and slice 6 runs the rest one at a time. **Basis:** none for gRPC.
   **If wrong:** slice 6 spreads over days, and the author run waits.
10. **Assumption:** a grpc-gateway path template and a book's endpoint path name the same route
    when they agree on method and on every segment except the variable names. **Decided:**
    route coverage ignores variable names. **Basis:** grpc-gateway writes `{field}` and the
    book's route grammar its own variable syntax. Not checked against `ostler/routes.py`. **If
    wrong:** §5 Coverage finding normalises the two grammars before comparing.
