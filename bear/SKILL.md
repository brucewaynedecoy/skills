---
name: bear
description: Operate the macOS Bear app through the official bearcli command-line tool. Use when asked to search, read, create, edit, organize, tag, pin, archive, restore, trash, extract, or open Bear notes; manage Bear attachments; inspect the active Bear selection; or prepare notes for export.
---

# Bear CLI

Use Bear's official macOS CLI directly. Do not route this skill through a Bear MCP server.

## Discover the command

1. Run `command -v bearcli`.
2. Use the returned `bearcli` when it is on `PATH`; otherwise try `/Applications/Bear.app/Contents/MacOS/bearcli`.
3. If neither works, report that Bear 2.8 or later is required. Do not install anything automatically.
4. Never download or install Bear Claw.
5. Run `bearcli help <subcommand>` before an unfamiliar or version-sensitive operation. Use `bearcli help all` for the live full reference.

Examples below use `bearcli`; substitute the application-bundle path when necessary.

## Choose the narrowest read

- Use `bearcli list` to browse notes without a search query.
- Use `bearcli search` for Bear search syntax. Read [references/search-syntax.md](references/search-syntax.md) before composing an advanced query.
- Use `bearcli search-in` for exact, case-insensitive text occurrences within one note and its attachments.
- Use `bearcli show` for structured note metadata.
- Use raw `bearcli cat` output when only Bear Markdown content is needed.
- Use `bearcli outline` to discover copyable section addresses.

Many read commands default to headerless TSV. Prefer `--format json` for structured agent processing and select only needed fields with `--fields`.

Identify a note by ID or by `--title`, which is case-insensitive. Resolve the target first and retain its ID for later mutations:

```bash
bearcli show --title "Project Plan" --format json --fields id,title,location
bearcli cat <note-id>
```

Treat an ambiguous title as unresolved. Do not guess. Empty `list`, `search`, or `search-in` results are successful results, not errors.

## Handle output and failures

- Inspect every command's exit code: `0` is success, `1` is a business error, and `64` is a usage error.
- Expect many mutations and app actions to produce no stdout on success; their exit code is the success signal.
- Verify silent writes with a suitable follow-up read such as `cat`, `show`, `tags list`, `pin list`, or `attachments list`.
- Read plain errors from stderr. For read commands that accept `--format json`, expect documented JSON data or an `error` object; do not assume any third-party response envelope or error-code catalog.

## Mutate notes safely

Use `create` for a new note. When a title is supplied, Bear generates its `#` heading; `--content` is body text and `--tags` accepts comma-separated tag names:

```bash
bearcli create "Project Plan" --content "First draft" --tags "work,work/plans" --format json
```

Prefer the narrowest operation:

- Use `edit` for exact replacements, insertions, or deletions. Scope with `--section` when possible.
- Use `append` for content added at a note or section boundary.
- Use section-scoped `overwrite` only when a whole section or preamble must be replaced.
- Avoid whole-note `overwrite` when a narrower operation works.

Read [references/note-format-and-sections.md](references/note-format-and-sections.md) before writing Bear Markdown or changing a section.

Examples:

```bash
bearcli edit <note-id> --find "draft" --replace "final"
bearcli append <note-id> --section "## Tasks" --content "- [ ] Follow up"
```

Many text flags interpret `\n`, `\t`, `\r`, and `\\`. Content read from stdin is not unescaped in the same way.

For a whole-note overwrite:

1. Run `bearcli cat <note-id> --format json` and retain both `content` and `hash`.
2. Build the complete replacement while preserving the title heading, tags, and every attachment link that must remain.
3. Run `bearcli overwrite <note-id> --base <hash> --content "<complete-content>"`.
4. Check the exit code and re-read the note.

Never use `--force` merely to bypass the attachment-removal safety gate. Use it only after the rejection names attachments and their removal is intentional and within the user's request.

Require exact target resolution and explicit scope before trashing notes, renaming or deleting tags globally, merging tags, deleting attachments, or forcing an overwrite. For multi-note work, search first, collect the exact IDs, process them deliberately, and report partial failures. Do not invent a native multi-note command.

## Manage tags and pins

Use nested tag names with slashes, such as `work/meetings`.

```bash
bearcli tags list
bearcli tags list <note-id> --format json
bearcli tags add <note-id> work "work/meetings"
bearcli tags remove <note-id> draft
bearcli tags rename old-name new-name
bearcli tags delete old-name
```

Treat `tags rename` and `tags delete` as global mutations. A rename to an existing tag is rejected unless `--force` is supplied; `--force` merges the tags and cannot be undone.

Pins have contexts: `global` pins a note in All Notes, while a tag name pins it within that tag.

```bash
bearcli pin list <note-id> --format json
bearcli pin add <note-id> global work
bearcli pin remove <note-id> work
```

With no note target, `pin list` lists every pin context in use. Multiple targets passed to `pin add` or `pin remove` are atomic: if any tag does not exist, none of the pin changes apply.

## Handle lifecycle and app interaction

Use `archive`, `trash`, and `restore` by resolved ID. Trash is a soft delete and `restore` can return a trashed or archived note to active notes.

```bash
bearcli archive <note-id>
bearcli trash <note-id>
bearcli restore <note-id>
```

Use `bearcli app open` only when the user requests Bear app interaction or the workflow requires visible UI state. It can open a note, scroll to a header, select exact text, place a caret by byte offset, enter edit mode, or use a new or floating window:

```bash
bearcli app open <note-id> --header "Tasks" --edit
bearcli app open <note-id> --selection-text "Follow up"
bearcli app open <note-id> --selection-offset 120 --selection-length 0
```

Use `bearcli app get-selection --format json` to read the open note and current selection. Treat selection offsets and lengths as UTF-8 byte positions. App actions foreground or visibly change Bear, so avoid them for background-only work.

## Handle attachments and export

Read [references/export-and-attachments.md](references/export-and-attachments.md) before adding, saving, deleting, or exporting attachments or notes. Distinguish raw CLI extraction from Bear's native formatted export, and inspect live help before deciding whether the installed CLI supports export.
