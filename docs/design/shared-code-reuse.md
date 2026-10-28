# Agents find, spot and share the code they would otherwise copy

**Disclosure.** I read the existing solution before this note was written. That covers the
coder workflow's plan, scope, review and reviewer prompts, its gate loop, its decline check
and its plan schema, the code-structure skill and its module rules, the skill hook
mechanism farrier renders, and the base-library cache in core. I also read a reference
client repository: a multi-service monorepo where one service imports a package from
another. I ran jscpd 4.0.5 and then jscpd 5.4.1 on that repository, and probed jscpd 5 on a
scratch clone of it. The design decisions that reached me through that reading are claims
in section 1b. Section 4 re-derives or rejects each one.

## 1. Problem

**Who feels this.** An operator whose codebase is written and maintained by agents. The
agents copy a helper that already exists instead of calling it. They work around a shared
package rather than change it. When they do change it, they break a caller in another
service that nobody checked. This happens in the coder workflow and in interactive
sessions alike. The codebase grows two or three copies of each decision, and each later
fix lands in one copy only.

The operator cannot hand the agent a map of what is shared. The codebase is too large for
one context, and agents rewrite it faster than anyone could keep a map current. The agent
has to find shared code by searching, spot a copy it just made, and turn two copies into
one owner by itself.

The reference repository shows the cost. Its reporting service carries whole files copied
from its API service: a 166-line spreadsheet generator and a 106-line error catalogue, each
present twice. Its hand-written production code holds 398 duplicated fragment pairs. 39 of
them cross a service boundary. In 72 pairs, a story commit wrote the later copy of code
that already existed.

**Done looks like this.** Every item holds in an interactive session and in the coder
workflow alike.

- An agent about to add a named function, type or constant searches the tree first. Its
  plan or its reply says what it found: reuse, extend, or new.
- A commit that adds a fragment duplicating code elsewhere in the tree is refused. The
  refusal names both places by file, lines and enclosing function. The threshold is the
  one the repo configures, by default 50 tokens and 5 lines.
- The second copy is extracted in the same change. A third copy of a fragment that already
  has two is refused the same way. The only other exit is a stated coincidence: two
  reasons the copies will change apart.
- A change to a shared directory runs the checks of every service that imports it, not only
  the services the plan named.
- Copies that predate the change are never blamed on it. A change that adds no copy passes
  on a repository that holds hundreds, including a change that edits one of them.
- The check needs no Node and nothing the operator installs by hand.

**Out of scope.**

- Removing the duplication a repository already has. The search may surface it, and the
  coder files it as debt, but this design does not sweep it.
- A rewrite: the same behaviour written in different words. A token comparison cannot see
  it. The search rule is the only guard, and the reviewer's judgement backs it (A1).
- Functions with the same shape that encode different rules, such as one error mapper per
  domain. A shape comparison reports them, but most are not copies (A2).
- A copy with renamed identifiers. The gate matches tokens verbatim (A1).
- A cross-repository shared library, and a copy between two repositories of one workspace.
  Reach and the comparison both stop at the repository's edge (A6).
- Generated code, vendored code, mocks, fixtures, migrations and tests. The default
  ignore list and the generated-file markers exclude them, and a repo may opt its tests
  back in (A4, A7).

## 1b. Claims

1. "Extract on the second copy." Source: the operator, in this conversation.
2. "jscpd scoped to the diff." Source: the operator.
3. "Checks derived from the diff." Source: the operator.
4. The agent must find shared code by searching, with nothing preloaded into its context.
   Source: the operator.
5. A pre-commit check ships as a skill's `hooks:` entry, rendered by farrier. Source: the
   ostler-cli skill and farrier's hook collection.
6. An extraction is a follow-up, filed on the debt register with a pattern such as
   `extract-module`. Source: the coder's scope prompt.
7. A decline that calls a finding an improvement needs no evidence. Source: the coder's
   decline check, which inspects only "not a defect" declines.
8. Gates run for the services the plan names, and a directory no service names is not a
   service. Source: the coder's plan prompt and its dispatch list.
9. The reviewer judges only lines the change touched. Source: the coder's reviewer prompt.
10. jscpd ships upstream as is, fetched into the stablemate cache, behind one adapter, with
    token windows as the gate and each window snapped to its enclosing function. Source:
    the operator, after the jscpd 5 measurements.

## 2. Parts and concepts

### Level 1: parts

1. **Finding what exists.** Before an agent writes a new named piece, it looks for one that
   already does the job. Owns the search and the decision it backs. Never knows how copies
   are detected after the fact. Hands its decision to the change's plan or reply, where
   Holding the line reads it.
2. **Spotting copies.** Compares what a change added against the rest of the tree, and
   reports each fragment that repeats code elsewhere. Owns the comparison. Never knows
   what the agent intended or whether a copy is justified. Hands copy pairs to Holding the
   line.
3. **Sharing.** Turns two copies into one owner that both callers use. Owns where the shared
   piece lives and the move. Never knows how the copy was found. Hands the edited
   directories to Reach.
4. **Reach.** Finds everything that depends on the shared pieces a change edited, and runs
   their checks. Owns the dependent set. Never knows why the piece changed. Hands check
   results to Holding the line.
5. **Holding the line.** Rules on each copy pair and each failed dependent check: accepted,
   refused with a repair, or accepted on a stated coincidence. Owns the verdict. Never
   knows how a pair was detected or how a check runs.

