# Docs app backlog

Benchmark worklist for the design run. The app is a small multi-user documentation site:
people sign in, browse a tree of pages, and edit them. It ships in English and French.

Surfaces this app ships:

- **api** — Go service, the only writer of stored data. It listens on **port 18085**, and
  QA drives it at `http://localhost:18085`.
- **web** — React Router app, the only surface a person touches. It listens on
  **port 18093**.

  The ports are an environment constraint, not a behavior: the benchmark owns
  `18080-18099` and nothing else, and a surface that names no port gets the language's
  idiomatic default — `8080` and `3000`, the two most contended ports on any developer
  machine. `suites/README.md` records who holds which number.

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope
for decomposition and none may be dropped.

**This backlog is deliberately written the way a stakeholder writes one** — it names the
features someone would think to name. It is not a specification, and completing exactly
these sentences is not the same as designing an app a person can operate. Do not treat
the list as exhaustive.

## Getting in

- [account-signin] A person signs in with an email address and a password, and the app remembers them across page loads.

## The pages

- [page-tree] A person sees the site's pages as a tree, with pages nested under other pages.
- [page-create] A person creates a new page, gives it a title, and chooses where it sits in the tree.
- [page-edit] A person edits a page's text and saves it, and the saved text is what everyone sees afterwards.

## Languages

- [page-locales] A page can be written in both English and French, and a person reads it in whichever of the two they are using.
