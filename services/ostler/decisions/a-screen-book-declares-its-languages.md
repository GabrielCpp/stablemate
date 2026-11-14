story: ostler-book
date: 2026-11-13

A screen book declares its languages in `Service(languages=(...))`, and the tool names none. A label is
`T(<language>=<text>, ...)` with one keyword per declared language, and a bare string is a label that reads the
same in every language. The first language is the one a journey plays in unless it names another, and `check`
refuses a label that misses a declared language or names one the service does not declare.

The label type used to hold an English and a French text. An app with one language had to write every label twice,
and an app in other languages could not be written. A surface that needs a regional browser locale says so once in
`locales`, and with no entry the browser locale is the language name itself.
