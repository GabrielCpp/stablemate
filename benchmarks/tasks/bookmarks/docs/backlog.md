# Bookmarks backlog

Benchmark worklist for the cross-surface run. The app keeps a personal list of saved web
pages that a person reaches from a browser. Every bullet here needs both surfaces to be
satisfied — that is the point of the spec, so a bullet that one surface could deliver
alone would not belong in it.

Surfaces this app ships:

- **api** — Go service, the only writer of stored data.
  It listens on **port 18082**, and QA drives it at `http://localhost:18082`.
- **web** — React Router web app, the only surface a person sees.
  It serves on **port 18092**, and QA drives it at `http://localhost:18092`; it reaches the
  api at `http://localhost:18082`.

These ports are an environment constraint, not a behavior. The benchmark owns `18080-18099`
and nothing else; each spec and surface gets its own so two runs cannot collide either.
Left unsaid, each stack takes its language's default — `8080` for Go, `3000` for React
Router — which are the two most contended ports on any developer machine, and QA then
probes whatever already holds them instead of this app.

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope
for decomposition and none may be dropped. Each one applies to both surfaces: the screen
a person uses and the API work behind it are one bullet, not two.

## Saving pages

- [bookmark-save] A person saves a page by giving its address and a title, and it appears in their list straight away.
- [bookmark-list] A person sees every page they have saved, most recently saved first, and can open one.

## Keeping the list usable

- [bookmark-remove] A person removes a saved page and is protected from removing one by accident.
- [bookmark-search] A person narrows a long list down by typing part of a title, and is told plainly when nothing matches.
