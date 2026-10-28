# Configuration injection

Disclosure. Before this note was started I had read the saddlebag skill and README, the
`exec` output mask, the stack and environment references of the ostler skills, and the
workhorse transcript redactor. The design decisions those carried, and the ones settled in
conversation, are listed as claims in section 1b and re-derived or rejected in section 4.
Each part and concept below was checked against the question "would I have named this
without having seen the solution?"

## 1. Problem

An agent runs a product's commands and its QA against an environment. The values that make
the environment concrete, hosts, ports, flags, test accounts, passwords and tokens, sit mixed
in one dotenv file. To learn the hosts and ports the agent reads the file, and the passwords
and tokens come along into its context, its transcript, its checkpoints and its telemetry.
The operator cannot tell which of their secrets an agent has already seen.

Done looks like this to that operator:

- An agent learns every configuration value of an environment, and runs any command against
  it, while no secret value ever enters its context.
- A raw read of a secret-bearing file, or a command whose purpose is to print secrets, is
  refused before it runs, and the refusal names a command that gives the agent what it
  wanted.
- A test account's email, phone number and role are as easy for the agent to find as its
  password is hard.
- A repo that holds a mixed dotenv today moves to this shape with one command and a diff the
  operator reads.
- Zero secret values in the transcripts of a run against a migrated repo.

Out of scope:

- Masking secrets in the output of a command the agent runs outside the injector. Workhorse
  already redacts token shapes in transcripts, and wiring known values into it is its own
  change.
- Agent CLIs other than Claude Code (A1).
- A secret manager such as AWS Secrets Manager as a backing store for custody.
- Rendering the hook entry into a repo through farrier. Farrier renders git hooks only.
- Reading one-time codes from SMS.
- The QA plan's own `secret(from_env=…)` path (A11).
- A full book for saddlebag, which has none today. The pages this change touches in the
  ostler book are updated; saddlebag's book is a separate piece of work.
- The loss listed in 5b: an agent in a repo with no book loses raw reads of dotenv files and
  gets a masked view instead of the page.

## 1b. Claims

From the conversation that preceded this note:

1. The refusal is a PreToolUse hook of the agent CLI. (operator)
2. The hook ships as a subcommand of saddlebag, not a script. (me)
3. Non-secret variables live on the book's `environment` node under a nested key. (me)
4. One injector in ostler composes page literals with saddlebag's delivery. (me)
5. The dotenv file becomes a rendered artifact with secret lines blank. (me)
6. A test identity is one saddlebag record, whole, with a general metadata slot beside
   `username`. (operator and me)
7. Import classifies each dotenv line by an ordered rule list: held value, registered var,
   key name, token shape, URL userinfo. (me)
8. A secret is marked on the page by the word `secret` in place of its value. (me)

From documents that loaded before this skill:

9. A stack names one secret source, templates reference `${VAR}`, and compose runs under a
   `saddlebag exec` prefix. (ostler stack reference)
10. Saddlebag never returns a hidden value to its caller; username and description are
    printable metadata. (saddlebag skill and README)
11. `exec` masks held values in a piped child's output, in four spellings, above eight
    characters. (saddlebag README)
12. A workhorse turn's output passes through a redactor that masks five token shapes.
    (workhorse book)
13. A capability is a subcommand of a package, never a shell script beside the last one.
    (repository instructions)

## 2. Parts and concepts

### Level 1: parts

**Refusal.** Decides, before an agent's action runs, whether the action would put a secret in
front of the agent, and refuses it with the sanctioned way to get the same thing. Owns the
rules of what counts as exposure. Never knows a secret value, nor how configuration is laid
out. Hands nothing on; it only answers allow or deny, and asks Custody one yes-or-no question.

**Description.** The readable statement of what an environment is: its variables with their
values or a mark that says the value is held elsewhere, its addresses, the roles a step signs
in as. Owns the set of names, the literal values and which names are held. Never knows a held
value, nor how a command is launched. Hands the variable set to Injection.

