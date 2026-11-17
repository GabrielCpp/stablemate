story: none
date: 2026-11-17
elements: CheckBook, IndexBook, SearchBook, ExplainBook, ExplainNothing, ListBookDecisions, ExploreBook, RunBook, DrawBook, EnvCheck, EnvList, EnvRender, EnvRenderUnknown, EnvDown, EnvAddress, EnvExec

`ostler book` and `ostler env` read a book under `services/<name>/`, so the sandbox holds one: `demo`, a command book of
one command (`echo hello`), a notes file, one journey, one decision and a stack of one web container. Its files live in
`demo.py` as text. The book plays the commands that need no browser, device, server or git checkout of the app against it.
`book run` plays the demo book's own journeys, cells and input classes in a second sandbox, so it needs `echo` and the
installed `ostler` on `PATH`, as the outer play does.

The book does not play `book missing`, `stale` and `verified`, which read the tracked files of an app checkout, and the
sandbox is not a git repository. It does not play `book walk`, which arranges a scene on a live service.

`ostler env render` writes the compose file of the shared copy under the home folder, in a folder named after the
sandbox and the copy (`plan-shared`). `env down` removes it and says `tore shared down`, or says `shared is not up` when
nothing was rendered. The refusals of `render` for a book with no stack and of `address` for a copy that is not up are
printed on standard error. `env down` and `env render` read the machine's container tooling, and the book assumes it is
installed, as the play of `env compose` would; `compose`, `up`, `exec` with a stack's secrets and the bring-up of a
checkout are not played.

The refusal of `book explain` for a name the book lacks is printed on standard error too.
