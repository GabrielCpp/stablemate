---
type: concept
slug: dashboard-file-view-renderer
title: Dashboard file view renderer
---
# Dashboard file view renderer

Dashboard file view renderer is the browser-side layer that turns [workspace file content data](../workspace-file-content-data.md) returned by [select files file row](../gui/screens/groom-dashboard.md#select-files-file-row) into the Files pane's `#file-view` DOM. It owns the selected file header, the [dashboard HTML escaper](#method-escape-html) used for that header text, the [dashboard file language resolver](#method-ext-lang) used for optional syntax-highlighting classification, empty-or-binary placeholder, text-only code insertion, and Highlight.js handoff for the [groom dashboard](../gui/screens/groom-dashboard.md) file viewer.

- code: groom/groom/templates/dashboard.html::renderFile

## Contract

- purpose: replace the file viewer with a complete representation of one selected repo-relative path and the raw text body returned for that path.
- input path: required string; displayed as the file header after browser-side HTML escaping and used to choose a syntax-highlighting language.
- input text: required string-like value; falsey values render the empty-or-binary placeholder instead of a code block.
- output: mutates only the `#file-view` DOM subtree; emits no return value, network request, websocket frame, browser navigation, or server-state mutation.
- security: the selected path is text-context escaped before insertion into the header HTML; file content is assigned through text content on a `<code>` element, not inserted as HTML.
- highlighting: when the [dashboard file language resolver](#method-ext-lang) maps the selected path to a Highlight.js language known to the loaded library, the code block receives `language-{lang}` before highlighting; otherwise it remains unclassified for plain rendering or library auto-detection.
- error handling: Highlight.js exceptions are swallowed and leave the code block as plain text; empty, binary, missing, unsafe, and unavailable server responses are represented by the same empty-state message.

## Inputs

### field-path

- type: `str`
- default: none
- required: true
- meaning: repo-relative selected file path from the Files tree row's `data-path`; displayed in `.file-head` and passed to the dashboard file language resolver.

### field-text

- type: `str`
- default: `""`
- required: true
- meaning: raw text body from the workspace file-content response; rendered as literal code text when truthy, otherwise treated as empty or binary content.

## Output

### field-file-view-dom

- type: browser DOM subtree
- default: replaced on every render
- required: true
- meaning: the `#file-view` contents after rendering the selected path, including the header and either an empty-state block or a highlighted code block.

## Methods

### method-render-file

- sig: `renderFile(path, text) -> void`
- abstract: false
- raises: none intentionally surfaced for empty text, unknown extensions, unsupported highlight languages, or Highlight.js rendering failures.
- code: groom/groom/templates/dashboard.html::renderFile

Renders one selected file response into the dashboard Files pane.

#### Effects

- Reads: `#file-view`, selected path, returned text body, the dashboard extension-language map, and the loaded Highlight.js library if present.
- Header rendering: replaces `#file-view` with a new `.file-head` containing the selected path after `groom/groom/templates/dashboard.html::escHtml` converts nullish input to an empty string, stringifies non-nullish input, and serializes it as text-safe HTML.
- Empty branch: when `text` is falsey, appends `.file-body` containing `<div class="fd-empty">(empty or binary file)</div>` and returns without resolving a language or creating code/pre nodes.
- Language branch: when `text` is truthy, calls `groom/groom/templates/dashboard.html::extLang` with the selected path to get an optional Highlight.js language name from the selected file's lowercased basename, exact special filename, or last extension.
- Highlight class: when the resolver returns a non-empty language and Highlight.js reports that language as known, sets the generated `<code>` element's class to `language-{lang}`; an empty resolver result, missing Highlight.js library, or unsupported language leaves the code element without a language class.
- Content insertion: assigns the returned file body to `code.textContent`, so markup-like file contents remain literal text and do not execute or create DOM nodes.
- Highlight attempt: when Highlight.js is loaded, calls its element-highlighting routine inside a guarded block; any thrown error is ignored and the already-created text code block remains visible.
- Final DOM: appends `<pre class="file-pre hljs"><code>...</code></pre>` inside `.file-body`, then appends `.file-body` to `#file-view` after the header.
- Calls: `groom/groom/templates/dashboard.html::escHtml` for the displayed path and `groom/groom/templates/dashboard.html::extLang` for language selection; both are first-party dashboard-template layers for the crawl to document separately.
- Does not mutate: selected repository state, selected file-row active class, files tree contents, selected worker state, inbox rows, detail pane, diff pane, status bar, command palette, websocket connection, browser URL, workflow registry, sidecar state, Docker state, or workspace files.

### method-ext-lang

- sig: `extLang(path) -> string`
- abstract: false
- raises: none intentionally surfaced for supported mapped names, unmapped extensions, extensionless paths, or paths containing directories.
- code: groom/groom/templates/dashboard.html::extLang

Resolves a selected file path into the optional Highlight.js language name that the file renderer may apply to the generated code block.

#### Contract

- Input: accepts the repo-relative selected file path used by the Files panel; callers are expected to pass a string path.
- Basename handling: discards any directory prefix by splitting on `/` and taking the last segment, then lowercases that basename before matching so extension and special-name lookup are case-insensitive.
- Special filenames: returns `dockerfile` for a basename exactly equal to `dockerfile`, and `makefile` for a basename exactly equal to `makefile`, before extension parsing.
- Extension parsing: finds the last `.` in the basename; when the dot is after the first character, the substring after that dot is the extension key, otherwise the extension key is empty.
- Output: returns a Highlight.js language name string for mapped extensions and special filenames, or the empty string when no mapping applies.
- Consumer contract: the returned string is only a language candidate; [render file](#method-render-file) still checks whether the loaded Highlight.js library recognizes it before adding a `language-{lang}` class.
- DOM/network effects: reads only the path value and the dashboard's extension-language map; it does not mutate DOM, issue requests, send websocket messages, write storage, change selected repository state, or navigate.
- Dependencies: calls no first-party groom symbols, and otherwise uses only browser language string and array operations; this layer bottoms out for the first-party crawl.

#### Language Map

- JavaScript: `js`, `mjs`, `cjs`, and `jsx` map to `javascript`.
- TypeScript: `ts` and `tsx` map to `typescript`.
- Python: `py` maps to `python`.
- Ruby: `rb` maps to `ruby`.
- Go: `go` maps to `go`.
- Rust: `rs` maps to `rust`.
- Java and Kotlin: `java` maps to `java`; `kt` maps to `kotlin`.
- C and C++: `c` and `h` map to `c`; `cpp`, `cc`, and `hpp` map to `cpp`.
- C sharp: `cs` maps to `csharp`.
- PHP: `php` maps to `php`.
- Swift: `swift` maps to `swift`.
- Scala: `scala` maps to `scala`.
- Shell: `sh`, `bash`, and `zsh` map to `bash`.
- YAML: `yml` and `yaml` map to `yaml`.
- JSON: `json` maps to `json`.
- TOML and INI: `toml`, `ini`, and `cfg` map to `ini`.
- Markdown: `md` and `markdown` map to `markdown`.
- XML-family markup: `html`, `xml`, `svg`, and `vue` map to `xml`.
- Stylesheets: `css` maps to `css`, `scss` maps to `scss`, and `less` maps to `less`.
- SQL: `sql` maps to `sql`.
- Lua: `lua` maps to `lua`.
- Perl: `pl` maps to `perl`.
- R: `r` maps to `r`.
- Dart: `dart` maps to `dart`.
- Special basenames: `dockerfile` maps to `dockerfile`; `makefile` maps to `makefile`.

### method-escape-html

- sig: `escHtml(s) -> string`
- abstract: false
- raises: none intentionally surfaced for nullish input, non-string input, empty strings, or markup-like text.
- code: groom/groom/templates/dashboard.html::escHtml

Converts an arbitrary value into HTML text markup that can be concatenated into a dashboard HTML string where the caller needs visible text rather than parsed markup.

#### Contract

- Input: accepts any value; `null` and `undefined` are treated as `""`, and every other value is converted with the browser string conversion used for display text.
- Output: returns a string containing the browser's HTML serialization of that display text, so characters that would otherwise create elements or entities are represented as literal text when parsed back through `innerHTML`.
- Text-context guarantee: a caller that places the result between tags receives visible text equivalent to the original value, with no script execution and no caller-controlled HTML nodes created from the value.
- Attribute-context limitation: the result is not specified as a quoted-attribute encoder; callers that place it inside an HTML attribute must not rely on it as a complete attribute-safety contract for quote characters.
- DOM effects: creates only a transient detached element for serialization; it does not append nodes, alter visible DOM, update dashboard state, issue network requests, write storage, or send websocket messages.
- Dependencies: uses browser DOM text serialization and language-level string conversion only; it calls no first-party groom symbols, so this layer bottoms out for the first-party crawl.
