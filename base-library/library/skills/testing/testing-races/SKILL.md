---
name: testing-races
description: "Races between two writers of one record: spotting one, naming the interleaving, fixing it at the cause, proving the fix. Load when a test, play or scenario fails only some of the time, when code has two writers of the same record, or when a call is refused because the record changed."
tags: [standards, tests]
---

# Races

A race is two actors touching one record in an order nobody chose. It fails in some runs and passes
in others, so a green run proves nothing about it.

- **Spot it.** A failure that comes and goes is a race until shown otherwise. Rerun the failing
  case N times, and in parallel, before touching code. Call nothing a flake and rerun until green.
- **Name the interleaving.** Write down the two actors and the order that breaks: who read, who
  wrote between, who wrote last. A fix with no named interleaving is a guess.
- **Fix it in the app you own, at the cause.** Make the write atomic or conditional: compare-and-set
  on a version, a transaction, a single writer, an idempotency key. Or make the refusal part of the
  contract, with a documented retry signal, and retry in the app's own internal clients. A sleep, a
  longer timeout or a retry in the test hides the race and leaves it in the product.
- **For an app you do not own,** obey its documented retry signal and nothing else. Report any
  other race as a finding. For a book, the rule is in the `ostler-book` skill, under "A call the app
  asks to send again".
- **Prove it.** Write a test that forces the interleaving, with a hook or a barrier between the read
  and the write. When no forcing is possible, repeat the case a stated number of times under
  parallel load. Show the test fails with the guard removed, then passes with it back.
