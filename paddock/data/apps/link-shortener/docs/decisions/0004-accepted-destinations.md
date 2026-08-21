# A destination must be an absolute http or https URL

**Status:** decided
**Applies to:** [link-create] — validation of the submitted destination

## The question

Which submitted destinations does the service accept, and what does a caller observe when
one is refused?

## The ruling

A destination is valid when it is an absolute URL with an `http` or `https` scheme and a
non-empty host.

Everything else — a relative path, a missing or empty `url` field, a `javascript:` or
`file:` scheme, a malformed URL — is refused with `400 Bad Request` and a JSON body
`{"title": "..."}` naming the reason.

## Why

The scheme restriction is part of the decision rather than an implementation detail. A
public redirector that will emit any scheme is a redirect gadget, and [link-create] says
the short link is meant to be shared — so what it may point at is a product question, not
a hardening afterthought.
