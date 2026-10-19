---
type: cli
slug: standalone-programs
title: Standalone programs
---
# Standalone programs

Two programs run outside the `ostler` binary's own dispatch: a one-shot repo migration script a
maintainer runs by hand, and the sandbox's loopback port forwarder its container entrypoint
starts as a background process. Both run through `python3`, not through `ostler`.

- binary: python3
- detail: [ostler](cli.md)

## Commands

### okf-migrate
- usage: python3 -m ostler.scripts.okf_migrate [ROOT] — walks ROOT's `docs/epics`, `docs/features`
  and `docs/specs` trees, rewrites whatever legacy JSON-sibling or frontmatter-less markdown it
  finds into the current OKF markdown format, and prints `migrated <root>: <report>`, a dict
  counting how many epics, stories, features and specs it touched and whether it rewrote the
  epics backlog queue
- args: root — the repo root to migrate; defaults to the current directory when omitted
- exits: 0 — `migrate` only ever counts and rewrites what it finds; a tree with nothing legacy
  left prints a report of all zero counts and `'todo': False`, not an error
- run: invoke(argv=["-m", "ostler.scripts.okf_migrate", "okf-migrate-fixture"])
- verify: exit_status(code=0)
- verify: stdout(matches="^migrated okf-migrate-fixture: \\{'epics': 1, 'stories': 0, 'features': 1, 'specs': 0, 'todo': True\\}$")
- verify: contents(subject="okf-migrate-fixture/docs/epics/sample-epic/epic.md", matches="(?s)^---\\ntype: epic\\n")
- verify: absent(subject="okf-migrate-fixture/docs/epics/sample-epic/seed.json")
- verify: absent(subject="okf-migrate-fixture/docs/epics/sample-epic/dependencies.json")
- verify: contents(subject="okf-migrate-fixture/docs/epics/index.md", matches="(?m)^- \\[sample-epic\\]\\(sample-epic/epic\\.md\\)$")
- verify: contents(subject="okf-migrate-fixture/docs/features/legacy-page.md", matches="(?s)^---\\ntype: feature\\n")
- fixture: [legacy book layout](fixtures/legacy-book-layout.md) — seeds the pre-OKF epic, its
  `seed.json`/`dependencies.json` siblings, the `epics-todo.json` queue naming it, and a
  frontmatter-less feature page, all under `okf-migrate-fixture/`
- code: ostler/ostler/scripts/okf_migrate.py::migrate@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::main@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_epic@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_todo@96c0602e35de
- code: ostler/ostler/scripts/okf_migrate.py::_migrate_features@96c0602e35de
- detail: [Migrating the legacy book layout](concepts/migrating-the-legacy-book-layout.md)

### sandbox-forwarder
- usage: python3 ostler/docker/sandbox/forwarder.py [READY-FILE] — reads
  `OSTLER_SANDBOX_FORWARD` as a JSON object of `{"<local-port>": "<host>:<port>"}` entries, binds
  one loopback listener per entry, and once every listener is bound writes the count it bound to
  READY-FILE before it blocks relaying traffic forever
- args: ready-file — the path the forwarder writes its bound-listener count to once every
  listener is up; optional, and never written when a mapping entry is rejected first
- exits: 2 — a mapping value with no `host` before its last `:` is rejected with
  `forwarder: bad upstream <value> for port <port>` on stderr, before any port is bound and before
  the ready-file is ever written
- run: invoke(argv=["ostler/docker/sandbox/forwarder.py", "forwarder-ready.txt"], env={"OSTLER_SANDBOX_FORWARD": "{\"18080\": \"no-colon\"}"})
- verify: exit_status(code=2)
- verify: stderr(matches="^forwarder: bad upstream 'no-colon' for port 18080$")
- verify: absent(subject="forwarder-ready.txt")
- fixture: none, because the rejected mapping is passed as an environment variable, not read from
  a file
- code: ostler/docker/sandbox/forwarder.py::main@1a617ef8e11b
- detail: [Sandbox port forwarding](concepts/sandbox-port-forwarding.md)

