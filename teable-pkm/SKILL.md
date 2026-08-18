---
name: teable-pkm
description: >-
  Operate Tyler Kneisly's Teable personal knowledge management base. Use this
  skill to find, create, update, organize, archive, or relate organizations,
  people, agents, teams, projects, activities, notes, bookmarks, memories,
  tags, affiliations, and team roles in base bseWajUDRaJlY2pDgJf. Also use it
  for reminders, tasks, meetings, research, transcripts, instructions, agent
  context, knowledge relationships, schema guidance, and cross-table
  classification, even when the user does not call the system a PKM.
---

# Teable PKM

Operate Tyler Kneisly's Teable personal knowledge management base through the
Teable CLI.

## Use the fixed base identity

```bash
BASE_ID="bseWajUDRaJlY2pDgJf"
SYSTEM_TABLE_ID="tblF5VKs7aunLGBZ7tL"
START_VIEW_ID="viw8L0HsvP4IqyXv9AK"
```

Pass `--base-id "$BASE_ID"` when the CLI is not already scoped to this base.

Treat the live schema and active `System` records as authoritative. If they
disagree with this skill, follow the live base and report the difference.

## Keep the authority boundary

- Treat search, inspection, explanation, planning, and validation requests as
  read-only.
- Create, update, archive, or delete records only when the user requests a
  write.
- Confirm the exact target before a bulk change.
- Do not create synthetic domain records merely to test the base.
- Archive records instead of deleting them.
- Delete only when the user explicitly requests deletion and the link impact
  is known.
- Do not update agent connection timestamps during read-only work.
- Resolving your own agent identity is a read and is always permitted.
  Creating an agent identity is a write and requires user approval.

## Resolve your agent identity first

Do this once at the start of every session, before any other base work. It is
a read, so it is permitted even for a read-only request.

1. Read the active Agent records.
2. Keep only the records whose `Harnesses` include the harness you are running
   in. `Harnesses` is an eligibility gate, not a discriminator.
3. Among those, adopt the record whose `Role` fits your intent for this
   session. `Role` is the discriminator.
4. If exactly one record matches, adopt it and continue.
5. If no record matches, continue without an identity. Do not create one
   silently. Ask the user once, and create it only if the user approves.
6. If more than one record matches, ask the user which identity to use.

Re-resolve when the session's objective shifts to a different `Role`, such as
extraction becoming curation. Attribute every record to the identity that was
active when that work happened, and report each identity you used.

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "tbljYF8abSc3WN0g08o" \
  --take 100
```

An adopted identity gives you the `Agent` link that `Memories` requires and
the `Persons` record used for `Recorded By`, note authorship, and Activity
parties. Without an identity you may still read and write domain records, but
you must not write `Memories`. Say so in your final report.

Read [references/identity-and-groups.md](references/identity-and-groups.md)
for the match rule, the re-resolution rule, the approval wording, and the
memory-capture rules.

## Follow the core workflow

1. Resolve your agent identity.
2. Determine whether the request is read-only or permits a write.
3. Read the active operating guide for an unfamiliar task.
4. Choose the table from the meaning of the information.
5. Read the `System` row and the reference files for each involved table.
6. Search for existing records before creating new records.
7. Resolve linked records before writing links.
8. Write only the requested scope.
9. Read back the first affected record when Teable resolves links,
   collaborators, choices, or dates.
10. Capture durable `Memories` under your identity when the session produced
    knowledge that should shape later sessions.
11. Inspect the applicable validation view.
12. Report the result and all unresolved issues.

Read the active operating guide:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "$SYSTEM_TABLE_ID" \
  --view-id "$START_VIEW_ID" \
  --take 100
```

Read the `System` row for an involved table:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "$SYSTEM_TABLE_ID" \
  --search '{"value":"Activities","fieldId":"fldH35iswhbnyZlsUfB"}' \
  --take 20
```

Replace `Activities` with the exact table name. Use `teable get-node-tree`
when the current table catalog must be confirmed. Use `teable field get` and
`teable view get` when current fields or views are needed.

## Route information by meaning

| Information | Table |
|---|---|
| Durable company, client, church, community, agency, or group | Organizations |
| A person's role or relationship with an organization | Affiliations |
| Human contact, human user, or assignable agent identity | Persons |
| Agent role, instructions, harnesses, capabilities, or connection history | Agents |
| Purpose-driven group of people | Teams |
| Duties, functions, and assigned members within a team | Team Roles |
| Coordinated work with a measurable objective | Projects |
| Child project or measurable checkpoint | Projects with `Kind = Milestone` |
| Task, message, event, meeting, reminder, or operational log | Activities |
| Research, transcript, instructions, meeting notes, or unstructured knowledge | Notes |
| URL, file, location, locator, or polymorphic relationship | Bookmarks |
| Agent preference, contract, fact, decision, heuristic, or retained context | Memories |
| Reusable subject that spans tables | Tags |
| Base operating or schema guidance | System |

Do not create separate Meetings, Actions, Research, or Reminders tables. Use
typed Activities and Notes.

## Load only the needed references

- Read [references/table-registry.md](references/table-registry.md) when exact
  table IDs, primary field IDs, or table purposes are needed.
- Read [references/record-operations.md](references/record-operations.md)
  before complex searches or any record, link, or bulk write.
- Read [references/identity-and-groups.md](references/identity-and-groups.md)
  for Organizations, Affiliations, Persons, Agents, Teams, or Team Roles.
- Read [references/work-management.md](references/work-management.md) for
  Projects, Milestones, Activities, tasks, meetings, events, or reminders.
- Read [references/knowledge-management.md](references/knowledge-management.md)
  for Notes, Bookmarks, Memories, Tags, research, transcripts, instructions,
  or knowledge relationships.
- Read [references/capture-transcript.md](references/capture-transcript.md)
  before capturing a meeting recording, transcript, or call into the base.
  Read it in addition to the reference for each table you will write.

A reference named `capture-<source>.md` covers ingesting one kind of external
source into the base. Read the matching capture reference alongside the table
references, never instead of them. Name any new capture reference the same
way, so the set stays grouped.
- Read [references/system-maintenance.md](references/system-maintenance.md)
  for validation, archival, deletion, schema maintenance, or completion
  reports after a mutation.

Load each selected reference directly from this file. Do not load unrelated
references.

## Apply the universal operating rules

1. Search before creating a record.
2. Resolve linked records before writing links.
3. Use stable record IDs when a primary title is ambiguous.
4. Preserve useful summaries and context during updates.
5. Use direct links for common, stable relationships.
6. Use Bookmarks for polymorphic or external relationships.
7. Use Tags for subjects, not relationships or workflow states.
8. Do not bulk-update records until the target scope is read and checked.
9. Update `System` when the user requests a schema or operating-contract
   change.
10. Report created or updated record IDs after a mutation.
11. Write a `Memory` only under a resolved agent identity.
12. Reuse an existing agent identity instead of creating a near-duplicate.
13. Prefer a harness-agnostic identity; add a harness to an existing record
    rather than forking a parallel one.
14. Search the source identifier before capturing any external source, so a
    re-run updates records instead of duplicating them.

## Finish with evidence

After a permitted write, report:

- every agent identity used, what each one did, and any re-resolution, or that
  no identity was resolved
- tables affected
- records created or updated
- stable record IDs
- significant links established
- memories captured, or why none were captured
- validation issues or unresolved ambiguity
- requested operations that were not performed

Do not claim completion for failed writes or for asynchronous work that was
accepted but did not complete.
