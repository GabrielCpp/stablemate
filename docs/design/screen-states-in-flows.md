# Screen states that flows wait for and check

Disclosure: before this note was started, its author had read parts of the existing book schema
and harness: the flow node type, the check vocabulary and the QA harness reference. The decisions
those carry are listed as claims in 1b. Each part and concept below was tested against "would I
have named this without having seen the solution?"

## 1. Problem

**Who feels it.** The owner of a web or mobile app trusts its book's QA to catch a regression on
any screen a user walks through. Today a walk checks only where it ends. A screen on the way can
show the wrong empty message, a failure banner, a Save button that should be greyed out, or a
spinner that never stops, and the walk still passes. The same walks fail at random when a step
acts on a screen that has not finished loading. Each walk also restates how to reach and
recognise the screens it shares with every other walk, so one screen change means editing many
walks.

**Done looks like.**

- Each screen a walk passes through is checked in full, at that point, before the next action.
  In the six-walk sample that found this, that moves mid-walk checks from 12 of 30 named states
  to 30 of 30.
- Each wait ends on something the screen does: the requests it sent have answered, its busy
  sign is gone, and it shows one of its declared states. A screen that takes longer than the
  app's responsiveness ceiling fails, and the failure names what it was still waiting on.
- Every check reads what a person or an assistive technology perceives: roles, accessible names,
  visible labels and text, and accessibility states such as disabled or busy. A restyle that
  keeps those breaks no walk.
- Every tap and click finds its element the same way. A walk presses a button by its accessible
  name, which is the button's label.
- A screen's states and the moves out of them are written once, on the screen's page. Changing
  a screen edits that page, and every walk through it picks the change up.
- Every state a screen page declares is checked by at least one walk.

**Out of scope.**

- Finding states the app has that no screen page declares. That is the writers' coverage, and
  this note only gives them a place to write it.
- Speed budgets beyond one ceiling per app. How fast a screen should be is a separate question.
- Pixel or layout checks.
- Walks on a command line or over plain HTTP. They have no screens, and a response already marks
  the end of each step.
- Moving existing books to the new shape by hand. The book workflow does that on its next run.

## 1b. Claims

From the request:

1. Each screen declares its loading states.
2. Each screen declares the asynchronous requests it makes.
3. A flow gets indirect visibility on those, so it can await them.
4. A screen declares its flow fragments.
5. A screen declares full-state assertions.
6. A flow composes fragments across screens.
13. Hardcoded delays are asking for trouble. A max delay, assuming the app is reasonably
    responsive, keeps a test from running forever. (review, R8 and R10)
14. On a web or mobile app, a check is based on accessibility info and on visible items such as
    labels. (review, R9)
15. A walk acts on an element by its accessible name, and a button's accessible name is its
    label. (review, R11)

From the existing system, read before this note:

7. A flow makes claims only at its start and its end, and each check reads the last step's
   result. (flow node type) *Revised, R2: a web walk observes its start claim after the last
   step, not before the first.*
8. A step that links only a screen or a component adds no step. (flow node type)
9. An interaction claims what it does with `does:`, and a component declares its `states:`.
   (component node type) *Revised, R1: fixtures have no `states:`.*
10. Checks poll up to a three-second deadline before they fail, and the harness waits for a
    fixed quiet window after navigation. (check vocabulary, harness) *Revised, R1 and R8: the
    three seconds are polling deadlines, the quiet window and network idle are fixed waits, and
    all three are durations a walk depends on.*
11. A flow runs only the fixtures it names. (flow node type)
12. Mid-walk checks exist only in hand-written story QA plans. (spot check)

## 2. Parts and concepts

### Level 1: parts

1. **The screen's own account.** What one screen sends for, how it shows it is busy, each settled
   state it can show and how a person perceives it, how a person reaches it, and the moves a
   person can make from each state. It hands this to the walk builder. It never knows which walks
   pass through it, nor which device shows it.
