story: none
date: 2026-11-17
elements: CheckBook, RunBook, IndexBook

`App(ignore=...)` names 25 modules of `ostler/ostler/book/`. No command a person types reaches them from a text
sandbox, and none of them holds a command, a subcommand or a flag of its own. They are the runtime the plays of other
books run on:

- The surfaces of web, phone, gRPC and signed-credential books: `browser.py`, `pagesurface.py`, `pagedata.py`,
  `listjudge.py`, `screen.py`, `asked.py`, `device.py`, `mobilesurface.py`, `rpc.py`, `proxy.py`, `signed.py` and
  `delivery.py`.
- The definitions every kind of book shares, which `ostler book` loads for the book it reads and never calls on a
  command book: `arrange.py`, `backstage.py`, `boundary.py`, `cast.py`, `contracts.py`, `denied.py`, `entries.py`,
  `errors.py`, `event.py`, `planner.py`, `stack.py`, `surface.py` and `workspace.py`.

The plays of the books that use each surface exercise them: the screen books under the book root drive a browser or a
device through `pagesurface.py`, `browser.py`, `screen.py`, `mobilesurface.py` and `device.py`, the gRPC books through
`rpc.py`, and a book with a Bus or credentials through `delivery.py` and `signed.py`. The ostler book plays a command
book and nothing else, and the `ostler book` commands it plays (`check`, `index`, `search`, `explain`, `decisions`,
`explore`, `run`, `graph`) run only the modules its `source` pointers name.

The ignore lifts when a sandbox can hold a browser, a device, a gRPC server and a bus, or when the book root holds a
second book of ostler's own per surface that these commands run against. Each file then gets an element, and its pattern
leaves `App(ignore=...)`.

`ostler/ostler/api.py` is ignored for the reason in `commands-carry-their-words-in-the-argv.md`: it is the in-process
entry point of workflow nodes, and no command line reaches it.
