---
type: fixture
slug: book-scratch-repo
title: book scratch repo
---
# book scratch repo

Seeds `book-scratch/`, a small repo of its own under the checkout: one source file with two
functions, a Go and a TypeScript source file with one function each, a `demo` book that cites one of
them (a cli page, a flow and an entries page), and a source inventory that lists both functions. It
also seeds `book-scratch-broken/`, a repo whose entries page links to a page that does not exist.
Commands run there with `-C book-scratch`, so no other scenario reads these files.

## Steps

### write-scratch-source

- kind: seed
- run: mkdir -p book-scratch/src book-scratch/docs/features/demo/flows && printf 'def greet():\n    return "hi"\n\n\ndef farewell():\n    return "bye"\n' > book-scratch/src/demo.py

### write-scratch-other-sources

- kind: seed
- run: mkdir -p book-scratch/src && printf -- 'package main\n\nfunc Greet(name string) string {\n\tif name == "" {\n\t\tpanic("no name")\n\t}\n\treturn "hello " + name\n}\n' > book-scratch/src/greet.go && printf -- 'export function greet(name: string): string {\n  if (!name) {\n    throw new Error("no name");\n  }\n  return "hello " + name;\n}\n' > book-scratch/src/greet.ts

### write-scratch-entries

- kind: seed
- run: printf -- '---\ntype: entries\nslug: entries\ntitle: demo\n---\n\n- \133demo](cli.md)\n- \133Say hello](flows/say-hello.md)\n' > book-scratch/docs/features/demo/entries.md

### write-scratch-cli

- kind: seed
- run: printf -- '---\ntype: cli\nslug: cli\ntitle: demo\n---\n# demo\n\nA demo.\n\n- binary: demo\n- code: src/demo.py::greet\n\n## Commands\n\n### demo-greet\n- usage: demo greet — says hi\n- exits: 0 — always\n- run: invoke(argv=\133"greet"])\n- verify: exit_status(code=0)\n- fixture: none, because nothing is seeded\n- code: src/demo.py::greet\n' > book-scratch/docs/features/demo/cli.md

### write-scratch-flow

- kind: seed
- run: printf -- '---\ntype: flow\nslug: say-hello\ntitle: Say hello\n---\n# Say hello\n\n- start: nothing\n- steps:\n  - \133demo greet](../cli.md#demo-greet)\n- end: said\n- fixture: none, because nothing is seeded\n' > book-scratch/docs/features/demo/flows/say-hello.md

### write-scratch-inventory

- kind: seed
- run: printf '{"units":\133{"kind":"symbol","path":"src/demo.py","symbol":"greet","code":"src/demo.py::greet"},{"kind":"symbol","path":"src/demo.py","symbol":"farewell","code":"src/demo.py::farewell"}]}' > book-scratch/inventory.json

### write-broken-book

- kind: seed
- run: mkdir -p book-scratch-broken/docs/features/demo && printf -- '---\ntype: entries\nslug: entries\ntitle: demo\n---\n\n- \133Missing page](missing.md)\n' > book-scratch-broken/docs/features/demo/entries.md
