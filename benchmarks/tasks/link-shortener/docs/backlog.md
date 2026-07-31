# Link shortener backlog

Benchmark worklist for the smoke run. The app is a link shortener with one surface: an
HTTP API that anyone can call. There is no sign-in and no web page — a short link is a
public URL, and keeping it that way is what holds this backlog to three bullets.

Surfaces this app ships:

- **api** — Go service, the only surface, and the only writer of stored data

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope
for decomposition and none may be dropped.

## Shortening and following links

- [link-create] A person submits a long URL and gets back a short link they can share.
- [link-follow] A person opens a short link and arrives at the URL it was created from.
- [link-missing] A person who opens a short link that was never created is told it does not exist, rather than being sent somewhere wrong or seeing a crash.
