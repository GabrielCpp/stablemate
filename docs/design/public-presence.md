# Public presence: an ecosystem a visitor adopts without a clone

**Disclosure.** The order slipped in two ways. `AGENTS.md` loaded on its own and lists
this repo's packages and its rules. I also read `README.md` and the GitHub stats before
writing sections 1 to 4. Every part and concept below was tested against "would I have
named this from floci and the adoption domain alone?" Design decisions carried by that
context are claims C13 to C15 in section 1b. The second pass (R6 to R10) ran the
undeclared-assumption sweep of section 7. The third pass (R11 to R16) re-derives the note
after the maintainer replaced the audience, named the product, and asked for the whole
ecosystem seen by a user who has no checkout. The fourth pass (R17 to R24) applies an
outside review and the base library's new pin to farrier's release tag. R25 drops
test-first as a goal. R26 keeps the `stablemate` pack for this repo and has the reader
add skills of their own. R27 moves the base library's two packs from the reader's repo
to their home. The fifth pass (R28) adopts an outside strategy review: its reader, its
promise, its line between what installs today and what is direction, and its first
screen.

## 1. Problem

A developer uses Claude Code, Codex or Copilot every day on a real codebase. They have
written a `CLAUDE.md` or an `AGENTS.md` full of rules: run the suite before saying done,
keep the adapter out of the domain, ask when unsure. They do not know which of those
rules the agent followed, so they read every diff by hand. "Done" from the agent tells
them nothing yet (R28). They land
on stablemate from a link. The first screen argues against a bash loop they do not run,
names seven tools in a stable-yard vocabulary before it shows a result, and the one
command they can try proves only that the install worked. They leave. Four months after
going public the repo has 1 star and 0 forks.

**Done looks like this to that developer:**

- The first screen of the README and of the site says, in three lines, who it is for,
  what it replaces and why it is better. The thing it replaces is their agent plus a
  rules file (R11). The headline is "Don't take your agent's word for it", and the one
  line under it is "stablemate tests, reviews and QAs the work before you see it" (R28,
  R29).
- The first screen shows one real question a run asked its human, and the answer that
  let it continue (R28, A20).
- Every claim on either surface either runs after the install block or sits on a dated
  Status page as direction. No first-screen claim or picture shows a thing the install
  block does not install (R28).
- The first screen shows one path through the ecosystem: the session they already run,
  then the plan, then the work handed to a workflow, then the moments the workflow asks
  for them. Each tool appears at the step where the user meets it, as the answer to one
  question (R13).
- Every step on that path runs from PyPI with no clone of this repo. One install line
  puts the whole path on the `PATH` (R13).
- Within an hour of installing, the reader has scaffolded a workflow around one check,
  run it on a public sample repo whose one test fails, and watched the run refuse to
  finish until the test passed. The same command then takes a check from their own repo
  (R12, R20, A3).
- Until launch, the README is the main public page. At launch, a site at a stable URL
  carries the pitch, the path, a replay of a real multi-day run and one page per tool,
  and it renders on a phone in both themes (R30).
- Every number on either surface names the release and the date it was measured on.

**Out of scope:**

- Changing what the shipped workflows do or how well they do it.
- A first run that shows the full roadmap-to-QA path. It takes days, so the site shows
  it as a replay (R5).
- Publishing `saddlebag` and `paddock`. No step of the user's path needs them (A12).
- Growth work outside the repo and the site: posts, talks, paid placement.
- Sponsorship tiers and a sponsor wall.
- A custom domain. The site ships on GitHub Pages first (A16).

## 1b. Claims

From floci's README (github.com/floci-io/floci) and site (floci.io), read 2026-10-02:

1. A three-line pitch built on removed pain: "No account. No auth token. No feature
   gates. Just `docker compose up`." (README)
2. A comparison table against a named incumbent with measured numbers: startup ~24 ms
   against ~3.3 s, memory, image size. (README)
3. A three-command quick start: `floci start`, `eval $(floci env)`, one AWS call. (README)
4. A `curl -fsSL https://floci.io/install.sh | sh` installer. (site)
5. Tabbed code demos, one tab per cloud provider. (site)
6. "Teach your agent once": a paragraph the user pastes into their coding agent. (site)
7. Releases on the 1st and 3rd Tuesday of each month, plus dated nightlies. (README)
8. Docs on MkDocs Material, one page per emulated service. (floci.io/floci)
9. A demo video embedded in the README. (README)
10. Sponsor tiers, a Slack invite, a contributor grid and a star-history chart. (README)
11. A compatibility matrix: 2,576 tests across 5 SDKs and 3 IaC tools. (README)
12. A single native binary that starts in 24 ms. (README)

From context that loaded on its own (`AGENTS.md`):

13. The repo is a uv workspace of separately versioned packages.
14. No ad-hoc shell scripts. A capability goes into a CLI or a guard under `scripts/`.
15. No private project name may appear anywhere in the tree.

## 2. Parts and concepts

### Level 1: parts

1. **Positioning.** Owns who the project is for, the pain it removes, the one-line
   promise, the alternative it replaces, and the role each tool plays in the whole. Never
   knows how the project is packaged. Hands the pitch and the role map to the Storefront.
2. **Path.** Owns the steps a user takes from nothing installed to their own workflow,
   with no clone: what each step needs, what it shows and how long it takes. Never knows
   how pages are laid out. Hands the step texts to the Storefront and the Reference (R13,
   formerly First run).
3. **Proof.** Owns the evidence a skeptic can check: numbers, a comparison against the
   alternative, a recording, a replay. Never knows which page shows it. Hands
   measurements to Positioning, which cites them, and to the Storefront, which shows them.
4. **Storefront.** Owns the README's first screen and the landing page, and publishing
   them. Never knows how a number was measured. Links into the Reference.
5. **Reference.** Owns the pages a user returns to: guides, one page per tool, settings.
   Never knows the pitch.
6. **Pulse.** Owns the signals that the project is alive and open: releases on a
   calendar, a changelog, a dated status, a place to ask, a path to contribute. Hands
   live badges to the Storefront.