**Custody.** Keeps identities and secrets as records with a public side and a hidden side,
delivers a hidden value straight to the thing that consumes it, and answers whether a given
text carries a held value. Owns the values, the metadata and the tags. Never knows the page,
nor what the consuming command is for.

**Injection.** Composes a Description with Custody's delivery so a command runs with the
whole environment, or so a loader that wants a file gets one. Owns the moment of composition
and the order in which sources win. Never knows a held value; Custody puts those in place.

**Migration.** Turns an existing mixed dotenv into a Description plus Custody records, line
by line, and shows the operator the result as a diff. Owns the orchestration of that move.
Never knows how Injection runs, nor what Refusal denies.

Flow. Migration runs once per repo: it asks Custody to classify the file's lines, writes the
literals and marks onto the Description, and asks Custody to take the held values from the
file. From then on the agent reads the Description to learn configuration, and runs commands
through Injection, which reads the Description and asks Custody to deliver each marked name
into the child. When the agent instead reaches for the raw file or a revealing command,
Refusal denies it and names the Description, the Injection command or Custody's masked view.
Refusal asks Custody one question, whether a text carries a held value, when the action's
text contains a candidate.

Test of the split: a secret vault, a readable spec, a launcher that marries the two, a
bouncer at the agent's door, and a one-time move from the old file. Two different code bases
fit it. No part is named after an existing module.

### Level 2: concepts

**Refusal**

| Concept | Owns | Never knows |
|---|---|---|
| Protected path | the shapes of paths whose contents are secret | what a file contains |
| Revealing command | the shapes of commands whose purpose is to print secrets, and the two exemptions: a secret-printing command piped into Custody's intake, and any command under the injector | paths |
| Pasted value | asking Custody whether the action's text carries a held value, and only when the text has a candidate token | the values |
| Redirect | the message naming the sanctioned alternative for a refused action | why the rule matched beyond its kind |
| Verdict | allow or deny with a reason (shared value type) | |

**Description**

| Concept | Owns | Never knows |
|---|---|---|
| Variable | a name with a literal value or a held mark | the value behind a mark |
| Held mark | the one spelling that says Custody holds this name | what Custody holds |
| Address | where a client reaches the stack (exists today) | |
| Role reference | the identity role a step signs in as | the account's attributes |
| Environment identity | the id by which Custody records are tagged to this page (read-only reference shared with Custody and Injection) | |

**Custody**

| Concept | Owns | Never knows |
|---|---|---|
| Record | the two-sided shape: a public side that always prints and a hidden side that only delivers | its consumers |
| Metadata slot | general printable attributes on the public side, a string map set at creation and edited afterwards by key | the hidden side |
| Delivery | placing a hidden value into a child's environment or a browser field | the command's purpose |
| Possession check | answering whether a text carries any held value, in any spelling the mask knows, without returning it | the caller |
| Output mask | masking held values in a child's piped output (exists) | the command |
| Secret-shape rules | the ordered predicates that say a line of a dotenv is secret: held value, registered var, key name, token shape, URL userinfo | the page |
| Masked view | a dotenv printed with secret lines masked and a count of what was masked | the page |
| Intake | reading a value from a file or stdin into the hidden side, inside Custody's own process | who asked |

Eight concepts. Secret-shape rules and Masked view are the file-facing half of Output mask
and Possession check, and splitting Custody into a store and a file reader would separate
the rules from the values they consult. Kept as one part.

**Injection**

| Concept | Owns | Never knows |
|---|---|---|
| Resolution | from an environment identity to its variable set, failing by name when a held mark has no record | values |
| Composition | setting literals, then handing the command to Delivery for the marked names; the process environment wins over any file | values |
| Rendered file | a dotenv written from the Description with held lines blank, derived and never a source | values |
| Consumer | the role Composition serves: a direct command, a compose stack, a file loader | |

**Migration**

