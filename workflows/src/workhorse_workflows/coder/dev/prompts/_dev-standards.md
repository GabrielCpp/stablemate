## Standards

Load the coding standards that govern each file at the moment you edit it, and tell each
writing seat to do the same. The repo advertises them through its own instruction files and
each skill's frontmatter. A service can mix languages, so the binding standard is a property
of the file. Load a layer's testing skill before its tests are written, and follow it over
this prompt where they differ.

A component that consumes an external contract tests against a captured real payload, not
a shape written by hand. A fixture you invent can encode the same wrong assumption as the
code.

When generated code depends on an input you changed (an API spec, a client, mocks), run the
generation command before writing code that uses it. Generated client code is app code: fix
its inputs or its generation, never exclude it from analysis.

## Branch

{% if branch %}
Every code repo you change must be on `{{ workhorse_var('branch') }}`. Before the first edit
in a repo, check that branch out, or create it from the current HEAD when it does not exist.
The workflow checks each changed repo's branch after the review phase.
{% else %}
Commit in each repo on the branch it is on now. Create no branch and switch none. This run
lands every story on the branches it found.
{% endif %}