**Flow.** At release time, the Path's checks install every step from the built
distributions on a clean machine and run it with the agent stubbed. At each minor
release, Proof reruns the compliance trial, which takes hours (F8). Positioning's
differentiators cite those numbers and runnable steps. At publish time, the Storefront
assembles the pitch, the role map, the path, the numbers and the badges into the README
and the landing page, and links to the Reference. Pulse acts on its own calendar, and
each release it cuts triggers the release-time moment above.

In one paragraph for a non-engineer: say who it is for and what it beats; show the one
path through the tools, each tool at the step where you meet it; make every step work
from a plain install; prove the claim with numbers anyone can rerun; show all of that on
the first screen of the repo and of a website; keep a manual for people who stay; and
show that someone is home.

### Level 2: concepts

**Positioning**

| Concept | Owns | Never knows |
|---|---|---|
| Audience | the one reader every page speaks to | the package layout |
| Pain | that reader's experience today, in their words | the fix |
| Promise | the one-sentence outcome, true after the install block (revised, R28) | how it is measured |
| Incumbent | the alternative the reader uses today: the same agent with the same rules written in a rules file (revised, R11) | stablemate's internals |
| Differentiator | one claim that separates stablemate from the Incumbent, citing one Measurement or one runnable step | the measuring method |
| Tool role | one tool's one question in the user's words, and the step of the Path where the user meets it (added, R13) | the tool's commands |
| Objection | one doubt the reader raises before installing, with the page's answer (added, R28) | the Path's order |

The Promise names what stablemate refuses to accept, and not the reader's rules. "Holds
the agent to your standards" is an overclaim, because the skills a run loads are the
base library's plus what the reader writes. "Checked the way you would check a
colleague's" is an overclaim too, because the workflow fixes the checks and the reader's
judgment does not. "Runs fixed gates, and loads your skills into each gate" is true
today (R28, R29). The line under the headline stays one line. The gate question on the
same screen shows that a run asks when it cannot decide, so the line does not say it.

The direction, stated on the Status page and nowhere as a present fact: a developer
hands work to the agent subscription they already pay for and gets back a pull request
that passed the gates a colleague's would. Those gates are tests written against the
story, a review from a context that never saw the implementation, QA against the
feature's own documentation, and a question to the human when the run cannot decide.
The standards the gates load are the reader's own, installed once across every agent
CLI they use. Other people publish workflows the way they publish packages (R28).

The Objections, ranked by how early the reader raises them (R28):

1. "This runs with permissions off on my machine for days." The first screen says, in
   one sentence before the install block, that isolating a run is the reader's job (A7).
2. "I need a roadmap in your format before anything happens." The First win needs none
   (A5).
3. "What does a run cost?" The Handoff guide answers once the Replay's run has measured
   it (A8).

Shared reference: the **role map**, the list of Tool roles, is a read-only catalog that
Positioning owns and the Path, the Storefront and the Reference consult. It is the one
place a tool's purpose in the whole is written.

**Path**

| Concept | Owns | Never knows |
|---|---|---|
| Install line | one command from nothing to every step's command on the `PATH` | which distributions it pulls |
| Step | one moment on the path: its input, its command, its duration, and what the user sees (added, R13) | the other steps |
| First win | the step that shows the core mechanism within an hour: a scaffolded workflow runs on a public sample repo with one seeded failing test and cannot finish until the test passes (added, R12; revised, R20) | the shipped workflows |
| Workflow scaffold | a new workflow package, from a template carried inside the install, with one agent turn and one check (added, R12) | the reader's rule |
| Agent recipe (role) | the commands that run one workflow under one agent CLI | which agent CLI the page shows next to it |
| One recipe per agent CLI (variants) | the flags and setup one CLI needs | the other CLIs |
| Agent brief | what the reader's own interactive agent knows about operating the ecosystem | the human quick start |

The Steps, in order (A5, A6, revised R19):

1. **First win.** The reader scaffolds a workflow around one check and runs it on the
   public sample repo, whose one test fails. The run loops until the test passes. The
   reader then points the same command at a check of their own. Under an hour (A3, A4).
2. **Standards.** The reader installs the base library's `general` and `stablemate`
   packs into their home, once for every repo, and complements them with skills of their
   own, kept in a library of their own that farrier layers over the base (R26, R27).
   Their repo selects only what it alone needs, such as a stack pack. Their next session carries the standards and the skills that plan
   and operate the rest. The first
   install needs git and the network, because the library is fetched at the release
   that matches the installed tool. Same day (A18).
3. **Intent.** The reader writes a roadmap in their interactive session and saves it in
   the folder the planning workflow reads. Nothing checks it before the planning run
   reads it. An hour or two of their time (R22).
4. **Handoff.** The reader's repo needs a roadmap and a docs graph. The planning
   workflow turns the roadmap into stories. The coding workflow builds them, tests them,
   reviews them, documents them and runs QA. Hours to days, wherever the reader chooses
   to run it (A7, R23).
5. **Step in.** A run parks on a question its flow raises. The reader answers it from
   the dashboard and the run continues at once.

The choice of which Agent recipes to show belongs to the Storefront's landing page,
which lists them as tabs.

**Proof**

| Concept | Owns | Never knows |
|---|---|---|
| Measurement | one number with its unit, its method, its release and its date | which claim cites it |
| Compliance trial | one set of tasks run twice with the same rule text: once with the rules written in a rules file, once with the rules as workflow checks, scored by the rules broken at the end (added, R11) | the reader's rules |
| Comparison | the table of Measurements taken on both arms with one method | how a Measurement was produced |
| Recording | a replayable capture of one First win | where it is embedded |
| Exhibit | one real artifact a run produced, shown as is | the run that produced it |
| Replay | a real multi-day run's timeline: stories, gates answered, cap sleeps, resumes, QA verdict | how the run was started |

**Storefront**

| Concept | Owns | Never knows |
|---|---|---|
| First screen | logo, Promise, one paragraph naming the Incumbent, the isolation sentence, Install line and one real gate question with its answer, above the fold (revised, R28) | the Reference |
| Landing section | one block of the landing page with one job: path map, recipes, why, replay | the other sections |
| Identity | name, logo, palette and voice | the content |
| Publisher | building the site and deploying it on merge | what a page says |