**Flow.**

- While writing, the agent consults Finding what exists before adding a name.
- At commit, Spotting copies compares the working tree with HEAD and keeps the new pairs
  inside the staged files' added lines. Holding the line refuses the commit when a pair
  has no coincidence.
- In the coder's checking lap, Spotting copies compares the working tree with the story's
  base and keeps the new pairs inside the story's added lines. Reach runs the dependents'
  checks. Holding the line turns either failure into a finding the owner repairs.
- At review, Holding the line reads each Reuse finding's answer. A decline passes only as a
  coincidence.
- On a refusal, the agent uses Sharing, and the next commit or lap starts over.

In one paragraph: before writing something new, the agent looks for it. After writing, a
tool compares the new lines with everything else and points at any copy, naming the
function each side sits in. The agent then moves the logic to one place both sides use.
Changing that shared place re-checks everyone who uses it. A copy stays only when the agent
says why the two will change for different reasons. The same check runs when a person's
agent commits and when the coder finishes a lap.

### Level 2: concepts

**Finding what exists**

| Concept | Owns | Never knows |
|---|---|---|
| Intent | the behaviour about to be written, stated in the domain's words | where any code lives |
| Search | the queries run over the tree: by name, by behaviour word, by signature shape | the decision drawn from the hits |
| Reuse decision | one of reuse, extend or new, with the search that backs it | how a copy is detected later |

**Spotting copies**

| Concept | Owns | Never knows |
|---|---|---|
| Change span | the lines this change added, per file, read from the working tree | which tool compares them |
| Base ref | the commit a moment measures against: HEAD at commit, the story's base in the lap | the lines inside the span |
| Detector | the pinned comparison program on this machine, fetched once and verified | what a reported pair means |
| Clone report | every duplicated pair over the whole tree, each marked new or old against the base ref | the change span |
| Copy pair | one reported pair marked new, with the change span holding at least the minimum lines of one side | whether the copy is justified |
| Enclosing unit | the named function or type around each side of a copy pair | whether the pair counts |
| Clone threshold | the minimum size, the ignored paths and the generated-file markers that make a fragment count | the change span |

**Sharing**

| Concept | Owns | Never knows |
|---|---|---|
| Owner | the one place the shared logic lives, chosen by the placement rules | which callers found it |
| Extraction | the move that puts one copy in the owner and points both callers at it | how the copy was spotted |

**Reach**

| Concept | Owns | Never knows |
|---|---|---|
| Edited unit | a directory the change edited | why it changed |
| Unit identity | the names a caller imports a unit by: its path forms and its manifest's package name | who imports it |
| Dependent | a service whose sources import an edited unit's identity | the check commands |
| Check set | the union of the plan's services, the services owning edited files, and every dependent | how a check runs |

**Holding the line**

| Concept | Owns | Never knows |
|---|---|---|
| Coincidence claim | two named, different reasons the copies change apart | how the pair was found |
| Copy verdict | accepted, refused, or accepted on a coincidence claim, per copy pair | how Sharing repairs a refusal |
| Refusal | the finding sent back: both locations, their enclosing units and the repair | the next lap's outcome |

**Shared value types.** A copy pair crosses from Spotting copies to Holding the line. It is
a value type: two file and line ranges, the enclosing unit of each side, and the line
count. A check result crosses from Reach to Holding the line. It is the existing gate
outcome.

## 3. Invariants

1. **No uncovered copy.** A change is accepted only when every copy pair is extracted or
   covered by a coincidence claim. Owner: Copy verdict. Upheld by Change span, Clone
   report and Extraction.
2. **Old copies are not the change's fault.** A pair is a copy pair only when the detector
   marks it new against the base ref and the change span holds at least the threshold's
   minimum lines of one side (revised, log 15). Either condition alone blames old code. An
   edit inside an old copy shifts its fragment, and the detector then marks the shifted pair
   new. Owner: Copy pair, which applies both. Upheld by Base ref, Change span and Clone
   threshold.
3. **Every dependent is checked.** A change that edits a unit runs the checks of each
   service in its check set before acceptance. Owner: Check set. Upheld by Dependent and
   Unit identity.
4. **A coincidence names two reasons.** A coincidence claim that names one reason, or the
   same reason twice, is refused. Owner: Coincidence claim.
5. **One rule at both moments.** The commit check and the coder's lap check run the same
   script, with the same detector version, threshold, ignore list and markers. Only the
   base ref differs. Owner: Clone threshold, read from one place in the repo. Upheld by
   Detector, which refuses a binary whose hash differs from its pin.
6. **A new name carries its search.** Each new exported name in a coder plan carries a reuse
   decision and the queries behind it. Owner: Reuse decision, checked by the reviewer's
   Reuse lens. This one has no mechanical check. Invariants 1 and 3 are the mechanical
   backstop for what it misses.
7. **No detector, no pass.** When the detector cannot be found or fetched, the check fails
   with a message naming what is missing and where it was looked for. It never passes
   silently. Owner: Detector.

## 4. Forces and patterns

### Forces

- **F1. Languages vary.** Target repos mix Go, TypeScript, Dart and Python, sometimes in one
  repo.
- **F2. Old duplication is everywhere.** A repo adopting the check already carries many
  copies. Reporting them would make every commit fail.
