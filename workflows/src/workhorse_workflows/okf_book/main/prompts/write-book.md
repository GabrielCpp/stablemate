Write the OKF book for this repository's `{{ service }}` {{ kind }} surface.

You run from the book's folder, `{{ book_folder }}/` in this repository, and you can write only
under it. You can read the app's source, without its tests, test doubles and fixtures, in a
copy under `{{ source_view }}/`. Each file there is the repository's file at the same path under
`{{ source_folder }}/`, and a `code:` bullet cites that repository path. Your shell runs the
three commands below, and nothing else. Start each shell call with one of them, spelled in
full exactly as written here, never through a variable, an alias or a `cd`. The shell refuses
any other spelling, and a refused call means only that its spelling was wrong: the three
commands keep working. Read files with your file tools. Where you have none, read them in
the shell with `cat`, `head`, `tail`, `sed -n`, `rg`, `grep`, `ls` or `find`, joined by `|` at most,
with no redirection, `;` or `&&`. Give such a read an absolute path, in the book, the source copy
or the skill. The repository's root is `{{ repo_root }}`, and a path the skill or this prompt
gives relative to the repository starts there.

- `ostler scaffold` and `ostler fmt` run through this command, with the same arguments after
  it, `{{ ostler }} scaffold …` or `{{ ostler }} fmt …`. It runs {{ ostler_run_cap }} times in all
  and prints the head of what ostler says. `ostler checks` does not run here: the check
  vocabulary is the skill's `check-vocabulary.md` reference.

  ```
  {{ ostler }}
  ```

- The surface: service `{{ service }}`, kind `{{ kind }}`, entry point `{{ entry }}`, a path
  relative to the repository root.
- The book is the folder you run from. Some pages may already be there. Keep what is right,
  fix what is wrong, and add what is missing.
- The format is the `ostler-okf` skill. Load it first and hold the book to its bar:
  {{ skill_command("ostler-okf") }}
- The book's root is `entries.md`, in the folder you run from. It has frontmatter `type: entries`, `slug:
  entries` and `title: {{ service }}`, then one `- [title](page.md)` line per entry page. Every
  other page must be reachable by links from an entry page.
- Read the product's source first. The book must be complete:
{% if kind == "cli" %}
  every command, option, flag and positional, every message the app prints and every exit
  code it returns, every file format it reads or writes,
{% elif kind == "http" %}
  every endpoint with its method and path, every parameter, header and body field it reads,
  every status code, header and body it answers with, every error it returns, every stored
  record it reads or writes. Each endpoint is a page of its own beside its server page, with
  a `server:` link to that page, and the server lists it under `## Endpoints` as a
  `- [id](page.md)` line. An endpoint written inline under the server is moved onto its own
  page after your turn,
{% else %}
  every screen and route, every control with its role and accessible name, every
  interaction and what it changes, every message the app shows, every value it stores,
{% endif %}
  and every rule the app applies must be stated as a claim with a `verify:` that would fail
  if the app stopped doing it.
- Every {% if kind == "cli" %}command{% elif kind == "http" %}endpoint{% else %}screen{% endif %} sits on a journey a user takes. Write each journey as a `flow` page under
  `flows/`, as the skill's flow reference says, with its `start:`, its `steps:`, its `end:` and
  its `fixture:`, and link it from a page the entries page reaches. The check names every
  {% if kind == "cli" %}command{% elif kind == "http" %}endpoint{% else %}screen{% endif %} no flow's steps link.
{% if kind == "cli" %}
  A step performs one command line, so the node it links states exactly one `run:`, and
  `start:` checks with `absent(subject="<file>")` that a file the walk creates is not there yet.
{% endif %}
{% if kind != "cli" %}
- The run brings the app up from the book alone. Write the stack `runbook` that starts it
  from a clean checkout, with the port, the health check and every service it needs, as the
  skill's runbook reference says. Assume the machine it runs on has a shell,
  git, curl and python3, and nothing else: no other language toolchain, no cloud CLI, no
  emulator, no database. The runbook fetches and starts every other tool and service the app
  needs.
  The health check is a route the app's source serves to say it is ready. Name that route,
  and never invent one. If the source serves none, name `/healthz` and say in your reply that
  the app must implement it. That run fails bring-up, and the report sends the gap to the app.
  The command below reports the step where bring-up failed, and it is the only way to probe
  that machine.
{% endif %}
{% if kind == "cli" %}
- A scenario runs the app only through a QA tool this repo offers. The page's `binary:` names
  one of these tools, and each `invoke(argv=[...])` carries the rest of the command line after it:
{% for tool in qa_tools %}
  - `{{ tool.name }}`{% if tool.description %}: {{ tool.description }}{% endif %}
{% else %}
  - none. Say so in your reply, because no scenario can run the app.
{% endfor %}
{% endif %}
- Every claim runs against the real app. This command compiles the book into scenarios and
  runs them, and prints each check that failed with what it expected and what it got. Name
  pages after it, each path relative to the repository root, and it runs only the scenarios on
  those pages. A fixture page runs the first scenario that arranges its fixture, so a seed is
  tried on its own. Each run brings the app up first, which takes a minute. Once a flow or a
  fixture page is whole, run the command on it, and fix every failure it prints before you run
  it again:

  ```
  {{ exercise }} <page> …
  ```

  Claims on one page run in document order in one working directory, so a claim sees the
  state the claims above it left.