**Reference**

| Concept | Owns | Never knows |
|---|---|---|
| Guide | one task, start to finish | the tool internals |
| Tool page | what one tool does and its commands, opened by its Tool role | the other tools |
| Settings reference | every config key and environment variable | why a default was chosen |
| Agent index | a machine-readable map of the docs for coding agents | page styling |

**Pulse**

| Concept | Owns | Never knows |
|---|---|---|
| Release train | cutting a release on a fixed calendar | what the commits contain |
| Changelog | what changed, per release, per package | the calendar |
| Badge | one live status shown on the first screen | the layout |
| Status page | each public claim's state, installable today or in progress, with its date (added, R28) | how the claim is worded |
| Channel | the public place to ask and propose | the issue tracker |
| Contributor path | how a stranger lands a first change | the release mechanics |

Shared value type: **Measurement** is read by Positioning and the Storefront and owned by
Proof.

## 3. Invariants

1. **Every Differentiator cites a Measurement that names its release and date, or a Step
   the reader can run.** Owner: Differentiator. The site build fails on a claim with
   neither. Upheld by Measurement, which records its release (revised, R11).
2. **Every Step runs from the published distributions and the library at their
   release.** CI checks it at two moments, in a clean environment with no checkout and
   no `stablemate_dir`. On every merge it installs the built wheels by path, and an
   install by path fetches the library from `main`. After each release it installs from
   PyPI, and that install fetches the library at the release tag. Both moments run each
   Step's command with the agent CLI stubbed. Both fail on any command, template or
   link that resolves only inside a clone. Owner: Step (added, R13; revised, R18).
   Upheld by Workflow scaffold, which carries its template inside the install.
3. **The README, the landing page and the getting-started Guide show one quick-start
   text.** Owner: Install line. Upheld by Publisher, which includes the text and never
   copies it.
4. **Each tool is introduced by its Tool role, at its Step, and nowhere earlier.** The
   first screen names no tool the path does not reach. Owner: Tool role (added, R13).
5. **The Comparison shows only rows measured on both arms with the same rule text, and
   prints that text.** Owner: Comparison (revised, R11, A2).
6. **No private project name appears on a published page.** Owner: Publisher. It runs
   the repo's existing public guard over the built site.
7. **Every page renders at phone width with no horizontal scroll, in both themes.**
   Owner: Publisher.
8. **Every claim on a public page either runs after the install block or appears on
   the Status page as in progress, with a date.** No first-screen picture shows a tool
   the install block does not install. Owner: Status page. Upheld by Differentiator and
   First screen (added, R28).
9. **The first two screens name `stablemate` and the commands the reader types, and
   nothing else.** Every other tool goes by its job: the dashboard, the docs checker,
   the skill library. Tool pages use the real names from their first heading. Owner:
   First screen (added, R28).

## 4. Forces and patterns

**Forces**

- F1. Numbers change every release. Two surfaces show them.
- F2. The quick-start text appears on three surfaces and rots when a command changes.
- F3. The agent CLI varies independently of the workflow. Five are supported today, and
  more will come.
- F4. One maintainer keeps the site up. It must cost nothing to host and little to
  change.
- F5. Screens change, so a hand-made recording goes stale.
- F6. A visitor decides in seconds. The first screen must answer "what does this beat?"
  before anything else.
- F7. The full path from roadmap to QA takes days, so no visitor can watch it live. Only
  a capture of a real run can show it.
- F8. A compliance trial takes hours of agent time and quota on each arm. A recording
  takes minutes. The two cannot share a cadence.
- F9. The tools release on their own clocks, but the user meets them as one path. A
  combination of versions that was never tested together reaches a user the day any one
  tool releases (added, R13).
- F10. A user without a clone sees only what the installed distributions carry and what
  their pages link to. Instructions that say "copy this directory" or "run from the
  source repo" fail for that user, and on the maintainer's machine the checkout hides the
  failure (added, R13).
- F11. The project's direction runs ahead of its install, and both change every release.
  A reader who meets one claim they cannot run stops trusting the ones they can (added,
  R28).

**Between parts**

- One value handed along (F1, F2, F6). Proof writes one measurements file. The Install
  line's text lives in one snippet file. Positioning's role map lives in one data file.
  The README and the site render from those files. No surface holds its own copy.

**Inside a part**

- Role map: a data file rendered into the README's tool table, the site's path map and
  each Tool page's header (F6, F9).
- Install line: one umbrella distribution that pins a tested set of tool versions and
  exposes each tool's commands (F9).
- Step: a plain value. The Path is an ordered list of them. No variation.
- Workflow scaffold: a template package shipped inside the workflows distribution, which
  is on PyPI today. The umbrella exposes its command like every other. CI scaffolds and
  dry-runs it on every merge (F10, invariant 2, revised R21).
- Compliance trial: a rerunnable benchmark task run by hand at each minor release (F8).
- Comparison: a table rendered from the measurements file (F1).
- Agent recipe: role and variants, one variant per agent CLI. The landing page's list of
  tabs is the one place the choice is made (F3).
- Publisher: a static site generator in the repo's own language, built and deployed by
  CI to free static hosting (F4).
- Recording: captured from the First win against a real agent CLI, by a capture command
  the maintainer reruns each release (F5).
- Replay: a sealed run directory, rendered into a static page by the Publisher (F7).
- First screen: an inverted pyramid. Promise, a paragraph naming the Incumbent, the
  isolation sentence, install line, one real gate question, in that order. The
  Incumbent comparison and the path map open the second screen (F6, revised R28).
- Status page: one claims file, each row with its state and date, rendered into the
  page. CI fails when a first-screen claim's row is in progress, on the README until
  launch and on the site after it (F11, invariant 8, R30).
- Everything else is a plain value or a plain page.

**Claims**