- **F3. Two moments, one rule.** The commit moment and the coder's lap must agree, or the
  coder passes what an interactive commit refuses.
- **F4. The coder's own commits skip hooks.** A commit-time check never sees coder work.
- **F5. The comparison tool is an external program.** A test must run the filter and the
  verdict without it.
- **F6. Commit latency is a budget.** An operator commits many times an hour. The check's
  cost lands on each commit.
- **F7. Callers cross service lines by package name.** A service imports another's package
  through a module path or a workspace package name, not through a path the plan lists.
- **F8. The codebase outgrows any context.** Nothing about what is shared can be loaded up
  front. It must be found when needed.
- **F9. Some copies are right.** Two services can encode the same rule today for reasons
  that diverge tomorrow, such as a public API's wire format and an internal one.
- **F10. The detector changes weekly.** jscpd shipped 24 releases between June and October
  2026. Its output has quirks that a release can move: file names relative to the scanned
  path, an end line that disagrees with the reported length, and a scan of `.git/` unless
  told otherwise.
- **F11. The detector is a native binary per platform.** One build is 46 MB. Eight
  platforms are published. Neither the operator's machine nor the coder's container
  carries it.
- **F12. Generated code sits beside hand-written code under no path convention.** Its
  copies are the generator's, and no agent can extract them.
- **F13. A window's edges follow a token count, not the code's structure.** An agent told
  "lines 40 to 52" has to read both files to learn what repeats.

### Patterns between parts

- **One value handed along (F3, F5).** Spotting copies produces copy pairs as plain values.
  The commit moment and the lap moment both pass them to Holding the line. A test feeds a
  recorded clone report to the filter.
- **Two moments, one entry point (F3, F4).** One program with two plain arguments: the base
  ref and the span source. At commit they are HEAD and the staged files. In the lap they
  are the story's base and the story's range. Nothing else varies, so they get no role.

### Patterns inside parts

- **Search** is a procedure in the agent's instructions (F8). Its queries run on the tools
  the agent already has. No index is built.
- **Detector and Clone report sit behind one adapter (F5, F10).** One module is the only
  code that knows jscpd's flags, its JSON shape and its quirks. It hands back clone report
  values. Tests feed it reports recorded from the pinned version. An upgrade is a change
  to the pin and to those recordings, made on purpose. There is one detector, so the
  adapter is a boundary, not a role.
- **The Detector is fetched once into the shared cache (F11).** The adapter downloads the
  pinned platform package from the npm registry, checks its sha512 integrity against a
  table, and unpacks the binary under the stablemate cache. No Node runs. Rejected: `npx`,
  which makes Node mandatory to launch a native binary. Rejected: bundling, which turns
  each Python package into eight platform wheels of about 46 MB.
- **Clone report** scans the whole tree with a token comparison and marks each pair new or
  old against the base ref (F1, F2, F6). A native scan with the baseline costs 2.1 to
  2.6 s on the reference repo, so the tree needs no narrowing.
- **Copy pair** is a pure filter: report plus span in, pairs out (F2, F5).
- **Enclosing unit** reads each side's file upward from the window for the nearest
  definition line, from one pattern per language (F1, F13). A language with no pattern
  keeps the raw line range. The unit names what the refusal says. It never changes a
  verdict.
- **Clone threshold** is a table in the repo's existing check config (F3): size, ignored
  paths, generated-file markers. A marker is text in a file's first lines, such as
  "Code generated" or "DO NOT EDIT" (F12).
- **Dependent** is a text search over sources for each identity form (F7). A real import
  graph per language answers the same force at four times the cost, and F1 makes it four.
- **Coincidence claim** is a fixed reason prefix plus a shape check for two reasons (F9).
- **Copy verdict**, **Owner**, **Extraction**, **Check set** and **Refusal** have no
  variation. They are plain functions or instructions.

No concept here has interchangeable variants, so the design names no role.

**Rejected: a function-level unit as the gate.** Comparing whole functions by syntax tree
finds pairs the token scan misses, but most of them are F9's case: same shape, different
rule. It also misses the commonest copy, a repeated block inside two different functions.
The token window stays the trigger, and Enclosing unit gives it the function's name (A2).

### SOLID check

- Single responsibility: every Owns above reads without "and".
- Open/closed: a new language needs no change to the comparison, which is language-blind.
  It adds one row to Enclosing unit's pattern table. A new manifest kind adds one row to
  Unit identity's table.
- Liskov, interface segregation, dependency inversion: no roles, so nothing to check.

### Claims

- Claim 1, extract on the second copy: re-derived from F9 and invariant 1. Waiting for a
  third copy lets two copies drift first. F9 is the exit, not a count.
- Claim 2, jscpd scoped to the diff: re-derived. F1 picks a token comparison. F2 scopes it
  to the base ref and the span. jscpd is the instance (A1, A11).
- Claim 3, checks derived from the diff: re-derived from F7 and invariant 3.
- Claim 4, search instead of a map: re-derived from F8.
- Claim 5, skill hooks: re-derived from F3. The rule lives with the skill that states it.
- Claim 6, extraction as a follow-up: **rejected** for a copy the change introduced, by
  invariant 1. Kept for copies the search finds that predate the change, which are out of
  scope.
- Claim 7, improvement declines need no evidence: **rejected** for Reuse findings, by
  invariant 4.
- Claim 8, gates from plan services only: **rejected** by F7 and invariant 3. The plan's
  services stay in the check set as one of three sources.