| Concept | Owns | Never knows |
|---|---|---|
| Line sort | asking Secret-shape rules for each line's verdict | the rules themselves |
| Page diff | writing literals and held marks onto the Description, shown as a diff | values |
| Registration | asking Intake to take each secret line's value and create its record with `var` and environment tag | values |
| Report | the counts: lines, held, literal, and the operator's next line | |

## 3. Invariants

- **I1. A hidden value leaves Custody only by Delivery.** Owner: Record. Possession check,
  Masked view and Intake uphold it: each reads values and returns none.
- **I2. A Description carries no secret value.** Owner: Variable, through the book's doctor,
  which asks Possession check and the token-shape rule about each literal. Migration upholds
  it by sorting before writing.
- **I3. Every held mark resolves to exactly one record with that `var` and this environment
  identity.** Owner: Resolution, which fails naming the mark. Registration upholds it.
- **I4. Every refusal names an alternative that exists and that Refusal itself allows.**
  Owner: Redirect. A test runs each redirect's command through the Verdict.
- **I5. The process environment wins over the rendered file.** Owner: Composition. Rendered
  file upholds it by leaving held lines blank, so a stale file has nothing to win with.
- **I6. The rendered file is derived.** Owner: Rendered file: it is gitignored, regenerated
  on demand, and a file that differs from its Description is a finding.
- **I7. Refusal never needs Custody to be reachable for a path or command verdict.** Owner:
  Verdict. Only Pasted value asks Custody, and when Custody is unreachable it allows and says
  so on stderr (A5).

## 4. Forces and patterns

Forces:

- The shapes of protected paths and revealing commands grow as new secret managers and
  tools appear. Rules are data in one table, each kind a plain predicate.
- Custody's store already varies, keyring or daemon, behind one role. Possession check and
  Intake join that role.
- What consumes a composed environment varies today: a direct command, a compose stack, a
  loader that reads a file. Three variants of one role.
- Refusal runs on every Bash and Read call. It must cost milliseconds. The custody question
  is the only slow step and is asked only when the text holds a candidate token.
- Secret-shape rules have false negatives by nature. The backstop is a human reading a
  diff, not a stricter rule.
- The agent CLI hands the hook its action as JSON on stdin. A test must drive Refusal with a
  payload, no CLI involved.
- The tests must swap Custody's store, the filesystem and the hook payload.

Patterns between parts: a value handed along. Description produces a variable set,
Injection consumes it, Custody is a port each of the others calls with one small request.
Refusal is a separate stage with one port into Custody.

Patterns inside parts:

- Refusal: a rule table of plain predicates. Verdict is a frozen value. No variation beyond
  the table, so no role.
- Description: a plain value type on an existing node. Held mark is a constant.
- Custody: the existing store role gains two operations. Secret-shape rules are an ordered
  list of plain predicates, and Masked view and Line sort both read it.
- Injection: Consumer is a role with three variants, exec into a child, the compose prefix,
  and the rendered file. The choice is made by which command the operator runs. Composition
  depends on Delivery through Custody's port, never on a store.
- Migration: a sequence of four plain steps. No variation.

Claims, re-derived or rejected:

1. Re-derived. The hook is the only point the agent CLI offers before an action runs, and
   the force is that the value must never exist in the agent's context.
2. Re-derived from claim 13 and from a second force: the guard must ship to client repos,
   which `scripts/` never does.
3. Re-derived. The agent must read configuration without reading secrets, and the page is
   the one place that is both tracked and allowed.
4. Re-derived from the three-consumer force.
5. Re-derived from the loader variant: a loader that wants a file gets a derived one.
6. Re-derived. An account's attributes rotate together with its credentials, and the public
   side already exists; a general slot is one concept, a field per attribute is many.
7. Re-derived from the false-negative force, with the rule list moved into Custody so Masked
   view and Line sort share it.
8. Re-derived from a force not stated before: a literal and a reference must be told apart
   with no second key. A whole-value constant does that (A3).
9. Kept. The compose prefix is one variant of Consumer.
10. Kept. It is I1.
11. Kept. Masked view reuses it.
12. Kept and out of scope.
13. Kept. It is the placement rule for claim 2.

