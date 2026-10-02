---
name: revise-docs
description: "Revising a document written for readers outside the code, such as a README, an install guide or a user-facing page, in two passes: every checkable claim verified against the source of truth, then every detail the reader does not act on inventoried and cut, with a link left where the material lives elsewhere. Load when asked to make a document truthful, to trim or tighten one, to inventory what it states, or before publishing a document that has drifted from what it describes."
tags: [docs, review]
---

# Revise a document for its readers

A document for readers outside the code drifts two ways. It keeps stating things that
stopped being true, and it collects detail that serves its authors instead of its
readers. Revise in two passes, truth first, because a false sentence is cheaper to cut
than to polish.

## 0. Name the reader

Write one sentence: who opens this document, and what they came to do. Every later
judgement is made against that sentence. When the document serves two readers, such as
a user and a contributor, name both and mark which reader each section serves.

## 1. Truth: verify every checkable claim

**List the claims before checking any.** A claim is checkable when the source of truth
could contradict it:

- a command, flag, path, file name, link or heading anchor the reader would type or
  follow;
- a list of members: "the commands are", "the formats it accepts";
- an absolute: only, never, every, all, no, none;
- a behaviour: what runs when, what a tool reads, where output lands, in what order;
- a fact true on one platform or configuration, stated as universal;
- a number.

**Check each one against the source of truth, never against another document.** Run
the command. Read the code that implements the behaviour. List the directory. Follow the
link to its anchor. Two documents that agree prove only that one copied the other.

**Lists and absolutes go stale first, and each needs its own check.** Check a list by
enumerating the real members and comparing, not by confirming that the listed ones
exist. That catches the member that was added. Check an absolute by searching for a
counterexample.

Give each claim one verdict: true, false, or true only in some case. Rewrite a false
claim to what the source says, or cut it. Narrow a partly true claim to the case where it
holds. A false claim found in another document while checking gets reported, and fixed
in its own change.

Done when every claim on the list has a verdict and names where it was checked.

## 2. Necessity: inventory what the reader does not act on

Go through the document passage by passage and ask whether the reader from step 0 acts
on it. These kinds of detail fail that test:

| Kind | What it looks like | What to do |
|---|---|---|
| Duplicate | another document the reader can reach says the same thing | keep a one-line rule and a link |
| Internals | how a component works inside, when the reader needs only what to do | cut |
| Internal address | a function, module, class or line number where the rule itself would do | keep the rule, link the file if the reader must look |
| Author rationale | why the design is this way, written for someone changing it | move it to the contributor document, or cut it if that document already says it |
| Hypothetical | what would happen if the reader did something nobody does | cut |
| Repeated aside | the same point made in two sections | keep the one in the section about it |
| Out of place | true and useful, but about another subject than its section | move it to the section it is about, or cut it |

**Inventory before cutting.** List each item with its line range, grouped by kind, and
name its destination: cut, link or move. When someone else owns the document, show the
inventory and wait for agreement before cutting.

Then cut. Every item that leaves a topic the reader still needs leaves a link in its
place, pointing at the document that now carries it.

Done when every inventoried item is cut, moved, or kept with a stated reason.

## 3. Close

- **Re-verify what you wrote.** A revision adds claims too. Run step 1 on every sentence
  the revision introduced.
- **Search for inbound links** to every heading you removed or renamed, across the whole
  repository.
- **Keep the passes apart.** The truth fixes and the cuts land as separate changes,
  because a reviewer asks different questions of each: "is this now correct?" and "did
  the reader need this?".