2. **The walk's itinerary.** The world a walk starts in, then the screen states it passes
   through, in order, and the move between each pair. It hands this to the walk builder. It never
   knows how a state is recognised or waited for.
3. **The walk builder.** It turns an itinerary and the screens it names into one concrete walk:
   check the start, act, wait for the screen to settle, check the state, act again. It refuses an
   itinerary whose stops do not join up. It hands the walk to the runner. It never knows the
   device.
4. **The runner.** It performs a walk on a running app, a browser page or a mobile device, and
   records what each wait and check saw. It hands that record to the tally. It never knows the
   book.
5. **The tally.** It reports which declared states and moves no walk reaches, and it builds a
   one-screen walk for each such state. It never knows how a walk runs.

Flow between the parts: when the book is written, the screen's account and the itinerary are
fixed. When QA compiles, the builder reads both and emits walks for the app's device, and the
tally adds one-screen walks for unreached states and counts what every walk is built to pass.
When QA runs, the runner performs each walk, and a walk that fails stops counting for the states
after the failure.

Plain-words test: each screen page says what the screen waits on, what a person sees and hears
in each of its looks, how you get there and what you can do from each look. A walk just names the
looks it passes, in order. Something stitches those into a walk that waits, checks and acts at
every screen, a browser or a phone runs it, and a tally says which looks no walk visited. Two code
bases could fit this. No part is named after an existing module.

### Level 2: concepts

**Shared value type: Perceivable.** One thing on a screen as an assistive technology exposes it:
an element named by its role and accessible name, or by its visible label or text, together with
whether it must be present or absent and the accessibility states it must carry, such as
disabled, busy, checked, expanded or selected. A button is named by its label. Parts 1 and 4 both
use it: part 1 writes it, part 4 reads it from the running screen and acts on it. It never knows a
style class, a markup structure or a test id (added, R9; revised, R11).

**Part 1: the screen's own account**

| Concept | Owns | Never knows |
|---|---|---|
| Screen request | One request the screen sends, named by method and address, and the moment it goes: on arrival or during a passage | what the answer must contain, which belongs to the request's own page |
| Busy sign | The perceivable mark that the screen is not settled, such as a progress indicator, an element marked busy, or a control disabled while it sends | which requests cause it |
| Screen state | The set of perceivables that identify one settled look of the screen, built from the states of the components it holds (R4, R9) | how the screen got there |
| State condition | What must be true for the screen to settle in one state, by reference to the world's named facts, the screen's own entry requirements, or how a request answers (R3) | the perceivables of the state |
| Passage | One ordered run of interactions on this screen, from one of its states to a target state on this screen or another, with the requests it sends (renamed from Fragment, R1) | the walks that use it |
| Way in | How a person reaches the screen from a known start: its address, or the moves that lead to it (added, R5) | the states it settles in |

**Part 2: the walk's itinerary**

| Concept | Owns | Never knows |
|---|---|---|
| Itinerary | The ordered stops of one walk and the claim it ends on | how a stop is recognised |
| Stop | A reference to one screen state the walk must pass, and the passage that leaves it | the state's perceivables and waits |
| World | The arranged starting data and its named facts, by reference to fixtures | the screens |

World is a read-only catalog every part consults. It is the existing fixture, not a new concept.

**Part 3: the walk builder**

| Concept | Owns | Never knows |
|---|---|---|
| Walk | The ordered sequence of act, wait and check steps for one itinerary | the driver calls behind each step |
| Settle wait | The wait for one arrival: the requests the screen or the passage sent have answered, then the busy sign is gone, then one declared state holds, all within the responsiveness ceiling (revised, R8, R10) | which state the stop expects |
| Responsiveness ceiling | The one longest time any screen of the app may take to settle, set once for the app (added, R10) | which wait it bounds |
| Joint | Rejecting a stop whose passage does not leave from it, or does not land on the next stop's state | the world |
| Condition match | Rejecting a stop whose state condition the walk's world does not arrange | the perceivables |

**Part 4: the runner**