SOLID:

- Single responsibility: every Owns above reads without "and". Composition's two steps are
  one act, placing the environment.
- Open/closed: a fourth consumer adds one variant and one command. A new revealing command
  adds one table row.
- Liskov: each consumer variant is a kind of Consumer only.
- Interface segregation: Composition asks Custody for Delivery only. Refusal asks for
  Possession check only. Migration asks for Secret-shape rules and Intake.
- Dependency inversion: Composition's Never-knows is values; it depends on the port, not a
  store.

Open lookups, resolved in section 5: where the environment node declares its keys; how a
PreToolUse decision is spelled; what the secret record holds today; how the stack already
wraps compose; where ostler's environment commands live.

## 5. Mapping onto the existing system

Revision log:

- Section 2, Custody: Secret-shape rules and Masked view added, and Migration's Line sort
  reduced to asking them. Finding: the guard is installed at user scope and applies in a
  repo with no book, so Redirect needed an alternative that exists there (I4), and the
  rules would otherwise be written twice.
- Section 2, Migration: Registration delegates to Intake. Finding: values would otherwise
  pass through ostler's process; `saddlebag secret set` already reads values on stdin.
- Section 3, I7 added. Finding: the keyring route can block on an unlock prompt
  (saddlebag skill, errors table), and a blocked hook blocks every Bash call.

**Refusal.** New. `saddlebag/saddlebag/guard.py`, exposed as `saddlebag guard --hook` and
`saddlebag guard install --user|--project`. The decision shape exists in
[check_no_shell.py:114](scripts/check_no_shell.py:114) and its `_hook` at line 142: a JSON
payload on stdin, `hookSpecificOutput.permissionDecision = "deny"` on refusal. The user's
settings already register two PreToolUse hooks on `Bash` and `Write|Edit|MultiEdit|Bash`, so
the entry shape is known. Mismatch: `check_no_shell.py` lives under `scripts/` and ships to
nobody, where this guard must reach every repo the operator works in. The design is right:
the guard is a saddlebag verb. Protected path and Revealing command are tables in
`guard.py`. Pasted value calls Custody's possession check over the existing route
(`route.py`).

**Description.** Reshape. The environment node's keys are declared at
[registry.py:618](ostler/ostler/registry.py:618): `selector`, `services`, `backing`,
`local-only`, `sharing`, `addresses`, `code`, `config`, `verify`, `fixture`. Variable is a
new `BulletKey("variables", nested=True)`. Held mark is the constant `secret`. Address
exists. Role reference: a runbook step today names no role; the saddlebag skill's `role=`
tag convention is the only carrier, so a runbook `sign-in-as:` key is the home. Environment
identity exists as the page id, matching the skill's `environment=<id>` convention (A7).
Doctor gains I2 on `variables`. The reference `environment.md` and the ostler skills are
updated with the key.

**Custody.** Exists, reshaped in three places.

- Record exists: [models.py:54](saddlebag/saddlebag/models.py:54) has `name`, `username`,
  `description`, `var`, `tags`, `fields`, and `to_dict` says it never carries a value.
  Metadata slot is new: `metadata: Mapping[str, str]`, set by `--meta k=v`, edited by
  `secret meta NAME k=v` and `secret unmeta NAME k` (the same pair tags have in `tag` and
  `untag`), printed by `list`, bound by `exec --env VAR=name.meta.k` and `fill --field
  meta.k` as the username is: plain, never masked. Catalogue and Vault serialisation carry
  it; a catalogue written before the slot loads with an empty map.
- Delivery exists: `fill` in `browser.py`, `exec` at [cli.py:203](saddlebag/saddlebag/cli.py:203).
- Output mask exists: `redact.py`. Possession check is new and reuses its derived forms
  through the daemon protocol and the keyring path alike.