| Claim | Verdict |
|---|---|
| C1 pitch of removed pain | Re-derived from F6 as Pain and Promise. |
| C2 table against a named incumbent | Re-derived from F6 as Incumbent and Comparison. Its rows are mechanisms with a runnable Step until the Compliance trial measures them (R11). |
| C3 three-command quick start | Re-derived as Install line plus First win. |
| C4 `curl \| sh` installer | Rejected. A Python tool already installs in one line with `uv tool install`, and C14 forbids the script. |
| C5 tabs per provider | Re-derived from F3 as Agent recipe tabs per agent CLI. |
| C6 "teach your agent once" | Re-derived as Agent brief. The reader works in an interactive session, so their agent is the second reader of every page. The Standards step already installs the operating skills (R13). |
| C7 release calendar | Calendar re-derived as Release train. Nightlies rejected: no user asks for builds of `main`. |
| C8 MkDocs Material, page per service | Re-derived from F4 as Publisher and Tool page. |
| C9 demo video | Re-derived from F6 as Recording. |
| C10 sponsors, Slack, contributor grid, star chart | Channel re-derived. The rest is out of scope or anti-proof at 1 star. |
| C11 compatibility matrix | Re-derived as invariant 2 run per agent CLI recipe, only once each recipe has a smoke run. |
| C12 single native binary | Rejected as a mechanism. Its force, one install line, is met by the umbrella distribution. |
| C13 separately versioned packages | Re-derived from F9: the umbrella pins a tested set and hides the split from the user. |
| C14 no shell scripts | A constraint. Rejects C4. |
| C15 no private names | Re-derived as invariant 6. |

**Open lookups**

- L1. Is there one distribution that installs every Step? Decides the Install line.
- L3. Does the benchmark harness already produce a publishable number? Decides
  Measurement.
- L5. Where can a site's source live without colliding with an existing docs tree?
  Decides Publisher.
- L6. Does a run's event log record cap sleeps? Decides Replay.
- L7. How long does one agent turn take? Decides the First win's promise.
- L8. How does a user start a workflow of their own today? Decides Workflow scaffold
  (added, R12).
- L9. Does the Standards step install the skills the Intent and Step-in steps need?
  Decides Agent brief (added, R13).
- L10. Where does a handed-off run execute for a user with no clone? Decides the Handoff
  Step (added, R14).

**SOLID check.** Each Owns reads without "and". Adding a sixth agent CLI adds one recipe
and one line in the tab list. Adding a tool adds one row to the role map and one Tool
page, and changes no Step that does not use it. Recipes are kinds of Agent recipe only.
The landing section never knows the variants, only the role. No change to section 2.

## 5. Mapping onto the existing system

**Revision log**

- R1. Section 2, Install line: "one command" now means a `stablemate` distribution on
  PyPI. L1 found the install is two tools today and the dashboard is not on PyPI.
- R2. Section 2, Incumbent: named as "a bash loop around an agent CLI". Superseded by
  R11.
- R3. Section 2, Proof: added Exhibit. The repo has a feature book and QA reports the
  design lacked, and they are the product's own output.
- R5. Sections 1, 2, 3 and 6: no canned demo. A Replay of a real run shows the multi-day
  path. The maintainer pointed out that a coding run needs authored stories, authoring
  needs a roadmap, and a run takes days.
- R4. Section 6: the measured comparison moved after the site skeleton. L3 found no
  publishable number exists yet.
- R6. Sections 1, 2 and 4: durability drills split from the quality trial. Superseded
  by R11, which drops the drills.
- R7. Section 2: added Status envelope and Stop rule for a prompt-file loop. Removed by
  R11.
- R8. Section 1: "within minutes" became "after the first agent turn". L7 found a median
  turn of 8.2 minutes and a 90th percentile of 18.9 minutes over 607 recorded turns.
- R9. Sections 2 and 6: the Replay needs cap sleeps in the event log, and they are not
  there (`workhorse/workhorse/runner/caps.py:60-90`).
- R10. Section 6: slice 1's done-when is marked unverified.
- R11. Sections 1, 2, 3, 4, 6 and 7: the maintainer replaced the audience on 2026-10-02.
  The reader works with an agent interactively and wants it held to a process, not only
  to what they asked: "You may write DO this and Don't do that; but you don't really know
  what the agent will actually do." The bash-loop comparison was not understood. The
  Incumbent became the same agent with the same rules in a rules file. The `loop`
  workflow, the Status envelope, the Stop rule and the fault drills are removed. The
  quality trial became the Compliance trial. The README first screen shipped in
  `b125b2da` now argues against the wrong incumbent.
- R12. Sections 1, 2 and 6: the maintainer named the product on 2026-10-02: the
  workflows and the tooling to build new ones, not this repo's own configuration. Added
  First win and Workflow scaffold. The repo's own Stop review gate and its write guards
  leave the pitch.
- R13. Sections 1 to 4: the maintainer asked for stablemate as an ecosystem in which
  each tool has a purpose, seen by a user with no checkout. First run became Path, with
  Steps. Added Tool role and the role map, invariants 2 and 4, forces F9 and F10.
- R14. Section 2, Path: added Run place. L10 found isolated runs need a clone: the
  Docker harness is "not part of the `workhorse-agent` PyPI package" and "lives in the
  source repo" (`workhorse/docs/DOCKER.md:3-7`), and the generated launcher reads
  `stablemate_dir` (`farrier/farrier/launcher.py:35`). Removed by R16.
- R15. Section 6: the dashboard ships as `stablemate-groom` as part of this work, by the
  maintainer's decision on 2026-10-02. A10 became a decision.
- R16. Sections 2, 3, 4, 6 and 7: Run place removed. The maintainer said on 2026-10-02
  that Docker support is a draft, that the project will publish no run image, that the
  reader is responsible for isolating a run, and that no public surface mentions Docker.
  The Handoff runs where the reader starts it. Slice 4 no longer publishes an image.
- R17. Section 5, comparison: the row "Write a failing test first" became "Keep the
  linter clean". Nothing in the engine or the scaffold orders a failing test before the
  implementation, so the row promised a step the reader could not run.
- R18. Sections 2 and 3: farrier now fetches the base library at its own release tag,
  and a farrier installed from a checkout or a URL tracks `main` (`a28fa969`). The
  Standards step names git and the network. Invariant 2 runs at both moments (A18).
- R19. Section 2, Steps: First win moved ahead of Standards. It needs no library in the
  reader's repo, and it is the step that shows the mechanism.
