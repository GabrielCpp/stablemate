---
type: concept
slug: audit-receipt-field-roles
title: Audit receipt field roles
---
# Audit receipt field roles

`AuditReceipt` declares both `story_digest` and `path`. They are complementary receipt
attributes, not alternative representations: `story_digest` identifies the exact story bytes
that passed the audit, while `path` locates the persisted `audit-receipt.json` artifact. Consumers
that need the proof use the digest; consumers that need to read the artifact use the path. The
schema declares no preferred or deprecated field, so neither field ranks above or replaces the
other.

- code: `workflows/src/workhorse_workflows/author/story_author/schemas.py::AuditReceipt`
- rule: use `story_digest` to identify audited story bytes and `path` to locate the audit receipt; neither substitutes for the other