- Secret-shape rules and Masked view are new: `saddlebag env show FILE`, `saddlebag env
  keys FILE`, `saddlebag env classify FILE --json`. The token-shape rule takes the five
  prefixes workhorse's redactor already names.
- Intake exists as `secret set` on stdin; `saddlebag env import FILE --keys K,K --tag …`
  is the file-reading form.

**Injection.** Reshape. `ostler/ostler/environments/secrets.py` already has the role:
`SecretSource` with `names()`, `files()`, `exec_prefix()`, and `SaddlebagSource` at line
111 builds the compose prefix from a tag query. That is the compose variant of Consumer.
Mismatch: `SaddlebagSource.names()` draws the required names from `saddlebag list`, while
the design draws them from the page's held marks and checks each against custody (I3). The
design is right: the page is the spec, and `list` confirms. `names()` stays for the stack's
`${VAR}` check and reads the page first. Resolution and Composition are new in
`environments/`, exposed as `ostler env exec <environment> -- <command>`. Rendered file is
new, `ostler env render <environment>`, and the file is added to the repo's gitignore by
the command.

**Migration.** New. `ostler env import-dotenv FILE --environment <id>` in
`environments/`: asks `saddlebag env classify`, writes the page diff, calls `saddlebag env
import` for the held keys, prints the Report.

What the existing system has that the design lacks:

- `DotenvFile` and `DecryptCommand` secret sources in `secrets.py`. Not waste: they are
  two more variants of the stack's secret source, read by ostler and compose, never by the
  agent. Refusal denies the agent's reads, not the stack's.
- Workhorse's redactor takes a `secrets` iterable that no caller passes. A concept the
  design lacks on purpose: out of scope, and the values Injection delivers are the set to
  pass it later.
- The QA plan's `secret(name, from_env=…)`. A second path for secrets into a run. Out of
  scope (A11); a run started under `ostler env exec` satisfies `from_env` without a file.

Claims against the existing system: 9, 10, 11, 12 and 13 hold in the code as read. 1 to 8
are new and the code follows none of them yet.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| saddlebag's users | every verb behaves as documented | `saddlebag/tests` | 235 passed | all pass, plus the new tests |
| ostler stack users | `env up` with a `saddlebag:` source wraps compose and writes no secrets file | `ostler/tests` matching env, stack, secret | 248 passed | all pass, plus the new tests |
| an agent in a repo with no book | can read a dotenv raw | nothing | reads allowed | lost on purpose; `saddlebag env show` is the replacement, listed out of scope in section 1 |
| an agent at the keyboard | `exec` becomes the command on a terminal and masks nothing | `saddlebag/tests` | covered by the 235 | unchanged |
| every Bash and Read call | two PreToolUse hooks run before it | nothing | not measured (A5) | the guard's path and command verdicts add at most 50 ms; the custody question runs only on a candidate token |
| the stack's `${VAR}` check | a template name no source defines fails `env check` by name | `ostler/tests` | covered by the 248 | unchanged, with the page as the first source of names |

## 6. Slices

1. **Refuse and show, in any repo.** Refusal (Protected path, Revealing command, Redirect,
   Verdict), Custody (Secret-shape rules, Masked view), `guard install`. Done when: in a
   repo whose dotenv holds a stored value, `cat .env` and a Read of it are denied with a
   message naming `saddlebag env show .env`, that command prints the file with the held
   line and the shape-matched lines masked and a count, `printenv` is denied, `openssl rand
   -hex 24 | saddlebag secret set x` is allowed, every redirect's command passes the guard
   (I4), the guard's verdict time is measured and under 50 ms, and both suites hold.
2. **Identities whole.** Custody (Metadata slot, Possession check), Refusal (Pasted value).
   Done when: `secret create --meta phone=…` round-trips through keyring and daemon, `secret
   meta` overwrites a key and `secret unmeta` drops one and names a key it cannot find, `list`
   prints it, `exec --env QA_PHONE=qa_admin.meta.phone` injects it, a Bash command whose
   text contains a stored value is denied, and with the daemon stopped the same command is
   allowed with a stderr note (I7). Suites hold.
