Write the OKF book for this repository's `{{ service }}` {{ kind }} surface.

You run from the book's folder, `{{ book_folder }}/` in this repository, and you can write only
under it. You can read the app's source, without its tests, test doubles and fixtures, in a
copy under `{{ source_view }}/`. Each file there is the repository's file at the same path under
`{{ source_folder }}/`, and a `code:` bullet cites that repository path. Your shell runs the
three commands below, and nothing else. Start each shell call with one of them, spelled in
full exactly as written here, never through a variable, an alias or a `cd`. The shell refuses
any other spelling, and a refused call means only that its spelling was wrong: the three
commands keep working. Read files with the Read, Glob and Grep tools, never the shell.

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
  {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
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
  record it reads or writes,
{% else %}
  every screen and route, every control with its role and accessible name, every
  interaction and what it changes, every message the app shows, every value it stores,
{% endif %}
  and every rule the app applies must be stated as a claim with a `verify:` that would fail
  if the app stopped doing it.
{% if kind != "cli" %}
- The run brings the app up from the book alone. Write the stack `runbook` that starts it
  from a clean checkout, with the port, the health check and every service it needs, as the
  skill's runbook reference says.
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
  runs them, and prints each check that failed with what it expected and what it got:

  ```
  {{ exercise }}
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

You are done when both commands pass: the check below prints "No problems", and the command
above prints "All N scenarios pass". The two commands share {{ check_and_scenario_run_cap }} runs in all, so fix
every problem a run prints before you run it again.

```
{{ check }}
```

Do not commit. Reply with one line saying which pages you wrote.
