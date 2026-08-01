# Link shortener backlog

Benchmark worklist for the smoke run. The app is a link shortener with one surface: an
HTTP API that anyone can call. There is no sign-in and no web page — a short link is a
public URL, and keeping it that way is what holds this backlog to three bullets.

Surfaces this app ships:

- **api** — Go service, the only surface, and the only writer of stored data.
  It listens on **port 18081**, and QA drives it at `http://localhost:18081`.

  This is an environment constraint, not a behavior. The benchmark owns `18080-18099` and
  nothing else; each spec gets its own port so two runs cannot collide either. Left unsaid,
  a Go service takes `8080` — the most contended port on any developer machine — and QA
  then probes whatever already holds it.

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope
for decomposition and none may be dropped.

## Operating constraint

The api listens on port **18080**, not the Go default 8080. This is a property of the
benchmark rather than of the product: the runner shares a machine with whatever else is
on it, and 8080 is the first port anything takes. A run whose service cannot bind spends
its whole budget failing to start, so the port is stated here — where decomposition will
carry it into the stories — instead of being left to a default that collides.

## Shortening and following links

- [link-create] A person submits a long URL and gets back a short link they can share.
- [link-follow] A person opens a short link and arrives at the URL it was created from.
- [link-missing] A person who opens a short link that was never created is told it does not exist, rather than being sent somewhere wrong or seeing a crash.