| Concept | Owns | Never knows |
|---|---|---|
| Screen reader | Role. Reporting which perceivables the running screen exposes now (added, R9) | the device behind it |
| Actor | Role. Performing one interaction on a perceivable | what it is expected to change |
| Request feed | Role. Reporting the requests the app sent and their answers since a mark (added, R9) | the screen |
| Request watch | Knowing when the declared requests sent after an action have answered | the busy sign |
| Busy watch | Knowing when the busy sign is gone | the requests |
| State watch | Knowing when one of the screen's declared states holds, and which one (added, R8) | which state the stop expects |
| State check | Judging, once, that the state the screen settled in is the one the stop expects (revised, R8) | how the screen was reached |

**Part 4, level 3: variants**

| Variant | Plays | Owns | Never knows |
|---|---|---|---|
| Browser driver | Screen reader, Actor, Request feed | A web app in a browser page, read through the page's accessibility tree | the device |
| Device driver | Screen reader, Actor | A mobile app on a device, read through its accessibility hierarchy | the browser |

The choice of variant belongs to QA compile, which knows the surface the book's app runs on. A
device driver offers no request feed, so a mobile settle wait is the busy sign and the declared
states (A4).

**Part 5: the tally**

| Concept | Owns | Never knows |
|---|---|---|
| Visit record | Which screen states and passages one walk is built to pass (revised, R6) | how the walk was built |
| Gap | A declared state or passage that no walk reaches | why it was missed |
| One-screen walk | A walk that arranges one state's condition, takes the screen's way in, settles and checks that state | the itineraries |

## 3. Invariants

1. **Consecutive stops are joined.** The passage that leaves a stop starts at that stop's state
   and lands on the next stop's state. Owner: Joint.
2. **A check follows its settle.** Every state check in a walk comes after the settle wait for
   that arrival. Owner: Walk. The builder upholds it during construction.
3. **Waits end on events, under one ceiling.** Each wait in a walk ends on an event of the
   screen: a request answered, the busy sign gone, or a declared state holding. The app's
   responsiveness ceiling is the only duration, and crossing it fails the stop with what was
   still pending. No book page names any other duration, and no check polls against one. Owner:
   Settle wait. (revised, R7, R8, R10)
4. **One definition per state.** A walk checks a screen state only through that state's own
   perceivables. An itinerary carries no observation of its own except its end claim. Owner:
   Itinerary.
5. **A busy sign is never a state.** No screen state lists its own screen's busy sign as a
   perceivable that must be present. A transient look is awaited until it goes, never checked
   while it shows. Owner: Screen state.
6. **Declared requests are the screen's requests.** A request the screen sends to the app's own
   API after an action, and that no screen request or passage declares, is a finding on the
   screen. Owner: Request watch. It holds where a request feed exists (A4).
7. **Every declared state is checked.** Each screen state is checked by at least one walk, either
   from an itinerary or as a one-screen walk. Owner: Gap.
8. **A stop is checked before the move that leaves it.** The start stop included. Owner: Walk.
   (added, R2)
9. **A screen's declared states exclude each other.** A settled screen matches at most one of
   its declared states. Two matching at once is a finding on the screen page. Owner: State
   watch. (added, R8)
10. **Walks find elements only by what is perceivable.** Every element a screen state, a busy
    sign or a passage checks or acts on is named by role and accessible name, or by visible label
    or text. A button is named by its label. An element a writer cannot name that way is an
    accessibility finding on the app, not a reason for a style or test-id locator. Owner:
    Perceivable, which refuses to be written from a style or a test id. Screen state, Busy sign
    and Passage uphold it by holding only perceivables. (added, R9; revised, R11)
11. **Every screen declares its states.** A screen page with no screen state is a finding on the
    page. Owner: Screen state. (added, R12)
12. **Every act that settles is followed by a stop.** On a screen flow, each step that acts on a
    screen, other than typing into a field, is followed by a stop: a state or a passage. A flow
    whose first act leaves a screen it never stopped at is a finding too. Owner: Walk's
    itinerary. (added, R12)

