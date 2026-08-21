# An uncreated key answers 404 Not Found

**Status:** decided
**Applies to:** [link-missing] — `GET /<key>` for a key that was never created

## The question

A caller follows a short link that does not exist. What status does the api answer with,
and what is in the body?

## The ruling

`404 Not Found`, with a JSON body `{"title": "Not Found"}`.

Not a redirect, and not a 500.

## Why

[link-missing] exists to rule out exactly those two outcomes: an unknown key that redirects
somewhere is worse than useless, and one that crashes the process is the failure the bullet
was written to catch. Naming the status and the body shape here is what makes the bullet
checkable — "reports an unknown short link" is otherwise satisfied by anything that is not a
redirect.

The body matches the refusal shape [[0004-accepted-destinations]] already uses for a
rejected `POST`, so a caller parses one error shape and not two. Because nothing expires
([[0005-links-are-durable-and-never-expire]]), this is the *only* not-found case there is.
