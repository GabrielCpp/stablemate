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

The api listens on port **18081**, not the Go default 8080. This is a property of the
benchmark rather than of the product: the runner shares a machine with whatever else is
on it, and 8080 is the first port anything takes. A run whose service cannot bind spends
its whole budget failing to start, so the port is stated here — where decomposition will
carry it into the stories — instead of being left to a default that collides.

It is stated twice, above and here, and the two statements must agree. They did not: this
section read 18080 against the surface block's 18081, which is the whole of the benchmark's
allocation policy contradicting itself in two paragraphs of the same file. The author lane
found it on the first grill and parked the run on it as its opening question — correctly,
since nothing in the document settles which number wins, and a port is exactly the kind of
environment fact a decomposition carries into every story and every QA plan. 18081 is the
allocation (seat-booking holds 18083, policy-desk 18084); 18080 was the single-port text
this file outgrew.

## Shortening and following links

The api is the only surface a bullet may be satisfied on. This is a product decision, not
an omission: [link-create] is reached by calling the api, and a round that ships exactly
that has shipped the whole bullet. It is written down because the alternative reading is
the natural one — "a person submits a long URL" describes something a person does, and a
judge reading it without this line looks for the web page and the mobile screen a person
would do it on, finds neither, and scores a complete round as a third built. The bullets
stay at the observable-behaviour level; what is scoped here is where the behaviour is
observed.

- [link-create] A person calling the api submits a long URL and gets back a short link
  they can share.
- [link-follow] A person opens a short link and arrives at the URL it was created from.
- [link-missing] A person who opens a short link that was never created is told it does not exist, rather than being sent somewhere wrong or seeing a crash.