- A check that passes on the real app can still pass on a wrong one. Before you finish, go
  through every rule the book states. Name the most plausible wrong implementation of it, the
  one a hurried developer would write, and check that at least one claim's example would fail
  on it. If none would, change the example or the check until one does.
- Give every rule an example on each side of every boundary it draws. Where it tells inputs
  apart by comparing them, show a pair that differs in exactly one part, once for each part.
  Where it counts or measures, show the values just below, at, and just above the limit.
- A check that parses output passes on any layout. For every structured output the app prints,
  answers or writes, state its layout, and check at least one example against its exact text.

{% if run_groups or check_groups or run_failures or operator_answer %}
## Where the book stands

You own this book. The run checked it and ran it against the app after your last turn, and
this is what failed. Read all of it before you edit a page. Many failures that share a status,
a fixture, a role or a route prefix usually share one cause, and you fix that cause once, in
the one page that holds it, often a fixture or a shared page.

Some causes are not the book's, and no page edit fixes them. For each numbered group below,
name the side that has to change in your reply. A group you name another side's is held back
from the book on every later lap, and goes to the operator as a finding with your evidence.

{% if run_groups %}
### The run

The run grouped its failed checks by what was observed. The cause beside each group is a
guess a per-check rule made, so treat it as a hint.

{% for group in run_groups %}
{{ group.number }}. `{{ group.text }}`: {{ group.count }} checks, guessed `{{ group.cause }}`.
   For example: {{ group.sample }}
{% if group.pages %}
   Pages: {% for page in group.pages %}`{{ page }}`{% if not loop.last %}, {% endif %}{% endfor %}

{% endif %}
{% endfor %}

What the run printed{% if run_lines_left %}, its first lines, with {{ run_lines_left }} more in its summary{% endif %}:

```
{% for line in run_lines %}
{{ line }}
{% endfor %}
```

- The whole run, every failed check with what it expected and what it observed, is
  `{{ run_summary }}`.
- The test plan the toolchain compiled from the book is `{{ run_plan }}`. It is what was sent
  to the app. Where a request in it differs from what the page says, the toolchain changed it.
{% if run_failures %}
- Each failure the book can fix, after the page that covers it, is in `{{ run_failures }}`.
{% endif %}

{% endif %}
{% if check_groups %}
### The check

The check grouped its problems by the rule that raised them.

{% for group in check_groups %}
{{ group.number }}. `{{ group.code }}`: {{ group.count }} problems, for example:
{% for sample in group.samples %}
   - {{ sample }}
{% endfor %}
   Nodes: {% for node in group.nodes %}`{{ node }}`{% if not loop.last %}, {% endif %}{% endfor %}{% if group.nodes_left %}, and {{ group.nodes_left }} more{% endif %}

{% endfor %}

Every problem of the check is in `{{ check_problems }}`.

{% endif %}
{% if earlier %}
### What you named on earlier laps

{% for finding in earlier %}
- Lap {{ finding.lap }}, {{ finding.measured }}: `{{ finding.signature }}`, {{ finding.count }}, named `{{ finding.side }}`. {{ finding.evidence }}
{% endfor %}

A group you named the book's that is back with the same count was not fixed by your edit.
Read it again: the edit was wrong, or the cause is not in the book.

{% endif %}
{% if operator_answer %}
### What the operator answered

{{ operator_answer }}

{% endif %}
### The sides

- `book`: a page states something the app's source contradicts, sends a request the source
  refuses for a reason the page could have read, or uses an arrangement its fixture page does
  not make. A fixture page is a book page.
- `ostler`: the toolchain compiled the page into something the page does not say, or cannot
  express a check the page is right to make.
- `app`: the page matches what the source is written to do, and the app does something else.
- `environment`: the stack lacks something the app needs that no fixture page can supply: a
  service that is down, a credential, an external provider, seed data only an operator loads.
- `unattributed`: you read the evidence and cannot tell. Say what you would need to see.

Name a side other than `book` only with evidence: the line of the plan, the source or the log
that shows the cause, with its path.

{% endif %}
You are done when both commands pass: the check below prints "No problems", and the command
above prints "All N scenarios pass". The two commands share {{ check_and_scenario_run_cap }} runs in all, so fix
every problem a run prints before you run it again.

```
{{ check }}
```

Do not commit. Reply with one JSON object and nothing else. Name one side for each numbered
group you were shown, and leave both lists empty when you were shown none:

```json
{
  "run": [{"group": 1, "side": "{{ sides | join('" | "') }}", "evidence": "what you read that shows the cause, with its path"}],
  "check": [{"group": 1, "side": "{{ sides | join('" | "') }}", "evidence": "what you read that shows the cause, with its path", "nodes": []}]
}
```

A check verdict that lists `nodes` judges only those nodes of its group. Give the group a
second verdict with no `nodes` for the rest.