- Claim 9, reviewer sees only touched lines: kept for what it reports. Its Reuse lens
  searches the whole tree for the existing helper, by F8.
- Claim 10, jscpd as is behind one adapter, token windows snapped to functions:
  re-derived. F10 gives the adapter, F11 the fetch, F13 the snap.

### Open lookups

1. Does the coder have a place to run a check that is not a service gate, and route its
   failure as a finding? Decides where invariants 1 and 3 run in the lap.
2. Is the finding's category available where declines are checked? Decides invariant 4's
   home.
3. Can the coder reach the code-structure skill's files when the repo did not select that
   skill? Decides whether the lap check depends on the repo's skill selection.
4. What does the comparison cost on a real multi-service repo, and how many copies do
   stories introduce today? Decides the threshold default and the latency budget (F6).
5. How does a hook script, run by the system `python3`, find the stablemate cache? Decides
   where the Detector lives on disk.
6. What does the detector mark new after an edit inside an old copy, and after a third
   copy of an old pair? Decides invariant 2's filter.

## 5. Mapping onto the existing system

### Revision log

1. Section 2, Reach: added **Unit identity**. A grep for the repo-relative path misses a
   TypeScript workspace import by package name, and a Go import names the module path, not
   the repo path. Finding: the reference repo's reporting service requires the API
   service's Go module by module path.
2. Section 4, F4: added. Finding: the workflow commits with hooks off
   (`workflows/src/workhorse_workflows/coder/shared/story_commit.py:75`, `:295`, `:347`,
   through `kit/git.py:135`). Without F4 the design had the commit moment cover the coder.
3. Section 4, open lookup 3 resolved to the base-library cache, not the repo's rendered
   skill. Finding: the reference repo selects no code-structure skill. A hook declared by
   that skill never renders there.
4. Section 2, Clone report, and section 4, its pattern: the scan covered only the
   languages the span touches. Finding: with jscpd 4.0.5, a whole-tree scan of the
   reference repo took 37.0 s with tests and mocks, and 11.3 s without. **Revised by 7.**
5. Section 1, out of scope: tests, mocks and generated files leave the default scan.
   Finding: with jscpd 4.0.5, 7 of the 10 largest pairs were test setup or generated
   mocks. **Revised by 11.**
6. Section 1, out of scope, and assumption 1: renamed copies are out of reach. Finding:
   jscpd 4.0.5 reports exact clones only. **Revised by 12.**
7. Section 2, Clone report, and section 4, its pattern: the scan covers the whole tree
   again. Finding: jscpd 5.4.1 is a native binary. With `--baseline-from-ref`, it scans
   the reference repo in 2.1 to 2.6 s.
8. Section 2, Spotting copies: added **Base ref**. Copy pair now needs a new mark and a
   side in the span, and invariant 2 states both. Finding: on a scratch clone, one added
   line inside one member of a 16-copy family made jscpd regroup the family. It marked 17
   old pairs new, and none of them touched the edited lines. A third copy of the same
   family was marked new, and so was a fresh copy of an unduplicated function into
   another service.
9. Section 2, Spotting copies: added **Detector**. Section 3: added invariant 7. Section 4:
   added F11 and the fetch pattern. Finding: one platform binary is 46 MB and runs with no
   Node. The fetch lives in the check script, not in core, because the hook runs on the
   system `python3`, where core is not importable. Core keeps owning the cache directory.
   Open lookup 5 resolved.
10. Section 2, Spotting copies: added **Enclosing unit**. Section 4: added F13. Finding: of
    184 hand-written Go pairs in the reference repo, 85% sit inside one function and 12%
    straddle the end of one function and the start of the next. jscpd reports line
    numbers and no unit.
11. Section 2, Clone threshold: added generated-file markers. Section 4: added F12. Section
    1, out of scope: fixtures and migrations join the ignore list. Finding: 128 of 636
    pairs have a side in a Go file headed "Code generated ... DO NOT EDIT", from sqlc and
    the OpenAPI generator, and no path rule matched them. Database fixtures, migrations and
    HTML fixtures held 114 more. 398 hand-written production pairs remain.
12. Section 1, out of scope: same-shape functions added. Section 4: function-level gate
    rejected. Finding: jscpd 5's syntax-tree mode found 61 hand-written function pairs the
    token scan misses, in 1.3 s. Its typical match is a per-domain error mapper. Two
    mappers share a switch shape and two branches, and score up to 1.0 while mapping
    different errors. jscpd 5 can match renamed copies with `--ignore-identifiers`, which
    was not measured, so renamed copies stay out of scope.
13. Section 4: added F10 and the adapter pattern. Finding: jscpd 5 names files relative to
    the scanned path, reports Markdown code blocks as `file.md:lang`, scans `.git/`
    unless ignored, and its `secondFile.end` disagreed with `lines` in 203 of 2,703 pairs.
14. Section 5, Holding the line: a coincidence claim at commit is an entry in the repo's check
    config. Finding while building slice 1: an interactive commit has no plan and no review
    answer to carry the claim. The design named a carrier only for the coder.
15. Section 3, invariant 2: a side counts as added only when the change span holds at
    least `min-lines` of it, not when it overlaps by one line. Finding while verifying
    slice 1: replacing a function body with a call, in a file that already held an old copy
    of a sibling file, shifted the old 46-line and 85-line pairs. jscpd marked the shifted
    pairs new, and the one changed line overlapped them, so the commit that removed a copy
    was refused.
