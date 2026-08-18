# Record Operations

Use these Teable CLI patterns for searches and permitted writes. Search and
resolve the target records before every mutation.

## Contents

- [Find records](#find-records)
- [Create and update records](#create-and-update-records)
- [Write links](#write-links)

## Find records

Search all fields when the identifying field is unknown:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --search "security review" \
  --take 100
```

Search a primary field for a precise lookup:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblpkjjYd2imTGVJspN" \
  --search '{"value":"Security Review","fieldId":"fldFvV0v7uSSXnTFQb7"}' \
  --take 100
```

Read a known record directly:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblpkjjYd2imTGVJspN" \
  --record-id "recXXXXXXXX"
```

Resolve a view by its exact name for view-relative requests:

```bash
VIEW_ID=$(
  teable view get \
    --base-id "$BASE_ID" \
    --table-id "tblsMY7UWZyRI4oA0FD" |
  jq -r '.views[] | select(.name == "Open Tasks") | .id'
)

teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --view-id "$VIEW_ID" \
  --take 100
```

Do not identify a record by title alone when records share that title. Use
organization, project, owner, email, or another contextual field to resolve
the target.

## Build the payload in a file

Do not write a `--records` payload as inline single-quoted shell JSON when it
contains prose. Extracted text routinely contains an apostrophe, which closes
the shell quote and silently mangles what gets written. The command still
succeeds, so nothing warns you.

Write the payload to a file, then pass it:

```bash
python3 - <<'PY' > payload.json
import json, sys
json.dump([[
  "Prepare security review",
  "Task",
  "Planned",
  "High",
  "2026-08-24T17:00:00-05:00",
  "Prepare the materials for Tyler's security review."
]], sys.stdout)
PY

teable record create \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --header '["Title","Type","Status","Priority","Due At","Summary"]' \
  --records "$(cat payload.json)"
```

Generating the JSON with a serializer also escapes quotes, newlines, and
non-ASCII characters correctly. Hand-written payloads do not.

Inline JSON is acceptable only for a short payload you can see contains no
apostrophe, quote, or newline.

## Create and update records

Use one bulk command for multiple records in the same table.

```bash
teable record create \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --header '["Title","Type","Status","Priority","Due At","Summary"]' \
  --records "$(cat payload.json)"
```

Update by stable record ID:

```bash
teable record update \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --header '["recordId","Status","Completed At","Outcome"]' \
  --records '[
    [
      "recXXXXXXXX",
      "Completed",
      "2026-08-24T16:30:00-05:00",
      "Review completed and findings documented."
    ]
  ]'
```

Apply these update rules:

- Use `""` to leave a field unchanged.
- Use `null` to clear a field.
- Use `true` or `null` for a checkbox.
- Use ISO 8601 dates with an explicit offset when time matters.
- Match choice names exactly. Choice names are case-sensitive.
- Read the target record immediately before updating it. Never trust a record
  ID you are carrying from earlier in the session. Writing the right content to
  the wrong record produces two wrong records and no error.

## Check every write

`success: true` does not mean the write landed as intended.

- Read the `warnings` array on every create and update. A link value that the
  CLI could not resolve is reported there and nowhere else, for example:
  `"Organization" (link): 2 value(s) not written`.
- Read back the first affected record whenever the write set links, dates,
  choices, or collaborators.
- Confirm the record you read back is the one you meant to change.

## Write links

Prefer link objects that contain the stable record ID and current title.

A single link uses an object:

```json
{"id":"recProject123","title":"Security Review"}
```

A multiple link uses an array:

```json
[
  {"id":"recPerson123","title":"Tyler Kneisly"},
  {"id":"recPerson456","title":"Security Agent"}
]
```

Create an Activity with resolved links:

```bash
teable record create \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --header '[
    "Title",
    "Type",
    "Status",
    "Project",
    "Assigned To",
    "Due At",
    "Summary"
  ]' \
  --records '[
    [
      "Draft risk summary",
      "Task",
      "Planned",
      {"id":"recProject123","title":"Security Review"},
      [{"id":"recPerson456","title":"Security Agent"}],
      "2026-08-24T17:00:00-05:00",
      "Summarize the known risks and recommended responses."
    ]
  ]'
```

Search and resolve every linked record before issuing the write.