- R20. Sections 1, 2 and 6: the First win runs on a public sample repo with one seeded
  failing test, and slice 1 records its wall-clock time as the first Measurement. A3's
  basis came from book turns, not from a small coding task on Claude.
- R21. Sections 4 and 6: the scaffold ships in `workhorse-workflows` as `workhorse-new`,
  because that distribution is on PyPI today. Old slice 3 becomes slice 1, old slice 1
  becomes slice 2, and old slice 2 becomes slice 3, so the first screen points at a win
  the reader can run from today's install. Log lines before R20 use the old numbers.
  The umbrella carries no command of its own.
- R22. Sections 2, 5 and 6: no roadmap validator exists. The author workflow reads the
  one roadmap under `docs/roadmaps/`
  (`workflows/src/workhorse_workflows/author/shared/roadmap.py:11-13`). The Intent step
  drops the validator, slice 3 drops the roadmap check from CI, and ostler moves to the
  Handoff step in the role map.
- R23. Sections 2 and 6: a run parks only where its flow raises a gate
  (`workhorse/workhorse/pyflow/transitions.py:123`,
  `workflows/src/workhorse_workflows/coder/review/flow.py:149-228`). Slice 4 seeds a
  roadmap that forces one gate and names that gate in its done-when. The Handoff step
  lists its repo prerequisites (A19).
- R24. Sections 5 and 6, Agent brief: the `stablemate` pack's description is stale and
  speaks to the maintainer. It promises five commands, among them `babysit-run`, which
  fixes stablemate itself. The pack ships `prompts: []`, and `grill` and `brainstorm`
  come from the `general` pack (`base-library/packs/general.yml:12-14`). Slice 8 starts
  by splitting the maintainer's skills out of the pack a user installs.
- R25. Section 1: test-first is no longer a goal, by the maintainer's decision on
  2026-10-02. "Write the test first" left the reader's example rules, and no row, Step
  or slice promises a red test before the implementation. The First win's seeded failing
  test stays, because it is the check the run loops on, not an order of work.
- R26. Sections 2 and 6, Standards and slice 8: the `stablemate` pack serves this repo,
  by the maintainer's word on 2026-10-02. A reader complements the base library with
  skills of their own in an overlay library (`docs/INSTALL.md`, `farrier config
  set-library`). Slice 8 no longer splits the pack. Its only pack change is a
  description that states what the pack ships. This reverses the split R24 planned.
  Its line on `farrier init` is revised by R27.
- R27. Sections 2 and 5, Standards and Agent brief: `farrier init` seeds no pack, by the
  maintainer's word on 2026-10-02. The `general` and `stablemate` packs hold for every
  repo the reader works in, so they belong in the user library that `farrier install
  --user` renders into the home. `init` prints a proposed `[user_library.claude]` table
  that selects both, and writes nothing to the home config. A repo install that selects
  nothing succeeds and says nothing about skills. Codex and Copilot take no prompts at
  user scope, so their readers lose the two `implement-plan` commands. The maintainer
  judged that loss small. On a terminal, `init` asks whether to write that table and
  install it, and a yes does both.
- R28. Sections 1 to 4 and 6: the maintainer adopted an outside strategy review on
  2026-10-02. The reader reads every diff by hand. The Promise became "Your agent's work,
  checked the way you would check a colleague's", which names gates and not the reader's
  rules. Added Objection, Status page, force F11 and invariants 8 and 9. The first screen
  trades the comparison for one real gate question, and the comparison opens the second
  screen. The groom screenshot under today's install block (`README.md:33`) breaks
  invariant 8, because that block cannot install groom.
- R29. Sections 1, 2 and 7, Promise: the maintainer judged the review's headline an
  overclaim on 2026-10-02. "The way you would check" promises the reader's own standard,
  and the workflow's checks are fixed. The Promise became "Don't take your agent's word
  for it", with one line under it. A21 now tests that line.
- R30. Sections 1, 4 and 6: the README is the main public page until launch, by the
  maintainer's word on 2026-10-02. A separate site before launch would split the few
  readers the project has across two places. Slice 5 waits for the launch call, and
  slice 6 embeds into the README until the site exists.

**Positioning: Reshape.**

| Concept | Verdict |
|---|---|
| Audience | Reshape (R11). The README speaks to "teams adopting an AI-native SDLC" and, since `b125b2da`, to people who loop an agent CLI. |
| Pain | Reshape (R11). The first screen's pain is a loop dying at 3am. |
| Promise | Reshape (R11, R28). "Your agent loop dies at 3am. stablemate's doesn't." targets the wrong reader. |
| Incumbent | Reshape (R11). The bash loop on the first screen becomes "your agent plus a rules file". |
| Differentiator | Reshape. The rows below are mechanisms the engine supports today (`workhorse/docs/AUTHORING.md:162-202`: states return the next state, a turn returns a typed reply, plain code decides). None has a Measurement. |
| Tool role | Reshape. "What's in the box" (`README.md:177-195`) gives each package a role, but as an engine part, not as a question the user asks, and it lists tools no Step reaches. |
| Objection | New (R28). No page says that a run acts without asking, and none states a cost. |

The first-screen comparison this mapping supports, each row runnable once slice 1
lands (revised, R17):

| You write in CLAUDE.md | What the agent does | As a workflow step |
|---|---|---|
| "Keep the linter clean" | Leaves the warnings it added | A check runs the linter, and the run moves on only when it reports nothing |
| "Run the tests before saying done" | Says done | The run moves on only when the suite passes |
| "Get it reviewed" | Reviews its own work in the same context | A separate turn returns a verdict, and a finding loops back |
| "Ask me if unsure" | Guesses | The run parks on a question and waits for your answer |
| "Keep going overnight" | Stops at the usage limit | Sleeps until the reset and resumes from its checkpoint |

The role map, in the user's words:

| Tool | The question it answers | Step |
|---|---|---|
| workhorse | Will the process run as written, even overnight? | First win, Handoff |
| farrier | Do all my repos and agent CLIs follow the same standards? | Standards |
| workflows | Who does the work? Planning, coding, research | First win, Handoff |
| ostler | What does the product promise, and does the code still keep it? | Handoff (R22) |
| groom | Where do I step in, and what did the run do? | Step in |
| saddlebag | How does a run log into my app without the agent seeing the password? | none yet (A12) |
| paddock | Did my change to a prompt or a workflow make the result better? | none yet (A12) |