16. Section 5, coincidence claim in the lap and base ref: the finding's category reaches
    the settle step from the flow, and the story base has a rule for a story run on trunk.
    Finding while planning slice 2: the answer ledger carries the disposition and the reason
    but not the category. The worklist item that filed the finding carries it. A story run
    on trunk has no merge base that separates its commits from trunk's.
17. Section 5, clone report, and assumption 4: lockfiles join the always-ignored paths.
    Finding while verifying slice 2: range mode on a reference commit that added a web
    service reported 9 pairs, all between two `package-lock.json` files. A lockfile
    carries no generated-file marker, and a repo that overrides `ignore` must not lose it.
18. Section 5, Unit identity and Dependent: a relative import is matched by resolving it,
    not by a substring of the repo path. Finding while planning slice 3: a relative import
    climbs only to the common ancestor, so `../shared/auth` never holds the unit's full
    repo path. The substring `/api/handlers` also matches a frontend's URL
    `"/api/handlers"`, which would gate the frontend on every private backend edit.
19. Section 5, Unit identity: a quoted repo path or `package.json` name counts only after
    an import keyword. Finding while verifying slice 3: on the reference stories, the
    infrastructure service held the web package's name as a cloud account id. It was
    gated on 11 of 17 stories, and none of them touched its code.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Finding what exists | Reshape | code-structure has no rule that fires before writing. The coder's plan step reads "the callers, the seams and the tests of each unit the story changes" and runs no reuse search (`coder/dev/prompts/dev-plan.md`, step 3). |
| Spotting copies | New | A script in the code-structure skill, declared as its pre-commit hook. |
| Sharing | Reshape | Rule 2.7 in `references/modules.md:123` gives a decoding one owner, but fires on a constant or a decoding only. The coder's scope prompt files extractions as follow-ups (`coder/dev/prompts/_dev-scope.md:16`). |
| Reach | Reshape | The lap gates only `impl.dispatch_list` (`coder/dev/flow.py:466`), built from the plan's services (`coder/shared/plan.py:284`). |
| Holding the line | Reshape | `decline_gap` returns "" for every reason that does not open with "not a defect" (`coder/shared/review.py:99`). |

### Concepts

**Finding what exists**

- Intent, Search, Reuse decision: **New** as a rule in code-structure,
  `references/modules.md` 2.11 "Search before you add a name", with its row in the trigger
  table of `SKILL.md`. Trigger: a diff adds an exported name. Fix: search by name, by
  behaviour word and by signature, then reuse, extend or add. Counter-case: the search
  ran and found nothing, and the reply or plan says what it searched.
- In the coder: **Reshape** `dev-plan.md` step 3 to run that search. Each line under
  Changes that adds a name records reuse, extend or new, and the query.

**Spotting copies**

- Home: `base-library/library/skills/architecture/code-structure/scripts/check_clones.py`,
  declared in that skill's frontmatter as `hooks: - stage: pre-commit`. Precedent:
  `base-library/library/skills/ostler/ostler-cli/SKILL.md` and its
  `scripts/check_staged_files.py`. The script uses the standard library only, because
  farrier's runner starts it with the system `python3`
  (`farrier/farrier/hook_managers.py:148`).
- Change span: **New**. Commit mode reads `git diff -U0 HEAD -- <staged files>`. Range mode
  reads `git diff -U0 <story base>`. Both parse the `@@` hunk headers into added line
  ranges. Both read the working tree, which is what the detector scans (A12).
- Base ref: **New**, a plain argument (revised, log 16). HEAD in commit mode, the story's base in
  range mode. On a branch the story base is the merge base with trunk. On trunk it is the
  parent of the story's earliest commit, or HEAD before the story's first commit
  (`coder/shared/okf.py`, `story_base`).
- Detector: **New**, inside the script. A table maps each of jscpd 5.4.1's eight platform
  packages to its registry tarball and its sha512 integrity. On first use the script
  downloads the package for this platform, verifies it, and unpacks the binary to
  `$STABLEMATE_CACHE_DIR/tools/jscpd/5.4.1/jscpd`. A missing variable, a failed download
  or a hash mismatch exits non-zero with the path and the URL (invariant 7).
- `$STABLEMATE_CACHE_DIR` at commit: **Reshape** of farrier's `runner_text`
  (`farrier/farrier/hook_managers.py:148`). The rendered runner exports the variable,
  defaulting to core's `cache_root()` (`core/stablemate_core/base_cache.py:29`) as
  resolved at install. An operator's own override still wins.
- `$STABLEMATE_CACHE_DIR` in the lap: the workflow sets it from `cache_root()`, which it
  reaches through `workhorse._vendor.stablemate_core`.
- Clone report: **New** (revised, log 7). One adapter function runs
  `jscpd . --baseline-from-ref <base> -r json -o <tmp> --min-tokens --min-lines --ignore`
  from the repository root, so file names are repo-relative. It always adds
  `.git/**,.agents/**,.claude/**,.github/**`, `**/*.md` and the package managers' lockfiles
  to the ignore list (revised, log 17). It reads
  `duplicates[]`: `firstFile` and `secondFile` with `name` and `start`, plus `lines`,
  `isNew` and `format`. Both sides span `start` to `start + lines - 1`, never
  `secondFile.end`. It drops a pair whose side lies in a file carrying a generated-file
  marker in its first 10 lines.