## 4. Forces and patterns

### Forces

- F1. Many walks pass the same screens. The walks overlap, and the screens change on their own
  schedule.
- F2. How long a screen takes to settle varies with the network, the data size and the machine.
- F3. Which state a screen settles in depends on the world and on how each request answers.
- F4. Writers are agents paying per token. A walk must stay short to write and cheap to read.
- F5. The validator reads the book without running anything, so declarations must be data.
- F6. Walks grow over time while screens get renamed, restyled and reshaped.
- F7. The same book format serves web and mobile apps, and the two devices expose different
  things: a browser shows its requests, a device does not. (added, R9)

### Between parts

- **One value handed along** (F5): the screen account and the itinerary are data, the builder
  is a pure function that returns a Walk, and the runner interprets the Walk. The validator
  checks joints and conditions on the itinerary and the screen accounts, which needs no Walk
  (revised, R6).
- **Catalog by reference** (F1, F4): the screen account is the one place a state, a request, a
  busy sign, a passage or a way in is defined. Itineraries reference states and passages by
  stable id.
- **Roles and variants** (F7): the runner's waits and checks ask a Screen reader, an Actor and a
  Request feed. Each device is a variant, chosen where QA compiles. (added, R9)

### Inside parts

- Screen account: plain data, sections on the screen page (F5).
- Perceivable: what an assistive technology exposes (F6, F7). Roles, names and labels survive a
  restyle and read the same on a browser and a phone. A style selector does neither.
- Walk: a closed set of three step kinds, act, wait and check, interpreted by the runner (F5).
- Settle wait: derived, never written. It is the screen's arrival requests, or the passage's
  requests, then the busy sign's absence, then any declared state holding (F2). This is the
  "indirect visibility" of claim 3. Waiting for any declared state, not the expected one, lets a
  wrong state fail at once, named, instead of running out the ceiling (R8).
- Responsiveness ceiling: one value per app, with a harness default (F2). Every wait shares it,
  so a slow machine is answered by raising one number, never by editing walks.
- One-screen walk: generated from a state, its condition and the screen's way in (F1, F4). A
  state no itinerary reaches costs the writer nothing extra.
- Stable ids on states and passages (F6). A rename that breaks an itinerary is a Joint failure,
  not a silent skip.

### Claims

1. Re-derived from F2, reshaped: a loading state is a busy sign. It is awaited until it goes,
   never asserted (invariant 5).
2. Re-derived from F2, with invariant 6 added: an undeclared request is a finding.
3. Re-derived from F2 and F4: the itinerary never names a wait. The builder derives each one.
4. Re-derived from F1 as Passage: a run of interactions on one screen, from a state to a state.
5. Re-derived from F1 as Screen state.
6. Re-derived from F1 and F4 as Itinerary and Stop.
7. Rejected for screen walks: each stop is checked. The end claim stays. The start is checked
   first (invariant 8).
8. Reshaped: a step that names a screen state now adds a stop, and the stop is checked.
9. Kept for components: a screen state is built from component states. `does:` stays prose, and
   a passage names its target state as data beside it. (revised, R1, R4)
10. Rejected. The polling deadlines, the quiet window and network idle all go from walks
    (invariant 3). (revised, R7, R8)
11. Kept: the itinerary names its world, and Condition match reads its named facts.
12. Replaced: the walk builder emits the mid-walk checks a story plan writes by hand today.
13. Re-derived from F2 as the Responsiveness ceiling: one bound per app, the only duration.
14. Re-derived from F6 and F7 as Perceivable and invariant 10.
15. Re-derived from F6 and F7: a passage acts through the same Perceivable it checks with, so a
    restyle breaks neither half of a walk.

### SOLID

- Single responsibility: each Owns reads without "and". Settle wait owns one arrival. It orders
  three watches under one ceiling, and it does not perform them.
- Open/closed: a new state, request or passage is a new entry on one screen page, and no
  itinerary changes. A new device is one variant and one line where QA compile chooses.
