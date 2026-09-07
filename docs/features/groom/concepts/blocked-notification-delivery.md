---
type: concept
slug: blocked-notification-delivery
title: Blocked notification delivery
---
# Blocked notification delivery

A blocked-work `notify` frame has two current, complementary delivery paths. The dashboard
always appends its in-page blocked toast, which is the operator-visible notification even in
browsers without the Notification API or with permission unset or denied. When the browser
exposes the API and reports granted permission, the same handler also creates a system
notification using the same message body. The system notification augments rather than replaces
the toast, so neither path is deprecated and there is no single winner to select.

- code: groom/groom/assets/dashboard.js::onNotify
- rule: use the in-page toast for every blocked-work notification; add the browser system notification only when the Notification API is available and permission is granted
