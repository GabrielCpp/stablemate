---
type: flow
title: Answer the inbox
---
# Answer the inbox

An operator checks what a run is asking, answers the outstanding message, and reads the inbox back
to confirm the answer landed. A reply to an unknown id, or with no text, is refused and leaves the
inbox as it was. A second reply to a message replaces the first. The run picks the reply up from
its inbox file, as the [operator inbox](../concepts/operator-inbox.md) page describes.

- steps:
  - [inbox](../workhorse.md#inbox)
  - [read-empty-inbox](../workhorse.md#read-empty-inbox)
  - [read-all-empty-inbox](../workhorse.md#read-all-empty-inbox)
  - [read-all-replied](../workhorse.md#read-all-replied)
  - [refuse-reply-without-text](../workhorse.md#refuse-reply-without-text)
  - [refuse-unknown-message](../workhorse.md#refuse-unknown-message)
  - [refuse-unknown-inbox-run](../workhorse.md#refuse-unknown-inbox-run)
  - [refuse-unknown-inbox-action](../workhorse.md#refuse-unknown-inbox-action)
  - [read-outstanding](../workhorse.md#read-outstanding)
  - [reply-to-message](../workhorse.md#reply-to-message)
  - [read-all-messages](../workhorse.md#read-all-messages)
  - [replace-reply](../workhorse.md#replace-reply)
  - [read-replaced-reply](../workhorse.md#read-replaced-reply)
- fixture: inbox-run dir=answer
- end: the formerly outstanding message shows its reply
- verify: stdout(matches="m1. 2026-01-01T00:00:00[+]00:00 [(]replied ")
- detail: [operator inbox](../concepts/operator-inbox.md)