- Liskov substitution: each driver plays its roles only and extends no other driver.
- Interface segregation: Screen reader, Actor and Request feed are separate roles, so the device
  driver is never asked for a request feed it cannot give.
- Dependency inversion: the watches and the check know the roles, never a driver.

### Open lookups

L1 to L6 are resolved in section 5.

## 5. Mapping onto the existing system

### Revision log

- R1. 1b claims 9 and 10, section 2 Fragment. Fixtures have no `states:`. The three-second
  waits are polling deadlines. The name Fragment collides with the existing `fragment` page type,
  which holds a page's overflow, so the concept is renamed Passage.
- R2. 1b claim 7, invariant 8 added. A web walk observes the flow's `start:` claim after its last
  step (`compile_playwright.py:592`), while the CLI walk checks it first (`compile_cli.py:225`).
- R3. Section 2 State condition. Screens already carry `requires:` (52 of 52 client screens), and
  fixtures expose named `provides` facts. A condition references those, not new fixture states.
- R4. Section 2 Screen state. Components already declare normative `states:`, and the `inert`
  and `actionable` checks already judge a greyed-out control. A screen state composes them.
- R5. Section 2 Way in added. Screens have a route, and components a `leads-to:`, from which the
  compiler finds hops to a screen. A one-screen walk needs that to reach a screen with params.
- R6. Section 2 Visit record, section 4 One value. Coverage is counted at compile time from what
  each scenario is built to cover. A failed run fails its scenario, so a runtime record adds
  nothing. The validator needs only the book, not the Walk.
- R7. Invariant 3. The harness waits on a fixed 500 ms quiet window and on network idle after
  navigation. Both are waste under invariant 3.
- R8. Section 2 Settle wait, State watch, State check; invariants 3 and 9; claim 10. The review
  rejected hardcoded delays. The settle wait now waits for a declared state to hold, and the
  check judges once.
- R9. Section 1, Perceivable, part 4 roles and variants, F7, invariant 10, claim 14. The review
  asked that web and mobile checks read accessibility info and visible labels. The harness
  already walks mobile apps (`maestro_walk`, `compile_maestro.py:426`), so "browser only, no
  role" was wrong.
- R10. Responsiveness ceiling, invariant 3, claim 13, assumption 2. The review asked for a max
  delay so a test cannot run forever. One ceiling per app replaces the five-minute scenario cap
  as the bound a wait fails on.
- R11. Section 1, Perceivable, invariant 10, claim 15, slice 4, assumptions 5 and 6. The review
  extended invariant 10 to actions: a walk presses a button by its label. Component `selector:`
  forms that are a style or a test id become waste for acting too.
- R12. Invariants 11 and 12 added. The client's two screen books hold 64 screens and 43 flows,
  and none declares a state. Every check in slices 1 to 4 judges only what a page declares, so a
  book run left them as they were. An absence has to be a finding for a run to backfill it.

### Parts

| Part | Verdict | Where, and the mismatch |
|---|---|---|
| Screen's own account | Reshape | The screen page type has `route`, `requires`, `params`, `entry`, `code`, `detail` and `verify`. None mints an obligation. States live on components, and moves on interactions and `leads-to:`. The screen needs normative keys of its own. |
| Walk's itinerary | Reshape | The flow page type: `start:`, `steps:`, `end:`. Steps link interactions. A step that links a screen adds nothing (claim 8). |
| Walk builder | Reshape | `compile_journey.py`, `web_walk` (`compile_playwright.py:575`) and `maestro_walk`. Each emits every action, then every observation at the end. The web walk spans one response window. |
| Runner | Reshape | The browser harness (`harness/ostler_qa_browser.py`) and Maestro flows. Both run, and neither knows the book. Their locators are not all perceivable (see Perceivable). |
| Tally | Exists | Coverage from each scenario's static cover list, with a gap per uncovered obligation. One-screen walks exist for component states. |

### Concepts

