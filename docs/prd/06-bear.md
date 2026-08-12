---
title: "06 Bear"
kind: "prd"
status: "active"
---

# 06 Bear

## Purpose

Enable an agent to operate the macOS Bear app through Bear's official command-line interface with precise target resolution, narrow reads and writes, concurrency and attachment safety, correct interpretation of output, and read-back verification. The user asks for a Bear outcome; the skill selects and safely runs the corresponding official command.

## Scope

The skill covers command discovery, note browsing and search, note and metadata reads, creation, exact text or section editing, append and overwrite, tags, pins, archive, trash, restore, visible app interaction, attachments, and export preparation. It applies only when Bear state or the Bear app is the requested surface.

The skill does not install Bear, download Bear Claw, invent unsupported multi-note operations, bypass attachment safeguards, or use visible app actions for background-only work. It requires macOS and Bear 2.8 or later with the official `bearcli` available on `PATH` or in the Bear application bundle.

## Component and Capability Map

| Capability | Required behavior |
| --- | --- |
| Command discovery | Resolve `bearcli` from `PATH`, then the Bear application bundle; report the prerequisite if absent and inspect live help for unfamiliar or version-sensitive operations |
| Browse and search | Use `list` for browsing, `search` for Bear query syntax, and `search-in` for exact case-insensitive occurrences within one note and attachments |
| Note inspection | Use `show` for structured metadata, raw `cat` for Bear Markdown, and `outline` for section addresses; prefer JSON and selected fields for agent processing |
| Target resolution | Resolve a note by exact ID or unambiguous case-insensitive title, retain the ID for mutations, and treat ambiguity as unresolved |
| Note creation and editing | Use `create`, exact `edit`, `append`, or section-scoped `overwrite` according to the narrowest authorized change |
| Whole-note overwrite | Read content and hash, preserve title, tags, and required attachment links, use optimistic concurrency with `--base`, then re-read |
| Tags and pins | Manage nested tags and contextual pins; treat global rename, delete, and forced merge as consequential global mutations |
| Lifecycle | Archive, soft-delete to trash, and restore by resolved note ID |
| App interaction | Open notes, headers, selections, carets, or edit mode only when visible interaction is requested or required; interpret selection offsets as UTF-8 bytes |
| Attachments and export | Follow the dedicated reference, preserve attachment safety, distinguish raw extraction from native formatted export, and inspect installed CLI support before export |

## Contracts and Data

### Read behavior

- Choose the narrowest command that answers the request and request only needed fields.
- Bear search syntax is a product-specific contract; advanced queries follow the local search reference instead of generic shell assumptions.
- Empty `list`, `search`, or `search-in` output is a successful empty result, not an error.
- Structured reads use documented JSON where supported. The skill does not assume a third-party envelope or undocumented error-code catalog.

### Mutation behavior

- Resolve exact targets before every mutation and preserve the resolved ID across the operation.
- Prefer exact replacement or section-scoped changes over whole-note rewriting. Multi-note changes begin with a read-only exact ID inventory and report partial failures.
- Text flags may interpret `\n`, `\t`, `\r`, and `\\`, while stdin content follows the CLI's separate behavior; command construction must preserve intended bytes.
- Whole-note overwrite uses the current content hash as an optimistic concurrency base. `--force` is never a convenience bypass and may be used only when an attachment-removal rejection names attachments whose removal is explicitly intended.
- Trash, global tag rename or deletion, tag merge, attachment deletion, and forced overwrite require exact scope and consequential-action authority.

### Output and verification

- Exit code `0` means success, `1` means a business error, and `64` means usage error.
- Many successful mutations and app actions produce no stdout. Their exit status is authoritative for the command, followed by a suitable `cat`, `show`, `tags list`, `pin list`, or `attachments list` read-back.
- Plain errors come from stderr. Read commands that support JSON return documented data or an error object.
- The skill reports resolved note IDs, the operation performed, and read-back evidence appropriate to the user's request without overexposing note content.

### Tags, pins, and app state

- Nested tags use slash-separated names. Global rename and delete affect all matching notes; forcing a rename to an existing tag performs an irreversible merge.
- Pins have contexts: `global` for All Notes or a tag name for that tag. Multi-target pin add and remove are atomic when any referenced tag is missing.
- App commands foreground or visibly change Bear and therefore require a visible-interaction reason. Background reads and writes should not open the app.

## Integrations

- The official `bearcli` is the sole command integration for Bear data and app behavior in this skill.
- Bear's local note store and app provide the state being read or changed; the skill does not create a parallel database.
- Local references define search syntax, Bear Markdown and section addressing, and attachment or export distinctions.
- The agent's shell provides command execution and exit status; visible application control remains limited to `bearcli app` operations described by the installed version.

## Rebuild Notes

- Preserve progressive reference loading: search syntax only for advanced queries, note-format guidance before content or section writes, and attachment/export guidance before those operations.
- Test missing CLI, application-bundle fallback, empty results, ambiguous titles, exact IDs, silent success, business and usage errors, stale overwrite hashes, attachment-removal gates, global tag consequences, pin atomicity, UTF-8 selection offsets, and version-sensitive help inspection.
- Do not substitute Bear Claw, scrape Bear's private storage, invent a native batch command, or claim that a silent write succeeded without a relevant read-back.
- Keep examples synchronized with live official CLI behavior while retaining the minimum supported Bear version.

## Source Anchors

- [Bear skill](../../bear/SKILL.md)
- [Search syntax](../../bear/references/search-syntax.md)
- [Note format and sections](../../bear/references/note-format-and-sections.md)
- [Export and attachments](../../bear/references/export-and-attachments.md)
- [Repository README](../../README.md)
