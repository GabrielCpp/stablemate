---
type: milestone
title: Personal todos everywhere
status: approved
---

# Personal todos everywhere

## Outcome

A person keeps their own todo list and reaches it from a web browser or a phone, with the
same list waiting on both. They sign up, add and organise todos, mark them done, find them
again in a long list, and keep working on the phone when the connection drops. Nothing
they do on one device has to be repeated on the other.

The release matters to the benchmark as the verdict run: four surfaces, eighteen journeys
and hours per round. It is the size at which the question "is the workflow good" can be
answered, and every other fixture here is a smaller cut of it.

## Release Boundary

This is one milestone with one gate: a person can complete every journey below on the web
app and on the mobile app against the same account and the same data. Identity, the todo
list and sync must coexist at cutover, because a list that is not tied to an account is
not personal and a list that differs between devices is two lists.

The first story proves the one end-to-end path: a person signs up on the web app, lands in
an empty list, adds a todo by title, and sees it on the phone after signing in there.
Later stories widen that path through organising, finding, offline work and the quality
bar.

## User Journeys

### Sign up with an email and a password

- services: web, app, api

A new person creates an account with an email address and a password, and lands in an
empty todo list. A badly formed email, a password that is too short, or an email already
in use is refused on the form with a message that names the field.

### Sign in and stay signed in

- services: web, app, api

A returning person signs in and stays signed in after closing and reopening the app. A
wrong password is refused with a message that does not say which of the two fields was
wrong.

### Sign out

- services: web, app, api

A signed-in person signs out, and their todos are no longer reachable until they sign in
again. Reopening the app after signing out shows the sign-in screen, not the list.

### Recover a forgotten password

- services: web, app, api

A person who forgot their password requests a reset email and regains access. The request
answers the same way whether or not the address has an account, and following the emailed
link lets the person set a new password and sign in with it.

### See and change the account

- services: web, app, api

A person sees the account they are signed in as, and can change their display name. The
new name shows wherever the app names the person, on both devices.

### Add a todo by title

- services: web, app, api

A person adds a todo by typing a title, and it appears in their list immediately. An empty
title is refused inline. The new todo is open and sits at the top of the list.

### See only your own todos

- services: web, app, api

A person sees all of their own todos, and never anyone else's. Two accounts on the same
device, used one after the other, each see only their own list.

### Mark a todo done and undo it

- services: web, app, api

A person marks a todo done and can undo that. Done todos stay visible but are clearly
distinguished from open ones, by more than colour alone.

### Edit a todo's title or notes

- services: web, app, api

A person opens a todo and changes its title or its longer notes. The change is visible in
the list straight away and on the other device after sync.

### Delete a todo safely

- services: web, app, api

A person deletes a todo and is protected from deleting one by accident, by a confirmation
or an undo window. A deleted todo leaves both devices.

### Give a todo a due date

- services: web, app, api

A person gives a todo a due date, and todos that are past due are called out distinctly
from those that are not. The due date can be cleared.

### Set a priority and order by it

- services: web, app, api

A person marks a todo as high, normal, or low priority and can order the list by it. A
todo with no priority set is normal.

### Group todos into named lists

- services: web, app, api

A person groups todos into named lists, for example Work and Home, and moves a todo
between them. A todo belongs to exactly one list, and a new account starts with one
default list.

### Find a todo by text and filter

- services: web, app, api

A person narrows a long list down by typing text, and by filtering to a list or to open
versus done. The two filters combine, and clearing them restores the whole list. A filter
that matches nothing says so plainly.

### Changes follow the person between devices

- services: web, app, api

A change made on one device shows up on the other without the person doing anything to
force it. A todo added on the web app appears on the phone within a few seconds while the
phone is open, and on next open otherwise.

### Keep working on a phone with no connection

- services: app, api

On a phone with no connection, a person can still read their todos and add or complete
one. Those changes reach the server once the connection returns, and the app shows that
it is offline and that changes are pending.

### Every screen meets the accessibility baseline

- services: web, app

Every screen is fully operable without a mouse, exposes its controls to a screen reader,
and meets contrast requirements. Focus is visible and moves predictably through forms and
lists.

### Every list and form shows its empty, loading and failed states

- services: web, app

Every list and every form tells the person what is happening when it is empty, still
loading, or has failed, and offers a way forward: a prompt to add the first todo, a
progress indicator, or a retry.

## Architecture Decisions

- The api is the only writer of stored data. The web app and the mobile app read and write
  through it and never reach the datastore directly.
- Identity is Firebase Auth. Sign-up, sign-in, sign-out and password reset go through it,
  and the api trusts its tokens. Persistence is Datastore, provisioned by the infra
  surface along with the Firebase project.
- Each todo belongs to one account and one list, and every api route scopes its reads and
  writes to the signed-in account.
- Sync is server-authoritative: the api holds the truth, each client refreshes from it,
  and an offline change on the phone is queued locally and replayed in order when the
  connection returns. A conflict resolves in favour of the latest write.
- Reading the datastore at construction and surviving a restart is code review's
  obligation, because QA cannot cross a process boundary.

## Constraints

- The api is a Go service. The web app is a React Router app. The mobile app is Flutter.
  The infra surface is Datastore for persistence and Firebase Auth for identity.
- A journey that names web and app applies to both front ends, and the api work it implies
  is part of the same journey rather than a separate one.
- Every screen meets the accessibility baseline, so no journey is complete on a screen
  that fails it.
- The web and mobile apps show the signed-in person's display name where they name the
  person.

## Acceptance

The milestone is complete when, against a fresh deployment of the four surfaces:

- A new account signs up on the web app and lands in an empty list; the same credentials
  sign in on the phone and see the same empty list.
- Reopening either app keeps the person signed in; signing out returns to sign-in, and the
  list is unreachable until sign-in.
- A password reset request answers identically for known and unknown addresses, and the
  emailed link sets a new password that then signs in.
- A todo added on the web app appears on the phone without a manual refresh, and one
  completed on the phone shows done on the web app.
- Done, past-due and priority are each visibly distinguished, and the list orders by
  priority on request.
- A todo moves between two named lists and appears only in its current one.
- Typing text and choosing a list or open-versus-done filter narrows the list, and a
  non-matching filter shows a plain message.
- With the phone offline, a todo is read, one is added and one completed; on reconnection
  both changes appear on the web app.
- Every screen passes keyboard-only operation, screen-reader labelling and contrast
  checks, and every list and form shows an empty, loading and failed state.
- A second account never sees the first account's todos on either device.

## Non-Goals

- No sharing of todos or lists between accounts, and no collaboration.
- No reminders, notifications or calendar integration.
- No recurring todos, sub-tasks or attachments.
- No social sign-in providers beyond email and password.
- No desktop app and no public api beyond what the two front ends use.
