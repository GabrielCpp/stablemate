---
type: concept
slug: layout-storage-locations
title: Layout storage locations
---
# Layout storage locations

`Layout` names locations by the lifetime and ownership of their contents, not as
interchangeable path choices. `claude_home` is the persistent writable volume for Claude
state. `workspace` and `runs` are writable roots for materialized repositories and run
artifacts. `settings_src`, `credentials_src`, and `observer_src` are optional read-only
operator mounts. `live_root` holds container-local staged source generations, while
`image_workhorse` is the checkout baked into the image for the observer's editable
environment.

Choose the field matching the data's ownership and lifetime. The fields are all current
and are used together by the supervisor; none supersedes or ranks above another.

- rule: select the location by whether its data is persistent Claude state, a writable run root, an optional operator mount, container-local staged source, or the image checkout