- Copy pair: **New**, a pure function over the report and the span (revised, log 8).
- Enclosing unit: **New**. One definition-line pattern per language, read upward from the
  window's first line: `^func ` in Go, `def ` and `class ` in Python, `function`, `class`
  and `const <name> = (` in TypeScript, a return type followed by a name and `(` in Dart. A
  window that straddles two units names both.
- Clone threshold: **New**, table `check-clones` in `.agent-checks.toml`. The ostler-cli
  skill's staged-files check already reads its table from that file. Keys: `min-tokens`,
  `min-lines`, `ignore`, `generated-markers`. The default `ignore` covers dependency and
  build directories, `mocks/`, `fixtures/`, `testdata/`, `migrations/`, and the test file
  patterns of each language. The default markers are "Code generated", "DO NOT EDIT",
  "DO NOT MODIFY" and "@generated".

**Sharing**

- Owner: **Exists**. Rules 2.5 to 2.9 already decide where shared code lives and what it
  may import.
- Extraction: **New** as rule 2.12 "The second copy is the extraction". Trigger: the clone
  check reports a pair. Fix: move one copy to the owner 2.5 to 2.9 pick, and point both
  callers at it. Counter-case: a coincidence claim. It generalizes 2.7 from decodings and
  constants to any fragment.
- In the coder: **Reshape** `_dev-scope.md`. Extracting a copy this change introduced is
  in scope. A follow-up with `extract-module` stays for copies the search found that
  predate the change.

**Reach**

- Edited unit: **New**. The directories of files changed between the story base and HEAD.
- Unit identity: **New**. The repo-relative path as a quoted string after `from`, `import`,
  `require(` or `import(`, and in Python dot form, plus the package name from the nearest
  manifest: `go.mod` module quoted, `package.json` name after the same keywords,
  `pubspec.yaml` name, `pyproject.toml` project name (revised, logs 18 and 19).
- Relative import: **New**, a second way to find a Dependent. A quoted `./` or `../` path
  in a service's source, resolved against its file, that lands inside the unit (log 18).
- Dependent: **New**. `git grep -l -F` each identity across the declared services'
  sources, mapped back to the service that owns each hit.
- Check set: **Reshape** of `resolve_impl_context` (`coder/shared/plan.py:284`). The
  dispatch list becomes the union of three sources. The plan prompt's rule "A directory
  that no `services:` entry names is not a service" (`dev-plan.md:61`) stays. A shared
  directory has no gate of its own. Its dependents' gates check it.
- `shared_packages` on the plan (`coder/shared/schemas/dev.py:91`): **Reshape**. Today the
  plan declares it. It becomes the edited units outside any service, derived from the
  diff, so QA sees the real list.

**Holding the line**

- Copy verdict and Refusal in the lap: **New** check in `_first_failure`
  (`coder/dev/flow.py:436`), after the story status check and before the service gates. It
  runs the script in range mode once per repository the dispatch list names, and routes
  pairs through `from_findings`, the route the story status check already uses. Open
  lookup 1 resolved.
- The script's location in the lap: core's base-library cache, which the workflows reach
  through `workhorse._vendor.stablemate_core`
  (`workflows/src/workhorse_workflows/kit/paths.py`). The lap check therefore runs
  whether or not the repo selects code-structure. Open lookup 3 resolved.
- A detector failure in the lap stops the run with the script's message. It is not a
  finding, because no repair by the owner fixes it.
- Coincidence claim at commit: **New** (log 14). A `[[check-clones.coincidence]]` entry in
  `.agent-checks.toml` names both files by glob and lists two reasons. The script drops a pair
  whose two files one entry covers. It fails on an entry with fewer than two distinct reasons,
  whether or not a pair uses it (invariant 4). The entry is tracked, so a reviewer sees each
  claim.
- Coincidence claim in the lap: **Reshape** `decline_gap`. A decline of a finding whose category is
  `Reuse` must open with "coincidence:" and name two reasons (revised, log 16). The worklist
  item that filed the finding carries the category (`coder/shared/work.py:230`). The flow
  passes the open Reuse ids to the settle step, which picks the check per id. Open lookup 2
  resolved.
- The reviewer's Reuse lens (`dev-reviewer.md:24`): **Reshape**. It searches the tree for
  the helper the diff repeats. It still reports only lines the diff touched
  (`dev-reviewer.md:15`).

Open lookup 4 resolved by logs 7 and 11. Open lookup 6 resolved by log 8.

### What the existing system has that the design lacks

- The debt register's `extract-module` pattern. Not waste. It is the home for copies that
  predate the change, which section 1 puts out of scope. Kept.
- Declared `shared_packages` in the plan. Waste as a declaration, kept as a carrier the diff
  fills.
- The plan's `implementation_order`. Unrelated to this problem. Untouched.
- Core's base-library fetch, which clones with git. Not reused for the Detector. The
  detector is a registry tarball, and the hook cannot import core.

### Claims against the existing system

| Claim | Existing system | Design |
|---|---|---|
| 1 | Does not follow. Extraction is deferred. | Follows. |
| 2 | No clone detection. | Follows. |
| 3 | Gates from plan services. | Follows. |
| 4 | Follows: no map exists. | Follows. |
| 5 | Follows for ostler-cli. | Follows for the interactive moment only. The lap reads the cache. |
| 6 | Follows. | Rejects for introduced copies. |
| 7 | Follows. | Rejects for Reuse. |
| 8 | Follows. | Rejects. |
| 9 | Follows. | Keeps for reporting, widens the search. |
| 10 | No detector. | Follows. |

