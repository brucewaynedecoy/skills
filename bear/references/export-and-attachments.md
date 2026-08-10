# Export and attachments

## Extract through the CLI

Use `cat` to extract raw Bear Markdown:

```bash
bearcli cat <note-id>
```

List attachment filenames and byte sizes before operating on them:

```bash
bearcli attachments list <note-id> --format json
```

Save one attachment by redirecting its raw stdout bytes. The command refuses to write binary data to a terminal:

```bash
bearcli attachments save <note-id> --filename photo.jpg > photo.jpg
```

Add local bytes through stdin. Bear appends a Markdown link automatically:

```bash
bearcli attachments add <note-id> --filename photo.jpg < photo.jpg
```

Add a remote attachment only from HTTPS:

```bash
bearcli attachments add-url <note-id> \
  --url https://example.com/photo.jpg \
  --filename photo.jpg
```

`add-url` rejects `http://`, `file://`, and `data:` URLs. On a filename collision, Bear may rename the new file, such as `photo.jpg` to `photo 2.jpg`; the inserted Markdown link uses the resolved name.

Attachment mutations update the note's Markdown links. `attachments add` and `add-url` append a link. `attachments delete` removes both the bytes and its link. Resolve the exact note ID and filename before deleting, then verify with `attachments list` and `cat`.

Do not expect an external image URL written into note Markdown to become a rendered Bear attachment. Add the image bytes with `attachments add` or fetch an HTTPS URL with `attachments add-url`.

## Distinguish native Bear export

Inspect `bearcli -h`, `bearcli help all`, and any live `export` help before deciding what the installed version supports. The currently observed CLI exposes no export subcommand; do not invent one. Recheck because a future Bear release may add the capability.

Bear's native UI exports these formats:

- Free and Pro: `.txt`, `.md`, `.textbundle`, `.bearnote`, and `.rtf`.
- Bear Pro: `.html`, `.docx`, `.pdf`, `.jpg`, and `.ePub`.

Treat `bearcli cat` plus separately saved attachments as raw extraction, not as Bear's native formatted export. It does not reproduce Bear's format conversion, export options, or packaging.

For a native export request:

1. Resolve the note ID.
2. Run `bearcli app open <note-id>` to bring the note into Bear.
3. Explain that selecting the format and destination remains a Bear UI operation.
4. Use a separately authorized desktop-control capability only when available and within the user's request.

Bear app interaction is visible and may foreground the app. Do not open Bear merely to perform raw CLI extraction.

See Bear's official [export documentation](https://bear.app/faq/export-your-notes/) and confirm live CLI capabilities before acting.
