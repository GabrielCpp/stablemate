---
type: concept
slug: okf-builder-workflow-entry-point
title: OKF-builder workflow entry point
---
# OKF-builder workflow entry point

The registry is the composition root for the OKF-builder distribution: it names the
package, registers the shared blueprint, and makes the `audit` and `walkthrough-web`
flows available alongside the default `OkfBuilder` flow. `main` is not a competing
composition path; it converts that registry's default entry point into the callable
the installed `workhorse-okf-builder` console script invokes.

The command-selection and composition-root concepts describe different contexts of
the same source. Reach for the composition-root concept to understand which flows and
shared configuration the registry owns. Reach for command selection to understand the
operational purpose of invoking a registered flow or inspecting the command surface.
Neither concept supersedes the other.

- rule: use the registry composition-root description for flow registration and package-level configuration, and the command-selection description for operational command choice; `main` is the adapter between the registry entry point and the installed console script
