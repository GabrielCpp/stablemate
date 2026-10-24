---
type: milestone
title: Keep saved pages
status: approved
---

# Keep saved pages

## Outcome

A person keeps a personal list of web pages worth returning to, reached from a browser.
They save a page by its address and a title, see everything they have saved with the most
recent first, open any of them, remove the ones they no longer want, and find one in a
long list by typing part of its title.

The release matters to the benchmark because every journey needs both surfaces: the screen
a person uses and the api work behind it are one journey, not two. A journey that one
surface could deliver alone would not belong here.

## Release Boundary

This is one milestone with one gate: the web app at `http://localhost:18092`, backed by
the api at `http://localhost:18082`, answers all four journeys end to end. Saving and
listing must coexist at cutover, because a page saved into a list nobody can see is not
kept.

The first story proves the one end-to-end path: a person saves a page on the web app and
sees it appear in the list, with the api storing it. Later stories widen that path through
opening, removing and searching.

## User Journeys

### Save a page by address and title

- services: web, api

A person saves a page by giving its address and a title, and it appears in their list
straight away. The web app offers a form with the two fields, submits it to the api, and
shows the new entry at the top of the list without a reload. An address that is not an
absolute `http` or `https` URL, or an empty title, is refused on the page with a message
that says which field is wrong, and the api refuses the same input with a reason.

### See every saved page and open one

- services: web, api

A person sees every page they have saved, most recently saved first, and can open one.
Opening follows the saved address in the browser. An empty list says plainly that nothing
has been saved yet and points at the form.

### Remove a saved page safely

- services: web, api

A person removes a saved page and is protected from removing one by accident. Removing
asks for confirmation before anything is deleted, and the entry leaves the list only once
the api has removed it. Removing a page that is already gone leaves the list consistent
rather than failing.

### Find a page by part of its title

- services: web, api

A person narrows a long list down by typing part of a title, and is told plainly when
nothing matches. Matching is case-insensitive on any part of the title. Clearing the typed
text restores the whole list.

## Architecture Decisions

- The api is the only writer of stored data, and the web app is the only surface a person
  sees. The web app reaches the api over HTTP at `http://localhost:18082`.
- Saved pages are ordered by the time the api recorded them, newest first, and the api
  owns that ordering rather than the page sorting client side.
- Stored data survives the request that wrote it: the api keeps its data in a durable store
  of the implementing lane's choice, and reading the store at construction is code review's
  obligation, because QA cannot cross a process boundary.
- Search is served by the api, so the list a person sees after typing is the same list a
  second browser would see.

## Constraints

- The api is a Go service listening on port 18082, and QA drives it at
  `http://localhost:18082`.
- The web app is a React Router app serving on port 18092, and QA drives it at
  `http://localhost:18092`.
- The ports are an environment constraint, not a behaviour. The benchmark owns 18080 to
  18099 and nothing else. Left unsaid, each stack takes its language's default, 8080 for
  Go and 3000 for React Router, the two most contended ports on any developer machine.
- The api serves `GET /healthz`, which answers 200 once the api can serve requests, and QA
  waits on it before driving either surface.
- Every screen is operable without a mouse and exposes its controls to a screen reader.

## Acceptance

The milestone is complete when, against a freshly started api and web app:

- `GET /healthz` on the api answers 200 and the web app's list page renders.
- Submitting a valid address and title on the web app shows the entry at the top of the
  list, and the api lists it.
- Submitting an invalid address or an empty title shows a field-level message and the api
  refuses the same input.
- Two pages saved in sequence list most recent first on the page and in the api.
- Opening an entry follows its address.
- Removing an entry asks for confirmation, and after confirming the entry is gone from the
  page and from the api.
- Typing part of a title shows only matching entries, a non-matching term shows a plain
  "nothing matches" message, and clearing the term restores the list.

## Non-Goals

- No sign-in, accounts or per-person lists beyond the one list this app keeps.
- No tags, folders or notes on a saved page.
- No editing of a saved page's address or title.
- No mobile app and no browser extension.
- No fetching of the saved page's content, title or favicon.
