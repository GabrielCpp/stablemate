# The api is the only surface

**Status:** decided
**Applies to:** every bullet in the link-shortener backlog, decomposition, and judging

## The question

The bullets are written as things a person does — "a person submits a long URL", "a person
opens a short link". Does satisfying one require a web page or a mobile screen for the
person to do it on, or is calling the api enough?

## The ruling

The api is the only surface. A round that implements the three bullets on the api has
implemented them completely. There is no web page and no mobile app that could be missing,
and none may be scaffolded to satisfy a bullet.

## Why

The alternative reading is the natural one, which is exactly why it is written down: a
reader who takes "a person submits a long URL" at face value looks for the screen a person
would submit it on, finds none, and scores a complete round as a third built. The bullets
stay at the observable-behaviour level on purpose; what is settled here is where that
behaviour is observed. Keeping the app to one public, unauthenticated surface is also what
holds the backlog to three bullets.
