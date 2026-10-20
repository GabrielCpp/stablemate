# Proving a claimed state under the condition that causes it

> **Evidence.** This note is the book method that the state-conditions work builds on. It comes
> from two attended runs. The first ran the book of one page of the `acme` client app, its
> reports page. The second ran the book of paddock's `globex` web seed, against the clean app
> and against six seeded faults. Each rule below names the case in those runs that shows it.

## Who feels it

The product owner who reads a green book run as "the screens behave". On the `acme` reports
page, a first probe returned 12 red scenarios that were the book's own fixture mistakes. The
same run kept the empty-project claim green while the defect it describes was live. A project
with no input row still showed the report tabs and the Download button. A red the owner cannot
trust and a green that hides a bug each cost a full QA loop.

Both faults have one cause. A claim such as "the tabs show once the project has an input row"
ran under whatever data the screen's fixture happened to arrange. Nothing named the condition
the claim depends on, so nothing checked that it held.

After the method below, the same page ran 26 scenarios green on the fixed app. On the app
before the fix, 3 went red, and each red was the defect. The probe had it the other way round.

## Terms

- **Claim.** One thing the book says a screen, component or route does. The compiler turns it
  into checks.
- **State.** A situation a screen or component can be in: populated, empty, failed.
- **Condition.** The fact about the world that puts the screen in a state, such as "the
  directory holds no widget".
- **Fixture.** A book page whose steps arrange a world. Its lifetime says whether a run builds
  it once and reuses it (`lap`) or builds it again for each scenario (`scenario`).
- **Read-back.** A step that reads a condition from the running app and fails when it does not
  hold.
- **Side.** Who owns a red: the product, the book, the arrangement or the environment.

## 1. Adjacency

A story owes proof on every screen that reads the data it changes. The screens it edits are a
subset of those.

The `globex` seed holds four state shapes. A story can break each one without touching the
screen that shows it.

| Shape | Screen state | Condition |
| --- | --- | --- |
| Needs records | widget list, table populated | the directory holds a widget |
| Computed empty | widget list, "no low stock" notice | widgets exist and none has fewer than 5 |
| Upstream failure | widget list, load alert | api-service is not listening |
| Missing reference | new widget, "no categories" notice | no category is on file |

One seeded fault changed only the field name the web-app reads from the list response. It
turned 10 scenarios red: the table, the low-stock panel, the stocked settle, a journey's end and
the list after a submit. Each of them reads the widget directory. No red fell outside what the
diff touched. A story that renames that field owes proof on all of those states, though it
edits none of their screens.

To apply it, list the data the story changes. For each piece, find every screen and component
whose state depends on it. Each of those states is in the story's proof, under every condition
that changes what the screen shows.

## 2. Rules

### A. Every claimed state names its condition

A condition on stored data links a data state. An empty or failure state also asserts the
controls that must be absent.

On the `acme` reports page, the screen required a fixture with an empty project. So every claim
about the tabs ran in the empty state and went red against the fixed app. The empty-state claim
checked the heading text only, and it passed on the defect. The repair gave the screen a fixture
with one input row. Each empty-state claim named its own empty-project fixture and asserted the
tabs and the Download button absent. Those absence checks are what turned red on the defect.

In `globex`, the upstream-failure and missing-reference faults each turned their claim red twice
over. The state's own text was missing. The absence checks failed too: the empty notice showed in
place of the alert, and the category picker stayed enabled in place of the notice. An absence
check catches the defect even when the text check is weakened. That redundancy is what rule A
buys.

A condition inherited by default is not a named one. A screen's `requires:` fixture becomes the
condition of every state on that screen. On the `acme` app, a stages screen required a
customer's project, though any owner of a project sees its `loaded` state. A flow that arrived as
another user could not stop there. The state needs its own `when:`, which overrides what the
screen requires.

### B. `fixture: none` is legal only on a page that sends no request

Otherwise the state names its condition. Today `fixture: none, because ...` suppresses the
"nothing arranged" gap only. The claim still runs under the screen's inherited `requires:`
fixtures, and nothing reads the reason. A page that sends a request shows what the answer holds,
so its states depend on a condition whether the book names it or not.

Neither run produced a red from a wrong `none`. The one `none` that stayed is the `globex` health
route. Its answer depends on no stored data, its page states that reason, and a status check
backs its auth and its behaviour. As worded, rule B forbids it, since the route answers a
request. The doctor rule for B has to decide whether "sends no request" means "reads no stored
data".

### C. Before the claim's checks, the walk reads the condition back and holds it

A fixture's read-back proves the fixture. It does not prove the claim.

In `globex`, one seeded book fault ran the "no low stock" claim under `widgets-on-hand`, a
fixture that adds one widget. That fixture reads back its own condition,
that the widget landed, and it passed. Nothing read back the claim's condition, that no widget
is below 5. The red that followed matched the product fault that drops the "none low" branch,
check for check. Read by hand, rule D blamed the product, and the fault was the book's.

So the condition the walk reads back has to be the claim's own, taken from the state's `when:`.
A screen `state` can carry `when:` today, and doctor raises `unheld-condition` when the walk does
not hold it. A component's `states:` child has no `when:` yet.

On the `acme` page, the empty-project fixture reads back "no input row" before any claim runs.
That read-back is what made the run on the faulty app trustworthy: the condition held, so the
red was the product's.

### D. A failure takes its side from what was observed

