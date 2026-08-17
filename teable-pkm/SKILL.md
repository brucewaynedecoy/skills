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

## Follow the core workflow

1. Determine whether the request is read-only or permits a write.
2. Read the active operating guide for an unfamiliar task.
3. Choose the table from the meaning of the information.
4. Read the `System` row and the reference files for each involved table.
5. Search for existing records before creating new records.
6. Resolve linked records before writing links.
7. Write only the requested scope.
8. Read back the first affected record when Teable resolves links,
   collaborators, choices, or dates.
9. Inspect the applicable validation view.
10. Report the result and all unresolved issues.

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

## Finish with evidence

After a permitted write, report:

- tables affected
- records created or updated
- stable record IDs
- significant links established
- validation issues or unresolved ambiguity
- requested operations that were not performed

Do not claim completion for failed writes or for asynchronous work that was
accepted but did not complete.