## 5b. What must not move

Inputs: the reference client repository at its current main, and the stories its coder
runs completed in the last month.

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Operator committing interactively | a commit returns quickly | nothing | no clone check. The scan with its baseline costs 2.1 to 2.6 s | the check adds at most 4 s to a commit. The first commit after install also pays one download (A3) |
| Operator committing a change with no copy | the commit passes | nothing | passes, 0 pairs reported | passes, 0 pairs reported, with the 398 old pairs still in the tree, including after an edit inside an old copy |
| Coder owner in a checking lap | gates for the plan's services only | the lap loop | services gated per lap unmeasured (A17) | at most one more service per lap on a story that edits no shared unit |
| Operator paying for a story | median 9.8 hours and 6 to 9 laps per story | nothing | 9.8 h median, 6 to 9 laps | median laps rise by at most 1 (A8) |
| Reviewer's findings | Bug, Standard and Reuse findings scored 80 or above | the reviewer prompt | Reuse findings per story unmeasured (A14) | Reuse findings that an owner declines as improvement: 0 |
| A public contributor with no check config | commits without any hook and without downloading anything | farrier renders hooks only from selected skills | no clone hook, no download | still neither unless code-structure is selected |

Row two is kept on purpose. It is invariant 2. Row four is enforced by nothing and stays
that way. Section 1 accepts that extraction can cost a lap, because a copy left in place
costs every later fix that lands in one copy only.

## 6. Slices

**Slice 1. An interactive commit refuses a copy.** Parts: Spotting copies, Holding the line
at commit, Finding what exists and Sharing as rules.

- The script exists with commit mode, the adapter, the detector fetch, the Enclosing unit
  table, its config table and its frontmatter declaration.
- Farrier's runner exports `STABLEMATE_CACHE_DIR`.
- Rules 2.11 and 2.12 exist with their trigger rows.
- Done when, on a scratch clone of the reference repo with code-structure selected and
  rendered:
  - A commit that copies a 37-line function from the API service into the reporting
    service is refused. The message names both files, both line ranges, both enclosing
    functions and rule 2.12.
  - A commit that adds a third copy of an existing 8-line block is refused.
  - The same commits after extraction pass.
  - A commit with no copy passes and reports 0 pairs against the 398 old pairs. So does a
    commit that adds a line inside one member of an old copy family.
  - With no network and an empty cache, a commit is refused with the cache path and the
    download URL.
  - Hook time is re-measured on the commits above, against 2.1 to 2.6 s for the scan
    alone.
  - The script's tests feed reports recorded from jscpd 5.4.1 and need no binary.

**Slice 2. The coder repairs a copy it introduced.** Parts: Holding the line in the lap and
at review, Finding what exists in the plan, Sharing in scope.

- The range-mode check runs in `_first_failure`.
- `decline_gap` checks Reuse declines.
- The scope, plan and reviewer prompts change.
- Done when:
  - Replaying a story whose commit wrote the later side of one of the 72 pairs, the lap
    check files a finding naming both sides and their functions.
  - The owner extracts the copy within one lap, and the story finishes.
  - A Reuse decline reading "improvement" is refused with the coincidence instruction.
  - A detector that cannot be fetched stops the run with the script's message.
  - Laps on that story are compared with its original run, against the 6 to 9 band.
  - The story status check and the gate order are unchanged on a story with no pair.
  - On the same story range, jscpd's syntax-tree mode counts the new same-shape function
    pairs, report only, to size the blind spot A1 names.

**Slice 3. A shared change checks its importers.** Parts: Reach.

- The dispatch list becomes the union of three sources, and `shared_packages` derives from
  the diff.
- Done when:
  - A story that edits the API service's shared auth package runs the reporting service's
    gates too.
  - A story that edits one service's private code gates exactly what it gated before.
  - Services gated per lap are re-measured on the stories from row three of 5b.

## 7. Assumptions

1. **Agents duplicate by pasting.** The copies that hurt share their tokens with the
   original. An agent that writes its own version of a helper it never found produces a
   rewrite, which shares structure and not tokens.
   - Decided: the detector gates pastes. The search rule (invariant 6) and the reviewer
     carry rewrites.
   - Basis: in the reference repo, 72 pairs had a story commit write the later side, and
     the largest cross-service pairs are whole files copied unchanged. Over the last 30
     commits the detector found 2 new copies. That number fits low duplication and it
     fits a rewrite habit, and nothing measured tells the two apart.
   - If wrong: the gate passes the operator's first complaint. Section 1 done-when,
     Clone report, slice 2's blind-spot count.
2. **A copy the change introduced is almost always one to extract.** In a codebase agents
   maintain, two copies drift, and coincidences are rare. Text that matches shares a
   reason to change.
   - Decided: extract on the second copy, with coincidence as the only exit. Same-shape
     functions stay out of the gate.
   - Basis: the operator's default. Against it: per-domain error mappers match in shape
     while mapping different errors.
   - If wrong: Copy verdict gains a softer verdict. Invariant 1, invariant 4.