**Path: Reshape.**

| Concept | Verdict |
|---|---|
| Install line | Reshape (R1, R15). Today it takes two `uv tool install` lines (`README.md:220-224`). groom is unpublished because its PyPI name is taken. A tool install exposes only the named package's commands (`README.md:231-234`), but uv 0.11 has `--with-executables-from`, so `uv tool install stablemate --with-executables-from workhorse-workflows,farrier,stablemate-groom` lands every command in one environment. New: a `stablemate` distribution pinning a tested set of `workhorse-workflows`, `farrier` and `stablemate-groom`, with no command of its own (A11, R21). |
| Step | New. The README's "From intent to evidence" (`README.md:59-77`) walks a story through the tools, but from the tools' side and with no input, command or duration per step. |
| First win | New (R12). The install check is `workhorse-loop-runner run --dry-run`, which proves the install and runs no agent (`README.md:285-300`). |
| Workflow scaffold | New (R12). L8: the authoring guide says to copy the `loop_runner/` directory and its `[project.scripts]` row (`workhorse/docs/AUTHORING.md:14-21`, `:113-114`) and links the source on GitHub. A user with no clone has that directory only inside a tool environment. New: `workhorse-new NAME --check CMD` in `workhorse-workflows` writes a package with one agent turn, one check node that runs `CMD`, and a transition back to the turn with the check's output until it passes (R21). |
| Run place | Reshape (R14), revised to removed (R16). The Docker harness is a draft and stays off every public surface. |
| Agent recipe | Reshape. The README lists `--cli codex\|copilot\|cline\|opencode` in one line. |
| Agent brief | Reshape (R24, revised R26 and R27), through the Standards step. L9: `farrier init` seeded `packs: [general, stablemate]` before R27 moved both packs to the user library. The `stablemate` pack ships the farrier, groom, ostler and workhorse skills and no commands (`base-library/packs/stablemate.yml:11-15`, `:30`). Its description promises five commands and a `babysit-run` that fixes stablemate itself, which is the maintainer's job, not the reader's (`:2`). `grill` and `brainstorm` come from the `general` pack. No page says the reader's agent already knows how to operate the ecosystem. |

**Proof: Reshape.**

| Concept | Verdict |
|---|---|
| Measurement | Reshape. paddock defines backlog satisfaction (`paddock/data/README.md:61`), but recorded results are DIAGNOSTIC and cover 3 bullets. Not publishable (R4). |
| Compliance trial | New (R11). A paddock task: the same tasks on a public seed app, one arm with the rules in `AGENTS.md`, the other with the same rules as checks in a scaffolded workflow, scored by rules broken at the end. |
| Comparison | New. A table rendered from the measurements file. |
| Recording | Reshape. groom screenshots exist (22 under `docs/features/`, one in the README). No recording. |
| Exhibit | Exists. `docs/features/` is a feature book the toolchain wrote, and QA renders a `qa-report.md` per run. |
| Replay | Reshape (R9). `link-shortener-dev/l2-batched-impl` is a 24-minute trial on a public seed app that scored 9/12, with no gate and no cap sleep. The event log lacks cap sleeps (A9). |

**Storefront: Reshape.**

| Concept | Verdict |
|---|---|
| First screen | Reshape (R11, R28). Since `b125b2da` it carries the bash-loop table, and it shows the dashboard the install block cannot install. |
| Landing section | New. There is no site. |
| Identity | Exists. `docs/assets/stablemate-logo.png` and the stable-yard naming. The names move below the path map (invariants 4 and 9). |
| Publisher | New. Source goes in a new top-level `site/` (L5), because `docs/` is the knowledge graph ostler validates. |

**Reference: Reshape.** Ten package READMEs plus `docs/INSTALL.md` and
`workhorse/docs/AUTHORING.md` hold the content. Their links point at GitHub, and several
instructions assume a checkout (F10).

| Concept | Verdict |
|---|---|
| Guide | Reshape. "Your first run" and `AUTHORING.md` become the First win guide, rewritten around `workhorse-new` (R21). |
| Tool page | Reshape. One README per package becomes one Tool page each, opened by its role-map row. |
| Settings reference | Reshape. Config rules are prose in `docs/INSTALL.md`. |
| Agent index | New. An `llms.txt` the Publisher generates from the page list. |

**Pulse: Reshape.**