| Concept | Verdict | Where, and the mismatch |
|---|---|---|
| Perceivable | Reshape | A component locates itself by `selector:` (a style selector, a role selector or `testID=`) and `name:`. The browser resolves role and name, label, text, test id or CSS (`ostler_qa_browser.py:78-90`). The device maps `testID=` to an id and a name to text (`compile_maestro.py:56`), and reads roles from the view hierarchy (`ostler_qa_hierarchy.py`). Style selectors and test ids fail invariant 10. The design is right: screen states, busy signs and passages accept role and name, label or text only, and a component locates itself by its role and its label (R11). The book workflow moves each component on its next run (A6). |
| Screen request | New | A link key on the screen page to endpoint pages, plus the same key on a passage. Today only an invocation's `on:` may link an endpoint (L5). A request is spelled `METHOD /path`, as `emitted(event=...)` already spells it. |
| Busy sign | New | A screen key holding one perceivable. 16 of 52 client screens describe loading in prose only. |
| Screen state | Reshape | Component `states:` are normative per component. A new normative screen key names each state by id and lists the component states and perceivables that make it up. It mints obligations through `NORMATIVE_KEYS_BY_TYPE` (`registry.py:769`). |
| State condition | Reshape | Built on screen `requires:`, fixture `provides` facts (`@fixture.key`) and an interaction's `when:` and `arrange:`. |
| Passage | Reshape | Interaction `does:` is prose and a locator, and it cannot name a target state (L2). A passage is a new screen key: interactions by link, then the target state id. |
| Way in | Exists | The screen route and `walk_hops` over `leads-to:` (`compile_playwright.py:214`), and its Maestro counterpart. |
| Itinerary | Reshape | The flow's `steps:` may name a screen state or a passage, and each one becomes a stop. A flow that names none compiles as today (A7). |
| Stop | New | A step entry naming a state id. |
| World | Exists | Fixtures, run only when the flow names them. |
| Walk | Reshape | The builder emits lines directly. The design keeps lines, ordered act, wait, check per stop. A separate Walk value buys nothing the validator needs (R6). |
| Settle wait | Reshape | Today `quiet()` (`ostler_qa_browser.py:438`), network idle (`:348`, `ostler_qa.py:1811`) and `writes_done()` (`:451`). Maestro's `assertVisible` waits on Maestro's own implicit timeout, a duration nobody in the book chose. The new wait is the declared requests, the busy sign gone and a state holding, under the ceiling. |
| Responsiveness ceiling | New | Today durations are scattered: 3 s per element check (`ostler_qa_elements.py:56`, `:110`, `:279`), 5 s eventually checks (`ostler_qa.py:107`), 5 to 10 s settles, and a 300 s scenario cap (`harness_host.py:35`). The ceiling is one setting per app, kept beside the app's stack settings, with a harness default. The scenario cap stays as the outer guard. |
| Joint | New | Nothing checks that a step starts where the last one ended. `walk_hops` silently fills the gap with hops instead. |
| Condition match | New | Nothing compares a screen's `requires:` with the flow's fixtures. |
| Screen reader | Reshape | The browser reads the accessibility tree through role, label and text lookups. The device reads the view hierarchy. Neither is behind one role today. |
| Actor | Reshape | The step click in `web_walk` and the tap in `maestro_walk` act on whatever locator the component carries, a style selector or a test id included. The Actor takes a perceivable only (R11). |
| Request feed | Reshape | `qa.window()` (`ostler_qa_browser.py:434`) records responses, and `response_for` (`:144`) reads them without waiting. A mark per action is the gap. The device has none. |
| Request watch | Reshape | Built on the request feed, with a wait for named responses. |
| Busy watch | New | Built on the existing `hidden` check, without judging its result as a claim. |
| State watch | New | The perceivable checks read as predicates, evaluated for every declared state of the screen until one holds. |
| State check | Reshape | Each check polls its own deadline today. In a walk it compares the state the State watch saw with the expected one, once. |
| Visit record | Exists | The scenario's cover list (R6). |
| Gap | Exists | One per uncovered obligation. |
| One-screen walk | Exists | `_state_arrivals` and `_arrival_scenario` (`compile_page.py:131`, `:348`) and `_discharge_states_an_interaction_reaches` (`context.py:797`). They extend to screen states. |

