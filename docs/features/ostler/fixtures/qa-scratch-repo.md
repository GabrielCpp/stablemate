---
type: fixture
slug: qa-scratch-repo
title: qa scratch repo
---
# qa scratch repo

Seeds `qa-scratch/`, a small git repository of its own under the checkout. Its git directory is `repo.git`, because a scenario's copy of the checkout leaves out every directory named `.git`, and commands reach it with `GIT_DIR=repo.git`. It holds a one-command book for a `demo` program, a QA plan for it under `art/specs/s1/`, and a `qa.toml` that maps the `demo` tool to `echo`. One commit holds the book, then the source file `src/demo.py` changes without a commit, so the repository carries one changed production unit. Commands run there with `-C qa-scratch` and with `STABLEMATE_ARTIFACTS_DIR` and `STABLEMATE_CONFIG` pointed at the scratch tree, so no spec reaches the artifacts directory of the person who runs the book.

## Steps

### write-qa-book

- kind: seed
- run: rm -rf qa-scratch && mkdir -p qa-scratch/ qa-scratch/art/specs/s1 qa-scratch/docs/features/demo qa-scratch/docs/features/demo/flows qa-scratch/src && printf -- 'qa:\n  tools:\n    - demo\n' > qa-scratch/agents.yml && printf -- '\133qa_tools.demo]\ncommand = "echo"\ndescription = "echoes its arguments"\n' > qa-scratch/qa.toml && printf -- 'art/\nrepo.git/\n' > qa-scratch/.gitignore && printf -- '---\ntype: cli\nslug: cli\ntitle: demo\n---\n# demo\n\nA demo.\n\n- binary: demo\n- code: src/demo.py::greet@137119c5c133\n\n## Commands\n\n### demo-greet\n- usage: demo greet — says hi\n- exits: 0 — always\n- run: invoke(argv=\133"greet"])\n- verify: exit_status(code=0)\n- fixture: none, because nothing is seeded\n- code: src/demo.py::greet@137119c5c133\n- capture: greeting from stdout\n- capture: badcapture\n' > qa-scratch/docs/features/demo/cli.md && printf -- '---\ntype: entries\nslug: entries\ntitle: demo\n---\n\n- \133demo](cli.md)\n- \133Say hello](flows/say-hello.md)\n' > qa-scratch/docs/features/demo/entries.md && printf -- '---\ntype: flow\nslug: say-hello\ntitle: Say hello\n---\n# Say hello\n\n- start: nothing\n- steps:\n  - \133demo greet](../cli.md#demo-greet)\n- end: said\n- fixture: none, because nothing is seeded\n' > qa-scratch/docs/features/demo/flows/say-hello.md && printf -- 'def greet():\n    return "hi"\n\n\ndef farewell():\n    return "bye"\n' > qa-scratch/src/demo.py && printf -- 'from ostler_qa import Qa, plan, scenario, target\n\nplan(run_id="qa-s1", story="s1")\n\ndemo = target("demo", driver="python")\n\nOB = "okf:docs/features/demo/cli.md#demo-greet:exits:1"\n\n\n@scenario(target=demo, mechanism="live", covers=\133OB])\ndef greet_exits_zero(qa: Qa) -> None:\n    """The greeting exits zero."""\n    seen = qa.tool("demo").run("greet")\n    qa.verify("exit_status", seen, code=0, covers=\133OB])\n' > qa-scratch/art/specs/s1/qa_plan.py

### commit-qa-base

- kind: seed
- run: cd qa-scratch && export GIT_DIR=repo.git GIT_WORK_TREE=. && git init -q && git config --unset core.worktree && unset GIT_WORK_TREE && git add -A && git -c user.name=okf -c user.email=okf@example.com commit -q -m base

### change-qa-source

- kind: seed
- run: mkdir -p qa-scratch/src && printf -- 'def greet():\n    return "hello"\n\n\ndef farewell():\n    return "bye"\n' > qa-scratch/src/demo.py

