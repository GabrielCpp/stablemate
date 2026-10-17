---
type: spec.executive
---

# Executive Summary: Publish Artifacts to a Bucket Only the Build Group Reads

Declares the depot's first and only storage: one bucket for published artifacts, with the
safeties stated rather than inherited, and one binding naming who may read it.

The criterion worth reading twice is that nothing here runs, so nothing here can be exercised.
There is no request to make and no response to read: the program's entire observable behaviour
is the plan `pulumi preview` writes, and every rule this story ships is a property of that
document. A bucket that is world-readable serves no differently from one that is not — it is
not a wrong answer to a request, it is a correct plan with one extra member in a list.

That is also why the safeties are written out. Uniform bucket-level access, object versioning
and force-destroy are all stated by the program even where the provider's default already
agrees, so that the plan shows the value the depot chose and not the value it happened to
inherit — a default that moves under an unpinned provider moves silently, and a plan that
never mentioned it has nothing to compare against.

One Go program, no service, no credential. See `plan.md` for the implementation shape and
`plan-context.json` for the machine-readable service manifest.
