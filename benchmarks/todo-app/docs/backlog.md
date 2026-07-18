# Todo app backlog

Benchmark worklist for the greenfield author→coder loop. The app is a personal todo
manager that a single user reaches from either a web browser or a phone, with their
data following them between the two.

Surfaces this app ships:

- **api** — Go service, the only writer of stored data
- **web** — React Router web app
- **app** — Flutter mobile app
- **infra** — Datastore for persistence, Firebase Auth for identity

Bullets are user-observable behavior, not implementation tasks. Every bullet is in
scope for decomposition and none may be dropped. Where a bullet names no surface it
applies to **both** web and mobile, and the API work it implies is part of it.

## Accounts and identity

- [auth-sign-up] A new person creates an account with an email address and a password, and lands in an empty todo list.
- [auth-sign-in] A returning person signs in and stays signed in after closing and reopening the app.
- [auth-sign-out] A signed-in person signs out, and their todos are no longer reachable until they sign in again.
- [auth-recover] A person who forgot their password requests a reset email and regains access.
- [account-profile] A person sees the account they are signed in as, and can change their display name.

## Working with todos

- [todo-create] A person adds a todo by typing a title, and it appears in their list immediately.
- [todo-list] A person sees all of their own todos, and never anyone else's.
- [todo-complete] A person marks a todo done and can undo that; done todos stay visible but are clearly distinguished from open ones.
- [todo-edit] A person opens a todo and changes its title or its longer notes.
- [todo-delete] A person deletes a todo and is protected from deleting one by accident.

## Organising a growing list

- [todo-due-date] A person gives a todo a due date, and todos that are past due are called out distinctly from those that are not.
- [todo-priority] A person marks a todo as high, normal, or low priority and can order the list by it.
- [todo-lists] A person groups todos into named lists (for example Work and Home) and moves a todo between them.
- [todo-search] A person narrows a long list down by typing text, and by filtering to a list or to open-versus-done.

## Following the person between devices

- [cross-device-sync] A change made on one device shows up on the other without the person doing anything to force it.
- [mobile-offline] On a phone with no connection, a person can still read their todos and add or complete one; those changes reach the server once the connection returns.

## Quality bar every screen must meet

- [a11y-baseline] Every screen is fully operable without a mouse, exposes its controls to a screen reader, and meets contrast requirements.
- [empty-loading-error-states] Every list and every form tells the person what is happening when it is empty, still loading, or has failed, and offers a way forward.
