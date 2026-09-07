---
type: concept
slug: pyflow-activity-label-selection
title: Pyflow activity label documentation
---
# Pyflow activity label documentation

`ActivityLog` is the one implementation for Pyflow activity labels: a flagged log record
supplies the sticky activity text while the filter preserves every log record. The source
contrasts this mechanism with the YAML engine's per-node `activity:` field, rather than
offering either as a replacement for the other.

[Activity labels from flagged logs](activity-labels.md) describes the tracker, installation,
and label lifecycle. [pyflow activity labels](pyflow-activity.md) records its fields and public
methods. Both document the same current `ActivityLog`; the source provides no deprecation,
migration, or preference between them.

- rule: use either linked description for its stated documentation context; neither is a preferred or deprecated ActivityLog implementation
