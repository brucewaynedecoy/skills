# Bear note format and sections

## Write Bear-flavored Markdown

- Use ATX headings (`#`, `##`, and so on). Do not use setext headings.
- Use `==highlight==`, `~underline~`, and `~~strikethrough~~`.
- Start a colored highlight with an allowed color marker: `==🔴highlight==`, `==🔵highlight==`, `==🟢highlight==`, `==🟡highlight==`, or `==🟣highlight==`.
- Write tags as `#tag`, `#multi word tag#`, or `#nested/child`.
- Write wikilinks as `[[Note Title]]` or `[[Title|alias]]`.
- Write inline math as `$x + y$` and block math between `$$` lines.
- Write tasks as `- [ ] todo` or `- [x] done`.
- Use GFM tables with pipes at both ends of every row:

```markdown
| Item | State |
| --- | --- |
| Draft | Open |
```

- Write callouts as `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, or `> [!CAUTION]`.
- Indent every continuation line in a list, and repeat `>` on every continued block-quote line:

```markdown
- First list line
  Continued list line

> First quote line
> Continued quote line
```

- Do not use indented code blocks or lazy continuation.
- Do not hard-wrap prose. Bear preserves those line breaks visually and produces ragged paragraphs.

Text flags such as `--content`, `--find`, and `--section` interpret `\n`, `\t`, `\r`, and `\\`. Content provided through stdin is not unescaped; pass the intended bytes directly.

## Address sections

Run `bearcli outline <note-id>` before a scoped operation. Its `address` values are copyable.

- Address a unique heading directly: `## Install`.
- Disambiguate repeated headings with enclosing ancestor headings, ordered outer to inner: `# Setup\n## Install`.
- Add a final 1-based occurrence index when needed: `# Build\n## Install\n2`.
- Add a final `preamble` line to address only a section's lead text above its first subheading: `## Install\npreamble`.

Addresses may be multi-line. TSV escapes their newlines as `\n`, and text flags interpret those escapes. JSON represents them as strings containing newline escapes.

Use `cat --section` to read one section and receive its address, range, and hash:

```bash
bearcli outline <note-id> --format json
bearcli cat <note-id> --section "## Tasks" --format json
```

## Replace sections safely

Understand the replacement boundary:

- `overwrite --section "## Tasks"` replaces the heading and everything nested under it. Begin replacement content with the same-level heading.
- `overwrite --section "## Tasks\npreamble"` replaces only the lead text above the first subheading. Do not begin preamble content with a heading.
- Empty content deletes the addressed section or preamble; treat that as destructive.

Use the read-hash-overwrite workflow:

1. Resolve the note ID and obtain the section address with `outline`.
2. Read the exact target with `cat --section <address> --format json`.
3. Retain the returned `hash` and the bytes being replaced.
4. Build content that matches the chosen boundary.
5. Pass the hash back with `--base`:

```bash
bearcli overwrite <note-id> \
  --section "## Tasks" \
  --base <section-hash> \
  --content "## Tasks\nRewritten body"
```

6. Check the exit code and re-read the section. If the base is stale, re-read and reconcile instead of forcing the overwrite.

A whole-note hash can guard a section replacement too, but it rejects the write when anything in the note changed. Prefer the section hash when only that section matters.