### settle-review-answers
- usage: python3 -c "...Ostler(root=...).settle_answers(STORY, FILED)..." — settles a story's
  filed review finding ids against the markdown Answer list in its spec directory, splitting
  them into fixed (with evidence), declined (with a reason) and still-open, collecting one error
  per malformed or unknown-disposition heading, and never touching `story.md`
- args: story, filed — the story's slug, and the finding ids a run filed against it
- exits: 0 — a malformed heading or an unanswered finding is reported as data in the ledger, not
  raised
- run: invoke(argv=["-c", "import json\nfrom ostler.api import Ostler\nprint(json.dumps(Ostler(root='answer-scratch').settle_answers('sx', ['F1', 'F2', 'F3'])))\n"], env={"STABLEMATE_ARTIFACTS_DIR": "answer-scratch/art"})
- verify: exit_status(code=0)
- verify: json_path(path="fixed[0]", equals="F1")
- verify: json_path(path="declined[0].id", equals="F2")
- verify: json_path(path="declined[0].reason", equals="out of scope for this story")
- verify: json_path(path="open[0]", equals="F3")
- verify: json_path(path="errors[0]", matches="^malformed answer heading '## F4 fixed': expected '## <finding-id>: fixed' or '## <finding-id>: declined'$")
- verify: json_path(path="all_answered", equals=false)
- fixture: [answer settlement scratch repo](fixtures/answer-settlement-scratch-repo.md) — seeds a
  story `sx` and its `review-answers.md`, naming one fixed finding with evidence, one declined
  finding with a reason, and one malformed heading
- code: ostler/ostler/answers.py::parse_answers@6c168f1fb49d
- code: ostler/ostler/api.py::Ostler.settle_answers@0001e6a151cb
- code: ostler/ostler/edit.py::settle_answers@7144473df397
- detail: [The Ostler facade and book utilities](concepts/the-ostler-facade-and-book-utilities.md)

### qa-context-source-repository
- usage: python3 -c "...Ostler(root=...).qa_context(..., repositories=[SourceRepository(...)])..." —
  maps a change across one or more independently-versioned checkouts, each scoped to the surfaces
  it owns, instead of the single checkout `qa context --source-root` addresses in the one repo it
  runs from
- args: none
- exits: 0 when every repository resolves and no health finding is an error
- run: invoke(argv=["-c", "import json\nfrom ostler.api import Ostler\nfrom ostler.qa.source_context import SourceRepository, SourceScope\nrepo = SourceRepository(id='demo-repo', checkout='qa-scratch', base='HEAD', scopes=(SourceScope(surface='demo', root='src'),))\noutcome = Ostler(root='qa-scratch').qa_context(base='HEAD', spec='s2', repositories=(repo,))\nprint(json.dumps(outcome.data))\n"], env={"STABLEMATE_ARTIFACTS_DIR": "qa-scratch/art", "STABLEMATE_CONFIG": "qa-scratch/qa.toml", "GIT_DIR": "repo.git"})
- verify: exit_status(code=0)
- verify: json_path(path="version", equals=2)
- verify: json_path(path="changedCode[0].path", equals="src/demo.py")
- verify: json_path(path="changedCode[0].repository", equals="demo-repo")
- verify: json_path(path="repositories[0].id", equals="demo-repo")
- verify: json_path(path="repositories[0].scopes[0].surface", equals="demo")
- fixture: [qa scratch repo](fixtures/qa-scratch-repo.md) with a QA scratch repo with one changed
  source file and a plan under spec s1
- code: ostler/ostler/qa/source_context.py::SourceRepository@c8ac0146f0b0
- code: ostler/ostler/qa/source_context.py::SourceScope@c8ac0146f0b0
- code: ostler/ostler/qa/context.py::_repository_changes@ae1dfb851ad2
- code: ostler/ostler/qa/context.py::_repository_row@ae1dfb851ad2
- code: ostler/ostler/api.py::Ostler.qa_context@0001e6a151cb
- detail: [Compiling a book into a QA plan](concepts/compiling-a-book-into-a-qa-plan.md)