3. **Every machine that commits, and the coder's container, reaches the npm registry once
   per detector version.**
   - Decided: the script fetches on first use and fails closed (invariant 7).
   - Basis: the operator's machine fetches the base library over the network already. The
     coder's container is unverified.
   - If wrong: an offline first commit is refused, and the lap stops. Detector, the 5b
     latency row, slice 1.
4. **Generators mark their output in a file's first lines.**
   - Decided: Clone threshold drops pairs by marker as well as by path.
   - Basis: sqlc and the OpenAPI generator both write "Code generated ... DO NOT EDIT".
     They account for all 128 generated pairs in the reference repo.
   - If wrong: a generated pair refuses a commit until the repo adds its path to
     `ignore`. Clone threshold.
   - Revised (log 17): lockfiles carry no marker, so the adapter ignores them by path.
5. **Every cross-service import names a path form or a manifest package name.**
   - Decided: Unit identity has those forms only.
   - Basis: the reference repo's cross-service import is a Go module path. TypeScript
     relative imports across service roots are unverified.
   - If wrong: Unit identity, Dependent, slice 3.
   - Revised (log 18): a relative import counts when it resolves into the unit. A path
     alias such as a `tsconfig` `paths` entry is still unseen.
   - Revised (log 19): a quoted name counts only after an import keyword. A Go import
     carries no keyword, so a `go.mod` module still matches bare. A module path without a
     domain, such as `module api`, would match any `"api"` string.
6. **Shared code lives in the same repository as its callers.** A copy between two
   repositories of one workspace is not the problem the operator described.
   - Decided: the comparison scans one repository. The lap runs it once per repository.
   - Basis: the reference repo is a monorepo. Multi-repo workspaces are unverified.
   - If wrong: Clone report needs a cross-repository scan. Section 1 out of scope.
7. **Test duplication is a separate problem.** Repeated test setup is rarely the shared
   logic the operator means, and forcing extraction there costs laps for little gain.
   - Decided: tests, mocks and fixtures leave the default scan, and a repo opts them back
     in.
   - Basis: including tests, fixtures and mocks raises the reference repo's pairs from 636
     to 2,993. No fixture-sharing rule reaches every service: the reference repo's Go
     fixture guidance applies to one service, and its reporting service carries copies of
     the API service's mocks. A gate on tests would refuse a copy without saying where the
     shared version belongs.
   - If wrong: the default ignore list, the 5b latency row.
8. **Extraction costs at most one lap.** An owner moving a 20 to 80 line fragment finishes in
   the lap that found it.
   - Decided: no lap budget for extraction.
   - Basis: none.
   - If wrong: the 5b cost row, slice 2.
9. **50 tokens and 5 lines is the size where extraction pays.**
   - Decided: jscpd's own defaults are the threshold defaults.
   - Basis: the smallest repeated family in the reference repo, an 8-line role check at
     the top of 16 handlers, clears it. No measurement ties the number to the cost of a
     copy.
   - If wrong: Clone threshold's defaults.
10. **Copies inside one file are in scope.** They are half the reference repo's pairs:
    201 of 398.
    - Decided: Copy pair treats them like any other pair.
    - Basis: rule 2.12 has no file boundary, and an extraction inside one file is the
      cheapest kind.
    - If wrong: Copy pair gains a same-file exemption. The 5b cost row.
11. **jscpd 5.4.1 stays published, and its output keeps the shape the adapter reads.**
    - Decided: the version and hashes are pinned. Recorded reports test the adapter.
    - Basis: the package is MIT-licensed and on the npm registry. 5.4.2 shipped seven
      days before this note, too fresh to pin.
    - If wrong: the adapter and its recordings change with the pin. Detector, Clone
      report.
12. **Agents rarely stage part of a file.**
    - Decided: the commit span reads staged files from the working tree, because the
      detector scans the working tree.
    - Basis: none.
    - If wrong: an unstaged addition in a staged file can refuse a commit. Change span.
13. **One definition-line pattern per language finds the enclosing function.**
    - Decided: Enclosing unit reads upward for that pattern.
    - Basis: gofmt puts every top-level Go `func` and its closing brace at column 0.
      TypeScript, Python and Dart are unverified.
    - If wrong: a refusal names the wrong function. No verdict changes. Enclosing unit.
14. **Reuse findings are rare enough to check.** Basis: none. The reviewer's Reuse findings
    per story were not measured.
    - Decided: every Reuse decline gets the coincidence check.
    - If wrong: the 5b reviewer row.
15. **The workflow keeps committing with hooks off.** Basis:
    `coder/shared/story_commit.py:75`.
    - Decided: the lap runs its own check.
    - If wrong: the lap check runs twice. Harmless, and slice 2 can drop it.
16. **The base-library cache is current in the coder's container.** Basis: the workflows
    already read core's cache through `kit/paths.py`.
    - Decided: the lap locates the script there.
    - If wrong: the lap runs an older rule than the commit. Invariant 5.
17. **Most stories touch one service.** A story that edits no shared unit gates the same
    services after slice 3 as before.
    - Decided: slice 3's done-when compares the count per story, not a fixed number.
    - Basis: measured after log 19 on the 17 reference stories with commits. 11 gate
      exactly the plan. 2 add a service through a relative test-data path into another
      service. 4 add services whose own files the story changed. Resolving the set takes
      a median 1.3 s and at most 16 s.
    - If wrong: the 5b lap row, slice 3.