### What the existing system has that the design lacked

- Screen `requires:`, `leads-to:` hops, component `states:`, and the `inert` and `actionable`
  checks. Missed concepts, fixed by R3, R4 and R5.
- A mobile walk. A missed variant, fixed by R9.
- The vet step: a route check and a screenshot at the end of a walk. Kept at the end. A stop's
  state check replaces it mid-walk.
- `writes_done()` before a navigation. Waste in compiled walks once every passage's requests are
  awaited at its arrival. Kept for hand-written plans.
- `quiet()`, network idle and the per-check polling deadlines. Waste in compiled walks (R7, R8).
  Kept for hand-written plans, which declare no screen states to wait on.
- Style selectors and test ids as locators. Waste for checks and actions under invariant 10 (R9,
  R11).
- Anchors on headings. The stable ids of section 4 exist already as anchors.
- The web `start:` observed after the walk. A defect, fixed under invariant 8 (R2).

### Claims against both sides

| Claim | Existing system | Design |
|---|---|---|
| 1 loading states | No. Prose only | Busy sign, awaited and never asserted |
| 2 requests | No screen-to-endpoint link | Screen request |
| 3 visibility to await | No. A fixed quiet window | Settle wait, derived |
| 4 fragments | No | Passage |
| 5 full-state assertions | Per component | Screen state |
| 6 composition | No | Itinerary of stops |
| 7 end-only claims | CLI yes, web observes start last | Rejected for screen walks |
| 8 screen step adds nothing | Yes | Reshaped: a state step adds a stop |
| 9 `does:` and states | Yes, components only | Kept, composed into screen states |
| 10 waits | Polling deadlines plus fixed quiet windows | Both removed from walks |
| 11 named fixtures only | Yes | Kept |
| 12 hand-written mid-walk checks | Yes | Replaced by compiled ones |
| 13 one max delay | No. Several fixed durations | Responsiveness ceiling |
| 14 accessibility-based checks | Partly. Style selectors and test ids allowed | Perceivable, invariant 10 |
| 15 act by accessible name | Partly. Style selectors and test ids allowed | Perceivable, Actor, invariant 10 |

## 6. Slices

1. **One web screen checked mid-walk.** On a fixture web app in the compiler's tests, one screen
   declares its arrival request, its busy sign and one settled state, all as perceivables. A
   two-screen flow names that state as a stop. The compiled walk checks its start first, waits on
   the request, the busy sign and the state, checks it, then clicks on. Parts: all five, thinly.
   Concepts: Perceivable, Screen request, Busy sign, Screen state, Stop, Settle wait,
   Responsiveness ceiling, Request watch, Busy watch, State watch, Browser driver. Done when the
   walk passes on the fixture app, passes again with the arrival request slowed to half the
   ceiling, fails at once naming the error state when the screen shows it, fails at the ceiling
   naming the pending request when the request never answers, and names no other duration.
2. **The same screen on a device.** The fixture's mobile twin runs the same screen account through
   the device driver: busy sign, then state, under the ceiling. Concepts: Device driver, Screen
   reader, Actor. Done when the same book page passes on both devices with no device-specific
   line in it.
3. **Every declared state checked.** Screen states mint obligations. A state no flow reaches gets
   a one-screen walk from its condition and way in. Concepts: State condition, Way in, Gap,
   One-screen walk, Condition match. Done when the coverage report lists every screen state of
   the fixture book, and an unreached one is covered by a generated walk.
4. **Passages and joints.** Flow steps name passages. The validator rejects a broken joint, an
   unknown id, an unarranged condition, and a check or an action on an element named by style or
   test id. An undeclared request after an action is a finding. Concepts: Passage, Joint, Actor,
   invariants 6 and 10. Done when a renamed state fails validation on every flow that names it,
   a button found by test id fails validation until it is named by its label, and an extra
   request fails its walk.
