---
type: concept
slug: artifact-store
title: The artifact store
---
# The artifact store

- code: pulumi/bucket.go
- extends:
- consistency: artifact-bucket — the plan turns uniform bucket-level access on for the artifact bucket, so an
  object's access is decided by the bucket's IAM policy alone.
- consistency: artifact-bucket — the plan declares the artifact bucket with force-destroy off, so destroying the
  stack cannot take the published artifacts with it.
- consistency: artifact-bucket — the plan keeps object versioning on for the artifact bucket.
- consistency: artifact-bucket — the readers binding on the artifact bucket lists exactly the build group.
- consistency: artifact-bucket — no member of that binding is `allUsers` or `allAuthenticatedUsers` — the
  artifact store is not public, and no plan may make it so.

One bucket holds every artifact the depot keeps, and one binding says who may read it. Both are
declared here rather than granted later by hand, because a grant made outside the program is a
grant the plan cannot show and the next preview will not remove.

The bucket is readable by the build group and by nobody else. "Nobody else" is the load-bearing
half: a reader added to this binding is a reader of every artifact ever published, and the members
list is the only place that is visible before it is true.

Every one of those is stated by the program rather than left to the provider's default, so a
preview shows the value the depot chose and not the value it happened to inherit.