| Observed | Side | Goes to |
| --- | --- | --- |
| A fixture step cannot start | environment | the operator |
| A fixture step runs and fails | arrangement | the book's writer |
| The claim's condition reads back false | book | the book's writer |
| The condition held and the claim failed | product | the developer |

In `globex`, the arrangement fault is the one red ostler attributes today. A fixture posted a
quantity the API refused, the fixture faulted, and ostler named the fixture page. The scenario
stopped before its claim, so the claim never ran on a world that was not built.

The four product faults all came out unattributed. ostler attributes a red from the request
evidence a check carries, and a browser check carries none. The condition read-back is the
evidence rule D needs.

Side matters because the run's advice follows it. Today the run appends one hint to every failed
state claim: "claim it at the interaction's `does:`, or name the fixture that arranges it". On
the `acme` app before the fix, the condition held and the claim failed, so the red was the
product's. The hint still told the writer to change the book. That is how the book came to
encode the defect before the probe. The hint belongs only on a condition that read back false.

## 3. Writing the book so the conditions hold

These rules came from the `globex` clean runs. The clean app ran 16 of 18 scenarios red at
first, and every one of those reds was the book's. Later runs exposed five harness faults,
each fixed in stablemate (bbdd46da, 68122dc0, eecafaf7, 035c50b9, 469ef16a).

**Fixture lifetime on an in-process store.** A book whose service keeps its state in process
needs `- lifetime: scenario` on every fixture. Fixtures default to `lap`. In `globex`, one
fixture recreated api-service to empty the directory. Every later scenario that trusted a lap
fixture found the directory wiped, and the reds landed on whichever scenario ran next. The line
goes at the fixture's head. Inside a step, nothing reads it: the outage fixture stayed `lap`
that way, and the error scenario got an empty list in place of an outage.

**Where a fixture line binds.** A `- fixture:` binds to the nearest normative bullet above it.
On an interaction it goes above `- trigger:`. Placed under `- trigger: click`, it gave the click
claim its world and left the keyboard claim from the same interaction with none. On a component
that shows only under a condition, it goes right after the verify of the component's name. The
arrival scenario for that name then builds its own world.

**Components that come and go.** A component that is not always shown says when, with `states:`
or `exclusive-with:`. The placement vet reads a component with neither as always shown. In
`globex` it failed the name error and the low-stock panel as "rendered nowhere on this screen".

**Every claim has a check.** The clean app passed 20 of 20 scenarios and the run still failed on
29 compile gaps. Each gap was a claim with no check: a component's role and name, two keyboard
claims, the health route's auth and behaviour. A fault that broke one would have stayed green.

- A `- verify:` right after `- name:` proves the role and the name, because the visible check
  finds the element by both.
- "Reachable by Tab" needs a `focusable` check of its own.
- One check that cannot compile drops a flow's whole `end:` claim. On the `acme` page a journey
  ended on a check that read a file the browser cannot see. So the journey checked only its
  start, and never the report figures.

With these the `globex` book compiles to 34 scenarios and no gap. The clean app passes all 34.
Each of the six seeded faults turns its target claim red, with no red outside its diff.

## 4. Two conditions a fixture cannot state today

**Device-computed conditions.** Some states depend on a fact the browser computes from stored
data, not on the data itself. "No low stock" holds when widgets exist and none has fewer than 5.
A fixture arranges records, and its read-back proves the records landed. It does not prove the
fact computed from them, which is the seeded book fault in rule C. Rule A says a condition on
stored data links a data state, and no single data state names this one. The condition has to
be stated as a test over the stored records, and the read-back has to evaluate that test. How
`when:` expresses it is still open.

**Upstream-failure conditions.** No mechanism makes a request fail on purpose. `globex` arranges
its load alert with a fixture that stops api-service, so every request the page sends is
refused. That works only where the book controls the service's lifetime. It cannot fail one
request among several, and it cannot produce an error status or a slow answer in place of a
refused connection. Each of those is a state a screen can owe and a book cannot yet arrange.

## 5. Where convergence is enforced

A book run converges when each red reaches the one owner who can fix it. Book reds then fall
every lap, and product reds reach the developer once.

| Point | What it enforces | Today | Still to land |
| --- | --- | --- | --- |
| Doctor, at write time | each state's condition is held by the walk | `unheld-condition` on screen states | `when:` on component states; a rule for B; a `- lifetime:` inside a step |
| Placement vet, at run time | a component that comes and goes says when | a component with neither `states:` nor `exclusive-with:` fails as rendered nowhere | |
| Compile | each claim has a check | a gap fails the run | a page compile prints no gap for a flow it selects, so a flow can vanish from the plan silently |
| Fixture run | the world was built | a failed step is an arrangement fault, and the scenario stops before its claim | |
| Condition read-back | the claim's own condition holds | written by hand as a fixture verify | compiled from `when:` before the claim, its failure tagged as the book's |
| Side attribution | each red names its side | arrangement, from request evidence | product and book, from the read-back |
| Routing | each side reaches its owner | the okf-book workflow routes book and arrangement to the writer, environment and app to an operator gate | coder QA sends every red to its QA owner or to the developer, so it needs to read the side |
| Standing round | the method keeps catching faults | the `globex` book, one clean pass and six seeded faults, 28 minutes of wall time | a scored paddock task; side accuracy joins the score once attribution lands |

The QA report also lists every fixture and read-back step as uncovered, even when each one ran
clean. A reader cannot tell a held condition from one that never ran.