5. **Writers write it.** The book skill and the writer prompt teach the new keys, and the book
   workflow rewrites one client book on its next run. Done when the six-walk sample moves from
   12 of 30 states checked mid-walk to 30 of 30.

## 7. Assumptions

1. **Assumption:** writers can name each screen's requests, busy sign and states from the app's
   source within a book run's budget. **Decided:** screen keys written by the book workflow, not
   inferred by QA. **Basis:** writers already wrote 79 component states on 29 screens and 240
   `does:` bullets in one client book. **If wrong:** section 2 part 1, slice 5.
2. **Assumption:** every screen of an app settles well inside one shared ceiling on the QA stack,
   and a default of 30 seconds fits the apps seen so far. **Decided:** one ceiling per app, never
   per screen or per wait. **Basis:** the existing arrange timeout is 30 s
   (`ostler_qa_browser.py:64`), and no client screen has needed more. **If wrong:** a slow report
   screen forces either a raised ceiling for the whole app or a per-screen override, which
   re-derives Responsiveness ceiling and invariant 3.
3. **Assumption:** every look a screen settles in during a walk is one of its declared states.
   **Decided:** the settle wait ends when any declared state holds. **Basis:** none. **If
   wrong:** an undeclared look fails at the ceiling, naming the screen page to complete. That
   costs one ceiling of run time per such walk.
4. **Assumption:** on a mobile app, a screen shows its busy sign for as long as any request it
   sent is pending. **Decided:** the device settle wait has no request step, and invariant 6 is
   web only. **Basis:** none; the device driver has no request feed. **If wrong:** mobile walks
   flake on screens whose content arrives after the sign goes. Re-derive Request feed with a
   device variant, such as a proxy.
5. **Assumption:** the client apps expose roles and accessible names for the elements their
   states depend on and the controls a walk presses, an icon button included. **Decided:**
   invariant 10 refuses style and test-id locators in checks and actions. **Basis:** the browser
   already resolves most component locators by role and name. **If wrong:** writers file
   accessibility findings instead of states, and slice 5 falls short of 30 of 30 until the app
   is fixed.
6. **Assumption:** existing books keep their style and test-id locators until their next book
   run. **Decided:** the validator refuses them on every component a screen state, a busy sign
   or a passage names, and warns on the rest, so today's books stay valid. **Basis:** section 1
   puts hand migration out of scope, and books change only through the book workflow. **If
   wrong:** invariant 10, slice 4.
7. **Assumption:** a flow that names no screen state still compiles as today. **Decided:** the
   new keys are additive, and books move on their next workflow run. **Basis:** section 1 puts
   hand migration out of scope. **If wrong:** Itinerary, slice 5.
8. **Assumption:** a request named by method and path template matches the requests the app
   sends, including ids in the path. **Decided:** Screen request uses the `METHOD /path` spelling
   the `emitted` check already reads. **Basis:** that check exists and passes on client plans.
   **If wrong:** Screen request, Request watch, invariant 6.
9. **Assumption:** invariant 6 applies only to the app's own API origin. **Decided:** analytics,
   fonts and third-party calls are ignored. **Basis:** endpoint pages exist only for the app's
   API. **If wrong:** invariant 6.
10. **Assumption:** checking every stop adds seconds, not minutes, per walk. **Decided:** every
    stop is checked, every run. **Basis:** a client flow passes 2.06 screens on average, at most
    6. **If wrong:** slice 1 done-when, invariant 8.
11. **Assumption:** a client book's value shows only after its next book run, hours after slice 5
    lands. **Decided:** slices 1 to 4 prove the change on fixture apps. **Basis:** books change
    only through the book workflow. **If wrong:** slice order.
12. **Assumption:** the six-walk sample that found the gap represents the client book's 36 flows.
    **Decided:** slice 5 measures on that sample. **Basis:** the spot check. **If wrong:** slice 5
    done-when.