| Concept | Verdict |
|---|---|
| Release train | Reshape. Releases run on manual dispatch only. |
| Changelog | Exists. release-please writes one per package. |
| Badge | Reshape. Four per-package version badges. The visitor needs build, license and one version. |
| Status page | New (R28). No page separates what installs today from what is in progress. |
| Channel | Exists since 2026-10-02. Discussions is enabled. |
| Contributor path | Exists. `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue templates. |

**What the repo has that the design lacks.** The methodology section and "where the work
is" are Reference material. They move to a Guide page, "How a story is verified". The
Docker harness is a draft the design leaves out, with no public mention (R16). The repo's own
review gate and write guards are this repo's development setup, not the product (R12).

**Claims against the repo.** C13: the repo follows it, and the design hides it behind
the umbrella distribution (F9). C14: the repo follows it, and the design follows it by
rejecting C4. C15: the repo follows it, and invariant 6 extends it to the built site.

## 6. Slices

1. **Your rule as a workflow step.** `workhorse-new NAME --check CMD` in
   `workhorse-workflows`, its template inside that distribution, a public sample repo
   with one seeded failing test, and a First win guide. CI scaffolds a workflow and
   dry-runs it with no checkout. Touches First win, Workflow scaffold, Guide,
   Measurement, invariant 2. Done when a real `claude` run of a scaffolded workflow on
   the sample repo, with `--check "pytest"`, loops back at least once and finishes when
   the test passes. Its wall-clock time from install to green is recorded, with release
   and date, as the first Measurement. Section 1 keeps "within an hour" only if that
   time is under an hour (A3, A4, R20, R21).
2. **The first screen speaks to the right reader.** Rewrite the README's first screen:
   the Promise, a paragraph naming the Incumbent, the isolation sentence, today's
   install line for `workhorse-workflows` followed by the First win command, and one
   real gate question with its answer. The comparison and the path map open the second
   screen. A Status section lists what installs today and what is in progress, each row
   dated, and the dashboard screenshot moves there until slice 3 publishes it. Touches
   Audience, Pain, Promise, Incumbent, Objection, Tool role, First screen, Status page,
   invariants 4, 8 and 9. Done when a developer who uses an agent interactively, and has
   never seen the repo, says after the first screen what stablemate replaces and which
   command they would run first (A17, A20, A21, R28).
3. **One install, no clone.** Publish `stablemate-groom` and the `stablemate` umbrella
   distribution. On every merge, CI builds every wheel and installs them by path in a
   clean environment with no checkout. After each release, a second job installs from
   PyPI, so farrier fetches the library at its release tag. Both jobs run each Step's
   command with the agent stubbed: the scaffold and its dry run, `farrier init` and
   `farrier install` in a scratch repo, and `groom serve` answering its health check.
   Touches Install line, Step, invariants 2 and 3. Done when both jobs pass and `uv tool
   install stablemate` on a fresh machine puts every Step's command on the `PATH` (A10,
   A11, A15, A18, R22).
4. **Hand off without a clone.** workhorse writes a cap-sleep event into the run's
   event log. The public sample repo gains a docs graph and a roadmap with one open
   question that the author run must ask the reader. Touches Step, Replay. Done when, on
   a machine with no clone, an author run on that repo starts from the installed
   command, parks on the gate the roadmap seeds, takes the answer from groom, and
   continues (A7, A9, A19, R23).
5. **The site exists.** It starts when the maintainer calls the launch. Until then the
   README carries every slice's public text (R30, A22). `site/` on MkDocs Material,
   deployed to GitHub Pages on merge:
   the first screen, the path map, Agent recipe tabs, a "why" grid from the
   differentiators, and one Tool page per tool opened by its role. Public guard over the
   built site. Touches Publisher, Landing section, Agent recipe, Tool page, invariants 6
   and 7. Done when the URL loads on a phone in both themes (A16).
6. **The recording and the replay.** A capture command records the First win on a real
   agent CLI. The main public page shows a real roadmap-to-QA run, started after slice
   4, with its gates and cap sleeps. Touches Recording, Replay, Exhibit. Done when the
   main public page, the README before launch and the landing page after it, embeds both
   and every reply shown came from a real model (R30).
7. **The compliance number.** The Compliance trial runs on a public seed app and its rows
   replace the mechanism rows of the comparison, with model, release and date. Touches
   Compliance trial, Measurement, Comparison, invariants 1 and 5. Done when the table
   renders from a run on the current minor release (A2, A13, A14).
8. **Agents and the calendar.** First, the `stablemate` pack's description states
   what the pack ships. Then a page that tells the reader their agent already operates
   the ecosystem after the Standards step and how to add skills of their own, a
   generated `llms.txt`, an Exhibit page showing a real `qa-report.md`, and a scheduled
   release dispatch. Touches Agent brief, Agent index, Exhibit, Release train. Done when
   an agent given only the docs site scaffolds and runs a workflow in a fresh repo, and
   the scheduled dispatch has cut one release (R24, R26).

## 7. Assumptions

1. **Assumption:** the reader who adopts fastest works with an agent interactively and
   wants it held to a process, not only to what they asked it.
   **Decided:** the Incumbent is the same agent with a rules file. The SDLC framing
   moves to a Guide.
   **Basis:** the maintainer's words on 2026-10-02 (R11).
   **If wrong:** Audience, Pain, Promise, Incumbent; slices 2 and 7.
2. **Assumption:** a reader shown the Compliance trial agrees that the rules-file arm
   is how they work. A baseline with weak rule text costs the project its credibility.
   **Decided:** both arms use one rule text, printed in full beside the table, and the
   page invites a pull request with better wording for the rules-file arm.
   **Basis:** none. No reader has seen it.
   **If wrong:** Compliance trial, Comparison, invariant 5, slice 7.
3. **Assumption:** the First win takes under an hour: about ten minutes to scaffold and
   one to three agent turns.
   **Decided:** the promise says "within an hour of installing" until slice 1 measures
   the First win on the sample repo. That measurement then replaces the estimate (R20).
   **Basis:** median turn 8.2 minutes, 90th percentile 18.9 minutes over 607 recorded
   turns. Those were book turns on MiniMax and Codex, not a small coding task on Claude.
   **If wrong:** section 1 wording, slice 1's done-when, the Recording's speed-up.
4. **Assumption:** after the sample repo's win, the reader's own repo has a check
   command that can fail, such as a test suite or a linter.
   **Decided:** the First win runs on the public sample repo first, so it never depends
   on the reader's repo (R20). The scaffold then takes the reader's check as
   `--check CMD`.
   **Basis:** none for the reader's repo.
   **If wrong:** First win, slice 1.
5. **Assumption:** the Intent step's input, an approved roadmap, is something the reader
   can write in one interactive session with the skills the Standards step installs.
   **Decided:** the Path puts Intent after the First win and before Handoff.
   **Basis:** the `stablemate` pack's skills carry the roadmap contract, and the
   `general` pack carries `brainstorm` (`base-library/packs/general.yml:14`). No reader
   has written one from them, and nothing checks a roadmap before the planning run reads
   it (R22).
   **If wrong:** Step order, the Intent guide.
6. **Assumption:** the Handoff step's duration, hours for planning and days for coding,
   is acceptable to a reader who first met the project through a one-hour win.
   **Decided:** the Path states each Step's duration, and the Replay shows a whole run
   before the reader starts one.
   **Basis:** the maintainer: "A run can take days."
   **If wrong:** Step, Replay, first screen wording.
7. **Assumption:** a reader who hands off a multi-day run isolates it themselves, and
   accepts that the run does not ask before each tool call.
   **Decided:** the project ships no run environment (R16). The Handoff guide states that
   a run acts without asking, and leaves where it runs to the reader.
   **Basis:** the maintainer on 2026-10-02: "The user is responsible of making it." The
   claude backend passes `--dangerously-skip-permissions`
   (`workhorse/workhorse/runner/backends/claude.py:107`).
   **If wrong:** Handoff Step, slice 4, the first screen's "overnight" row.
8. **Assumption:** the reader's agent CLI subscription can carry a multi-day run, and
   the reader accepts its cost.
   **Decided:** the Handoff guide states the cost per story once the Replay's run has
   measured it. Until then it states the run's duration and turn count.
   **Basis:** none for a coding run on Claude. The book runs use MiniMax because Claude
   costs too much per run.
   **If wrong:** Handoff, Agent recipe, the first screen's "overnight" row.
9. **Assumption:** a real run on a public seed app, started after slice 4, hits a cap or
   a gate and leaves a timeline the Replay can draw. It takes at least one night and the
   maintainer's quota.
   **Decided:** the 24-minute seed trial stands in, labelled, until that run exists.
   **Basis:** `workhorse/workhorse/runner/caps.py:60-90` writes no event today.
   **If wrong:** Replay, slice 6.
10. **Assumption:** groom publishes as `stablemate-groom` with no change to its import
    name or its `groom` command, and its web assets ship in the wheel.
    **Decided:** the maintainer decided the name on 2026-10-02 (R15). Slice 3.
    **Basis:** the name returned 404 on PyPI on 2026-10-02. groom's sdist includes the
    `groom` package (`groom/pyproject.toml:68-72`). The wheel's contents are unchecked.
    **If wrong:** slice 3 gains a packaging fix.
11. **Assumption:** `uv tool install --with-executables-from` exposes the commands of
    the dependencies named, and `pipx` users accept a longer line.
    **Decided:** the Install line uses it, and the umbrella pins the set.
    **Basis:** `uv tool install --help` on uv 0.11.15 lists the flag. Untested on the
    umbrella.
    **If wrong:** the `stablemate` command dispatches to each tool, as `stablemate
    groom serve`.
12. **Assumption:** no Step needs `saddlebag` or `paddock`.
    **Decided:** both stay unpublished. Their Tool pages say they need a clone.
    **Basis:** "no base workflow requires either" (`README.md:247-250`). A coding run
    whose QA logs into an app may need credentials. That case is not on the first path.
    **If wrong:** Path gains a Step, slice 3 publishes the tool.
13. **Assumption:** the Compliance trial shows a gap large enough to print.
    **Decided:** the first screen carries mechanism rows until the trial has run.
    **Basis:** none. No trial has run.
    **If wrong:** the mechanism rows stay, and the number goes to a Guide.
14. **Assumption:** the Compliance trial runs on a model the maintainer can afford.
    **Decided:** the row names its model.
    **Basis:** e2e runs use MiniMax for cost.
    **If wrong:** Compliance trial, slice 7.
15. **Assumption:** the maintainer registers `stablemate` and `stablemate-groom` on PyPI
    with trusted publishing, and enables GitHub Pages. These are account settings outside
    this repo.
    **Decided:** slices 3 and 5 list them as maintainer steps.
    **Basis:** both PyPI names were free on 2026-10-02.
    **If wrong:** Install line, Publisher.
16. **Assumption:** GitHub Pages at the default URL is good enough for launch.
    **Decided:** no custom domain in scope.
    **Basis:** `stablemate.dev` answers HTTP 200 and its owner is unknown.
    **If wrong:** Publisher config only.
17. **Assumption:** someone who uses an agent interactively and has never seen the repo
    is available to read the first screen.
    **Decided:** slice 2 stays unverified until one such reader has answered.
    **Basis:** none.
    **If wrong:** slice 2's done-when only.
18. **Assumption:** the reader has git and the network when they first install the
    standards.
    **Decided:** the Standards step names both. farrier fetches the library at its own
    release tag with a sparse git clone, and a farrier installed from a checkout or a
    URL tracks `main` (R18).
    **Basis:** the reader keeps their repo in git and runs an agent CLI that calls a
    hosted model. A live fetch at `farrier-v3.0.0` worked on 2026-10-02.
    **If wrong:** farrier downloads the tag's source archive over HTTPS instead of
    cloning. Standards Step, invariant 2.
19. **Assumption:** a roadmap can be written so the author run parks on one known gate
    every time.
    **Decided:** slice 4 seeds that roadmap in the public sample repo and names the gate
    in its done-when (R23).
    **Basis:** none. Gates fire only where a flow raises one
    (`workhorse/workhorse/pyflow/transitions.py:123`).
    **If wrong:** slice 4 uses a coder run whose review gate fires
    (`workflows/src/workhorse_workflows/coder/review/flow.py:149-228`). Step in, Replay.
20. **Assumption:** a real run on a public repo has asked a gate question that the
    first screen can quote, with the answer that let it continue.
    **Decided:** slice 2 quotes one. Until a public run has parked on a gate, the slot
    shows the comparison table instead, and slice 4's run supplies the question (R28).
    **Basis:** the dashboard screenshot in the README shows a coder run asking for a
    storage backend. Whether a real public run asked it is unchecked.
    **If wrong:** First screen, slice 2's done-when.
21. **Assumption:** a reader takes "stablemate tests, reviews and QAs the work" to mean
    checks the workflow runs around the work, not a promise that the agent follows their
    `CLAUDE.md`.
    **Decided:** the line names three checks and no standard. The second screen's
    comparison shows what each check does (R28, R29).
    **Basis:** none. No reader has seen it.
    **If wrong:** Promise, slice 2.
22. **Assumption:** the launch comes when the maintainer's own development is mostly
    done by stablemate runs rather than by live Claude sessions.
    **Decided:** slice 5 waits for that point. Slices 1 to 4 land their public text in
    the README (R30). The launch claim is the maintainer's own use, so the site opens on
    the project built by its own workflows.
    **Basis:** the maintainer on 2026-10-02: ready to launch means "when my developer
    work will mostly be done by stablemate rather than by live claude session". A run
    leaves no mark on the commits it makes today, so the share cannot be read from git
    yet.
    **If wrong:** slice 5's start, section 1's site line.
    **Open:** counting the share needs a run to mark the commits it makes, for example
    with a trailer. Until then the maintainer judges it.
