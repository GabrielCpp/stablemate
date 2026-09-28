Repair {{ pages | length }} pages of the OKF book for this repository's `{{ service }}` {{ kind }} surface.

You run from the book's folder, `{{ book_folder }}/` in this repository, and you can write only
under it. You can read the app's source, without its tests, test doubles and fixtures, in a
copy under `{{ source_view }}/`. Each file there is the repository's file at the same path under
`{{ source_folder }}/`, and a `code:` bullet cites that repository path. Your shell runs the
{% if exercise %}three{% else %}two{% endif %} commands below, and nothing else. Start each shell call with one of them, spelled in
full exactly as written here, never through a variable, an alias or a `cd`. The shell refuses
any other spelling, and a refused call means only that its spelling was wrong: the
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

- The format is the `ostler-okf` skill. Load it first and hold every page you touch to its bar:
  {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
{% if exercise %}
- The book failed its run against the real app. Each turn repairs a few of its pages. These are
  yours, each path relative to the repository root, with every check of the run that failed on
  it, every problem the check reports on it, and the source files it cites:
{% else %}
- The book is too large for one turn, so each turn repairs a few of its pages. These are
  yours, each path relative to the repository root, with every problem the check reports on
  it and the source files it cites:
{% endif %}
{% for repair in pages %}

  `{{ repair.page }}`{% if repair.sections %}, only {% for section in repair.sections %}{% if section %}`### {{ section }}`{% else %}the lines under no `###` heading{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}{% endif %}
{% for problem in repair.problems %}
  - {{ problem }}
{% endfor %}
{% if repair.sources %}
  Cites: {% for source in repair.sources %}`{{ source }}`{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}
{% endfor %}

{% if pages | selectattr("sections") | list %}
- A page followed by sections is too large to read whole. Repair those sections only. Find each
  with `rg -n '^### <id>$' <page>`, and read it with `sed -n` up to the next heading. Change
  nothing outside them. The check reports only the problems in them, and any your edits cause.
{% endif %}
- A cited `path:first-last` is the lines of the declaration or yaml key a citation names. Read
  those lines only, never the rest of the file. Where a claim rests on code outside them, leave
  the claim as it is, and name it in your reply with the declaration it needs.
- Fix each problem at its cause. Read the source a claim describes before you change the claim.
{% if exercise %}
  A check the run failed is fixed in the book, never by weakening it. Where the app refused a
  request, read the source for what it requires, and arrange that with a `fixture:`.
{% endif %}
  A claim the source contradicts is corrected to what the source does. A claim with no `verify:`
  gets one that would fail if the app stopped doing it. A claim that arranges nothing gets a
  `fixture:` naming the arrangement, or `fixture: none, because …`.
{% if flow_folder %}
- A {% if kind == "cli" %}command{% elif kind == "http" %}endpoint{% else %}screen{% endif %} on no flow goes onto a journey a user takes. Link it from a step of a flow that
  already walks near it, or write a new `flow` page at `{{ new_flow_page }}`, as the skill's flow
  reference says, and link that flow from a page the entries page links.
- A page nothing reaches is linked from the page a reader would come from, or deleted when it
  documents nothing the app does.
- Besides your pages, you may change these, and write the new flow page `{{ new_flow_page }}`:
{% for page in journey_pages %}
  - `{{ page }}`
{% endfor %}

  Find the flow that walks near it by the flow pages' headings, read with `rg -n '^#'`, and read
  only the flow you extend whole. On any page of these that is not a flow, add link lines and
  change nothing else: add the link under the heading it belongs to. Code puts back such a page
  when a turn changed more than that.
{% endif %}
- A `fixture:` that names a fixture the repository does not declare is fixed by declaring it:
  write its `fixture` page under `{{ fixture_folder }}/`, as the skill's fixture reference says.
  You may write and change any page in that folder.
- Do not edit `entries.md`. Code writes it.
- Change no page but {% if flow_folder %}those above{% else %}yours{% endif %} and the fixture pages. Code puts back every other change when the turn ends, so
  a fix made there is lost. The check below covers your pages and reports every problem your edits
  cause on a page you did not touch, such as an endpoint a flow you edited no longer walks.

{% if exercise %}
- This command compiles the whole book into scenarios, runs them against the real app, and
  prints each check that failed with what it expected and what it got:

  ```
  {{ exercise }}
  ```

You are done when the check below prints "No problems", and the command above no longer
prints a failure on your pages. The two commands share {{ check_run_cap }} runs in all, so fix
every problem a run prints before you run either again.
{% else %}
You are done when the check below prints "No problems". It runs {{ check_run_cap }} times in all,
so fix every problem a run prints before you run it again.
{% endif %}

```
{{ check }}
```

Do not commit. Reply with one line saying which pages you changed.