3. **The page is the environment.** Description (Variable, Held mark, Role reference),
   Injection (Resolution, Composition, Rendered file). Done when: an environment page with
   three literals and two held marks passes doctor, a literal equal to a held value fails
   doctor (I2), `ostler env exec local -- env | sort` shows the literals and `[REDACTED]`
   for the held names, a held mark with no record fails by name (I3), `ostler env render
   local` writes the file with the two lines blank and adds it to gitignore, and the stack's
   `${VAR}` check still passes on the existing books. Suites hold.
4. **Move a repo.** Migration, Custody (Intake from file). Done when: a fixture dotenv with
   eight lines, three of them secret by different rules, becomes a page diff with five
   literals and three marks, three records with `var` and the environment tag, a report of
   8, 3, 5, and `ostler env render` reproduces the file with the three lines blank. The
   values appear in no ostler process output. Suites hold.
5. **Say so.** The saddlebag skill, README and `docs/SECURITY.md`; the ostler skill's stack
   and environment references; the ostler book pages the change touched, restamped. Done
   when `make lint` passes and `ostler doctor` raises no new finding on a touched page.

## 7. Assumptions

1. **A2. Dotenv loaders and compose let a real environment variable win over the file.**
   Decided: Rendered file leaves held lines blank and Composition sets the variable. Basis:
   python-dotenv's `override=False` default, Node dotenv's same default, compose's documented
   precedence of shell over `.env`. A project's loader with `override=True` is the exception.
   If wrong: Rendered file (section 2), I5, slice 3's done-when.
2. **A1. Claude Code is the only agent CLI whose pre-action hook matters now.** Decided:
   one hook shape, one install command. Basis: the operator's settings register PreToolUse
   hooks for it alone. If wrong: Refusal's install concept gains a variant per CLI.
3. **A5. Custody's possession check answers in milliseconds over the daemon and may block
   on the keyring route.** Decided: I7, and the 50 ms budget on path and command verdicts
   alone. Basis: none; measured in slice 1 and 2. If wrong: Pasted value may need a cache,
   or the keyring route is excluded from it.
4. **A4. Path shapes and command shapes catch the common mistake, and the holes are
   accepted.** Decided: a table, not a parser. Basis: the operator's own words in the
   conversation. If wrong: Refusal gains a concept per hole, or the problem moves to the
   permission layer.
5. **A9. The operator reads the import diff before committing.** Decided: the diff is the
   backstop for a line the rules missed, and no interactive prompt. Basis: the repo's commit
   procedure reads the diff first. If wrong: Migration gains a confirmation step.
6. **A7. The environment page's id is the value of the `environment=` tag.** Decided:
   Resolution queries custody with the page id. Basis: the saddlebag skill states the
   convention. If wrong: Description gains an explicit tag key.
7. **A11. A QA plan's `secret(from_env=…)` is satisfied when the run starts under the
   injector.** Decided: out of scope. Basis: `from_env` reads the process environment, which
   Composition sets. If wrong: slice 3 adds a QA run case.
8. **A3. No real configuration value is the literal word `secret`.** Decided: the held mark
   is that word alone. Basis: none. If wrong: Held mark becomes `saddlebag:` and the
   reference updates.
9. **A6. The hook payload names a Read's path in `tool_input.file_path` and a Bash
   command in `tool_input.command`.** Decided: Verdict reads those two. Basis: the no-shell
   guard's `hook_decision` reads the same payload. If wrong: Verdict's reader only.
10. **A8. The eight-character floor from the output mask fits the masked view.** Decided:
    Masked view masks by key rule regardless of length and by value rule above the floor.
    Basis: README's reasoning that short strings match by accident. If wrong: Masked view's
    value rule.
11. **A10. Each slice is one story on the `dev` branch worktree, landed by rebase, and
    none needs a live book run stopped.** Decided: the order in section 6. Basis: the repo's
    commit and branch rules. If wrong: the slices reorder, not their content.
