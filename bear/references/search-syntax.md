# Bear search syntax

Use `list` for browsing without a query and `search` when Bear's query language is needed. Use `search-in` only after resolving one note; it finds exact, case-insensitive occurrences in the note body and recognized attachment text.

## Query building blocks

- Write bare keywords to require text terms.
- Wrap an exact phrase in double quotes: `"project status"`.
- Join alternatives with `or`: `recipe or errands`.
- Prefix a term, phrase, tag, or special search with `-` to exclude it.
- Search a tag and its nested children with `#tag`.
- Search only the exact tag, not children, with `!#tag`.
- Search only subtags beneath a tag with `#*/tag`.
- Search modified dates with `@today`, `@yesterday`, `@last7days`, `@date(2026-07-28)`, `@date(<2026-07-28)`, or `@date(>2026-07-28)`.
- Search created dates with `@ctoday`, `@created7days`, `@cdate(2026-07-28)`, or corresponding `<` and `>` comparisons.
- Find notes with incomplete tasks using `@todo`, all tasks complete using `@done`, or any task using `@task`.
- Find tagged or untagged notes with `@tagged` or `@untagged`.
- Add `@title` to restrict text terms to note titles.
- Find globally pinned notes with `@pinned`.
- Find content types with `@images`, `@files`, `@attachments`, or `@code`.
- Find note states with `@locked`, `@readonly`, `@empty`, or `@untitled`.
- Find notes containing wikilinks or explicit backlinks with `@wikilinks` or `@backlinks`.
- Add `@ocr` to search recognized text in images and PDFs. OCR search requires Bear Pro.

Combine compatible terms freely:

```bash
bearcli search '@today @todo "project status"' --format json
bearcli search '#work -#work/archive meeting' --fields id,title,tags,matches
bearcli search 'recipe or errands @untagged @attachments' --location all --format json
```

Use `--query` instead of the positional query when the query begins with `-`, so it is not parsed as an option:

```bash
bearcli search --query '-broccoli' --format json
```

## Result control

- Use `--location notes|trash|archive|all`; the default is `notes`.
- Use `--sort` with comma-separated `pinned`, `modified`, `created`, or `title`, plus optional `:asc` or `:desc`.
- Use `--limit` and `--offset` for bounded pagination. `--limit 0` returns only the match count without note bodies.
- Use `--count` when only the total is needed.
- Use `--fields` to request needed fields; `--fields all` still excludes content unless `content` is added explicitly.
- Prefer `--format json` for structured processing. TSV is the default.
- Treat no matches as success: JSON returns `[]`, and TSV emits a message on stderr with exit code `0`.

Browse and inspect with focused commands:

```bash
bearcli list --sort pinned,modified --limit 20 --format json --fields id,title,tags,modified,pins
bearcli show <note-id> --format json --fields all
bearcli cat <note-id>
bearcli search-in <note-id> --string "TODO" --section "## Tasks" --format json
```

See Bear's official [search documentation](https://bear.app/faq/how-to-search-notes-in-bear/) and confirm current CLI options with `bearcli help search`.
