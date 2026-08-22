---
type: concept
slug: deploy-identity
title: The deploy identity
---
# The deploy identity

- code: pulumi/identity.go
- extends:
- consistency: deploy-identity — the deploy identity's only grant is a bucket-level grant on the artifact store,
  naming an object-level role.
- consistency: deploy-identity — no project-level role is granted to the deploy identity anywhere in the plan.
- consistency: deploy-token — the deploy token reaches the secret version as a secret value, so the plan
  reports it as `[secret]` rather than as the token itself.

One service account publishes artifacts, and it is the only identity in the stack that writes. What
makes it safe to hand to a pipeline is not that it exists but what it does *not* hold: the account
is granted on the [artifact bucket](artifact-store.md) and nowhere else, so a token minted for it
opens exactly one thing.

The deploy token it authenticates with is a secret in the stack's configuration, and the program
passes it through as one. A secret that appears in a plan is a secret in every review, every CI
log and every state file that plan touched.
