---
name: teable-pkm
description: >-
  Operate Tyler Kneisly's Teable personal knowledge management base. Use this
  skill whenever finding, creating, updating, organizing, or relating
  organizations, people, agents, teams, projects, activities, notes,
  bookmarks, memories, tags, affiliations, or team roles in base
  bseWajUDRaJlY2pDgJf. Also use it for reminders, tasks, meetings, research,
  transcripts, instructions, agent context, knowledge relationships, and
  cross-table classification, even when the user does not explicitly call
  the system a PKM.
compatibility: Requires the Teable CLI and access to base bseWajUDRaJlY2pDgJf.
---

# Teable PKM

Use this skill to operate Tyler Kneisly's personal knowledge management base.

## Base Identity

```bash
BASE_ID="bseWajUDRaJlY2pDgJf"
SYSTEM_TABLE_ID="tblF5VKs7aunLGBZ7tL"
START_VIEW_ID="viw8L0HsvP4IqyXv9AK"
```

Pass `--base-id "$BASE_ID"` to commands when the CLI is not already scoped to
this base.

## Start Here

At the beginning of an unfamiliar PKM task, read the active operating guide:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "$SYSTEM_TABLE_ID" \
  --view-id "$START_VIEW_ID" \
  --take 100
```

Then read the `System` row for each table involved in the task:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "$SYSTEM_TABLE_ID" \
  --search '{"value":"Activities","fieldId":"fldH35iswhbnyZlsUfB"}' \
  --take 20
```

Replace `Activities` with the exact table name.

Use `teable get-node-tree` when current table IDs or available resources must be
confirmed. Use `teable field get` and `teable view get` when current fields or
views are needed. Treat the live schema as authoritative if it differs from
this skill.

## Table Registry

| Table | Table ID | Primary field ID | Purpose |
|---|---|---|---|
| Organizations | `tblFog0XHRPweFh4dcj` | `fld6ErHV8hiu25h5mjM` | Companies, clients, communities, churches, agencies, households, and other durable organizations |
| Affiliations | `tbl6vy1qknKh4XZeyMC` | `fldP8Qo921J6STHBgXh` | Person-to-organization roles, departments, relationship types, and dates |
| Persons | `tblfyvECUU5Wo3QVJ9J` | `fldLsjeMgJ9VkIaq7k9` | Contacts, human users, and assignable agent identities |
| Agents | `tbljYF8abSc3WN0g08o` | `fldXnm4RC50hcaI20Ww` | Supplemental role, instructions, harness, capabilities, and connection history for agents |
| Teams | `tblmW5QNcOSqo24fij3` | `fldMEugQUT5Wj6kDcKR` | Purpose-driven groups within organizations |
| Team Roles | `tbl9u9E16BJAa2Ucqv1` | `fldR3m0V6Ln2b90Q8Fh` | Team duties, functions, roles, and assigned members |
| Projects | `tblpkjjYd2imTGVJspN` | `fldFvV0v7uSSXnTFQb7` | Purpose-driven work with objectives, owners, teams, and milestones |
| Activities | `tblsMY7UWZyRI4oA0FD` | `fldnel1ZTlq9iHgq1M7` | Tasks, messages, events, meetings, reminders, and logs |
| Notes | `tblUMuHBGXe8Hbbqapp` | `fld6xL67NAOFroWiFxj` | Notes, research, transcripts, instructions, and other unstructured knowledge |
| Bookmarks | `tbllkHoWFPATTUh4L9J` | `fldsrUuR0XElG8DTmqJ` | URLs, files, locations, internal locators, and knowledge relationships |
| Memories | `tblQ3cH90sgslLjo4KD` | `fldJ0hck9PZ3jwbHcJS` | Agent-oriented preferences, contracts, facts, decisions, and context |
| Tags | `tblh1s1NfEWrrbMiK7z` | `fldGMQ9ODpwJO1S0rbU` | Canonical cross-table subjects and hierarchical classification |
| System | `tblF5VKs7aunLGBZ7tL` | `fldIZOucDjZCTLdsuNA` | Operating guide and schema index |

## Route Information Correctly

Choose the table according to the meaning of the information, not merely its
format.

| Information | Store it in |
|---|---|
| Company, client, church, community, agency, or other durable group | Organizations |
| A person's role or relationship with an organization | Affiliations |
| Human contact, human user, or assignable agent identity | Persons |
| Agent role, instructions, harnesses, capabilities, or connection history | Agents |
| Purpose-driven group of people | Teams |
| Functions and duties performed within a team | Team Roles |
| Coordinated work with a measurable objective | Projects |
| Child project or measurable checkpoint | Projects with `Kind = Milestone` |
| Task, action, message, event, meeting, reminder, or operational log | Activities |
| Research, transcript, instructions, meeting notes, or unstructured knowledge | Notes |
| URL, file path, coordinate, locator, or relationship between resources | Bookmarks |
| Agent preference, contract, fact, decision, heuristic, or retained context | Memories |
| Reusable subject spanning multiple tables | Tags |
| Base operating or schema guidance | System |

Do not create separate Meetings, Actions, Research, or Reminders tables:

- A meeting is an Activity with `Type = Meeting`.
- An action or task is an Activity with `Type = Task`.
- A reminder is an Activity with `Type = Reminder`.
- Research is a Note with `Type = Research`.
- Meeting notes are Notes linked to the meeting Activity.

## General Operating Rules

1. Search before creating a record.
2. Resolve linked records before writing links.
3. Use stable record IDs when a primary title is ambiguous.
4. Preserve useful summaries and context during updates.
5. Use direct links for common, stable relationships.
6. Use Bookmarks for polymorphic or external relationships.
7. Use Tags for subjects, not for relationships or workflow states.
8. Archive records instead of deleting them.
9. Do not bulk-update records until the target scope has been read and checked.
10. Update `System` when changing the schema or its operating conventions.
11. Do not create synthetic domain records merely to test the base.
12. Report created or updated record IDs when finishing a mutation task.

## Finding Records

Search all fields when the identifying field is unknown:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --search "security review" \
  --take 100
```

Search a primary field when a precise lookup is needed:

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

For view-relative requests, resolve the view by exact name:

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

Do not identify a record by title alone when multiple records share that title.
Use organization, project, owner, email, or another contextual field to
disambiguate it.

## Writing Records

Use one bulk command when creating or updating multiple records in the same
table.

```bash
teable record create \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --header '["Title","Type","Status","Priority","Due At","Summary"]' \
  --records '[
    [
      "Prepare security review",
      "Task",
      "Planned",
      "High",
      "2026-08-24T17:00:00-05:00",
      "Prepare the materials required for the security review."
    ]
  ]'
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

In updates:

- `""` means leave the field unchanged.
- `null` clears a field.
- Use `true` or `null` for checkboxes.
- Use ISO 8601 date values with an explicit offset when time matters.
- Choice names are case-sensitive.

## Writing Links

Prefer link objects containing both the stable record ID and current title.

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

Example Activity with resolved links:

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

Search and resolve linked records before issuing this write.

## Person and Agent Identity

`Persons` is the common assignment surface for humans and agents.

`Person Type` has these exact choices:

- `Contact`
- `User`
- `Agent`

When creating an agent:

1. Search both `Agents` and `Persons` for an existing identity.
2. Create the Agent record with its role, purpose, instructions, and status.
3. Create the Persons record with `Person Type = Agent`.
4. Link the Persons record to the Agent record through the one-to-one `Agent`
   field.
5. Assign work, team roles, project ownership, note authorship, and activity
   parties through the Persons record.

A Persons record with `Person Type = Agent` requires exactly one Agent link.
Contact and User records must not link an Agent record.

Agent `Role` choices are:

- `Personal Assistant`
- `Researcher`
- `Project Manager`
- `Analyst`
- `Writer`
- `Developer`
- `Administrator`
- `Specialist`
- `Other`

Agent `Status` choices are `Active`, `Paused`, `Inactive`, and `Archived`.

`Harnesses` may contain `Claude`, `Claude Code`, `ChatGPT`, `Codex`,
`GitHub Copilot`, `Cursor`, or `Other`.

When the current agent's identity is known:

- Read its Agent record when directed to load base-specific context.
- Read relevant active Memories and Bookmarks rather than loading every memory.
- Update `Last Connected At` when the agent actually connects under this skill.
- Update `Last Context Refresh At` after reloading its instructions and memories.
- Update `Last Action At` after a meaningful base mutation.
- Do not create an Activity log for every CLI command. Log only significant
  operational events when a durable timeline entry is useful.

## Organizations, Affiliations, Teams, and Roles

Use `Organizations.Relationships` for Tyler's overall relationship with an
organization:

- `Employer`
- `Client`
- `Partner`
- `Vendor`
- `Member Of`
- `Sponsor`
- `Other`

Use an Affiliation when a particular person's title, department, relationship
type, primary affiliation, or dates matter.

Use Team Roles for role definitions and duties. Team Role members link to
Persons, allowing human and agent members to be assigned consistently.

A Team should normally have:

- `Name`
- `Organization`
- `Team Type`
- `Purpose`
- `Status`

A Team Role should normally have:

- `Name`
- `Team`
- `Role`
- `Functions and Duties`
- `Status`
- `Members`, when filled

Use `Status = Open` for an unfilled Team Role.

## Projects and Milestones

A Project should have a measurable `Objective` and, when possible, explicit
`Success Criteria`.

Project `Kind` choices are:

- `Project`
- `Milestone`

Project `Status` choices are:

- `Proposed`
- `Planned`
- `Active`
- `Blocked`
- `On Hold`
- `Completed`
- `Cancelled`
- `Archived`

A record with `Kind = Milestone` requires `Parent Project`.

Use Activities for executable work. Do not place detailed task lists in
`Objective`, `Success Criteria`, or `Summary`.

When completing a Project or Milestone, set both:

- `Status = Completed`
- `Completed At` to the actual completion time

## Activities

Activity `Type` choices are:

- `Task`
- `Message`
- `Event`
- `Meeting`
- `Reminder`
- `Log`

Activity `Status` choices are:

- `Inbox`
- `Planned`
- `Active`
- `Waiting`
- `Blocked`
- `Completed`
- `Cancelled`
- `Archived`

Activity `Priority` choices are:

- `None`
- `Low`
- `Normal`
- `High`
- `Urgent`

Use party fields according to their semantics:

- `For`: who benefits from or requested the activity.
- `Assigned To`: who is responsible for completing it.
- `Actors`: who initiated, authored, or performed it.
- `Participants or Audience`: who participated or received it.

Use `Parent Activity` for hierarchical tasks and related sub-activities. Child
activities should normally use the same Project as their parent.

When an Activity is completed, set `Completed At` and record a useful `Outcome`
when the result is not obvious.

Use these views for operational work:

- `Inbox`
- `Open Tasks`
- `Unassigned Work`
- `By Assignee`
- `By Project`
- `By Organization`
- `Status Board`
- `Due Calendar`
- `Meetings and Events`
- `Logs`
- `Completed Missing Date`

## Notes

Use Notes as the primary store for unstructured knowledge, but keep concise
summary-level fields on Organizations, Persons, Teams, Projects, Activities,
and other domain records.

Note `Type` choices are:

- `Note`
- `Research`
- `Transcript`
- `Instructions`
- `Meeting Notes`
- `Journal`
- `Reference`
- `Draft`
- `Other`

Note `Status` choices are `Draft`, `Active`, `Final`, `Superseded`, and
`Archived`.

`Confidentiality` choices are:

- `Private`
- `Restricted`
- `Internal`
- `Shared`
- `Public`

A Note should normally include `Title`, `Type`, `Status`, `Body`, and `Author`
when known.

Use direct links from Notes to Organizations, Teams, Projects, and Activities
for common context. Use `Supersedes` when a Note replaces an earlier version.

Link meeting notes to the corresponding Meeting Activity.

## Bookmarks and Knowledge Relationships

Bookmarks support both one-sided resources and subject-disposition-object
relationships.

Bookmark `Kind` choices are:

- `URL`
- `File`
- `Internal Record`
- `Relationship`
- `Location`
- `Other`

Endpoint `Kind` choices are:

- `Internal Record`
- `URL`
- `File`
- `Location`
- `Text`
- `Other`

For a one-sided bookmark:

- Fill the subject endpoint.
- Leave `Disposition` and all object fields empty.

For an internal endpoint, store:

- exact table name in `Subject Table` or `Object Table`
- stable `rec...` ID in `Subject Record ID` or `Object Record ID`
- readable current title in the corresponding Label
- navigable URL in the Locator when available

For a relationship, store:

```text
[Subject] [Disposition] [Object]
```

Example:

```text
[Jane Doe] [is friends with] [Samantha Smith]
```

Relationship records require:

- `Kind = Relationship`
- a complete subject endpoint
- `Disposition`
- a complete object endpoint

Use concise, directional dispositions such as:

- `works for`
- `is a member of`
- `depends on`
- `applies to`
- `supersedes`
- `was produced by`
- `is evidence for`
- `is related to`

Prefer a precise disposition over generic `is related to`.

Use these validation views:

- `Relationships Missing Disposition`
- `Relationships Missing Object`
- `Needs Verification`

## Memories

Memories are agent-oriented retained context. They are not reminders.

Memory `Category` choices are:

- `Working`
- `Short-Term`
- `Long-Term`
- `Episodic`
- `Semantic`
- `Daydream`

Use the categories as follows:

- `Working`: immediately active context for current work.
- `Short-Term`: temporary context expected to expire or be reviewed.
- `Long-Term`: durable preferences, conventions, or context.
- `Episodic`: context tied to a specific event or experience.
- `Semantic`: stable facts or conceptual knowledge.
- `Daydream`: speculative, exploratory, or not-yet-adopted ideas.

Memory `Kind` choices are:

- `Preference`
- `Contract`
- `Fact`
- `Decision`
- `Heuristic`
- `Context`
- `Reflection`

Memory `Status` choices are `Active`, `Superseded`, `Expired`, and `Archived`.

A useful Memory normally includes:

- `Title`
- `Category`
- `Kind`
- `Content`
- `Status`
- `Agent`
- `Importance`
- `Confidence`

Use `Contract` for behavioral or formatting conventions. Do not use it for an
ordinary task or reminder.

Do not add direct Organization, Team, Project, Activity, or Note links to
Memories. Relate a Memory to another resource by creating a Bookmark
relationship.

Example:

```text
[Memory: Weekly reports use concise Markdown]
[applies to]
[Project: Executive Reporting]
```

Use `Supersedes` when guidance, preferences, or facts change. Preserve the old
record and set its status to `Superseded`.

Review `Working Memory`, `Long-Term Memory`, `Review Due`, and `Expiring Soon`
when loading agent context.

## Tags

Use Tags for reusable subjects that should retrieve records across different
tables.

Before creating a Tag:

1. Search `Name`.
2. Search `Aliases`.
3. Check the relevant `Namespace`.
4. Reuse the canonical Tag when one already represents the subject.

Use singular canonical names. Use `Parent Tag` for hierarchy and `Aliases` for
synonyms.

Tag `Status` choices are:

- `Active`
- `Deprecated`
- `Archived`

Do not use Tags to encode:

- workflow status
- assignment roles
- arbitrary relationships
- external locators
- prose that belongs in a Summary or Note

Every substantive table has a direct `Tags` link. Use that link instead of
creating Bookmarks for ordinary tagging.

## Archival and Deletion

Preserve historical and relational value by changing lifecycle state:

- Organizations, Persons, Teams, and similar records: `Inactive` or `Archived`
- Projects and Activities: `Completed`, `Cancelled`, or `Archived`
- Notes: `Superseded` or `Archived`
- Memories: `Superseded`, `Expired`, or `Archived`
- Tags: `Deprecated` or `Archived`
- Bookmarks: `Broken` or `Archived`

Do not delete records unless the user explicitly requests deletion and the
scope and impact have been confirmed.

Before deleting a duplicate, inspect its links and move any required context
to the surviving record.

## Validation Before Finishing

After a mutation, inspect the validation view relevant to the changed record:

- Persons: `Agents Missing Agent Record`
- Agents: `Agents Missing Person`
- Projects: `Milestones Missing Parent`
- Activities: `Unassigned Work` and `Completed Missing Date`
- Bookmarks: `Relationships Missing Disposition` and
  `Relationships Missing Object`
- Memories: `Review Due` and `Expiring Soon`

A validation view may contain unrelated pre-existing records. Report those
separately; do not modify them unless they are within the user's requested
scope.

For values resolved by Teable, such as links, collaborator identities, and
parsed dates, read back the first affected record once. Do not repeatedly
re-read every record written successfully.

## Maintaining System

When adding or materially changing a table:

1. Update or create its `System` row.
2. Record the exact table name and table ID.
3. Update purpose, retrieval guidance, minimum fields, validation rules,
   relationships, and important views.
4. Increment `Schema Version` when the operating contract changes.
5. Set `Last Reviewed At` to the actual review time.
6. Keep the guidance concise enough for an unfamiliar agent to scan quickly.

Do not duplicate the entire field schema in `System`. Store operational
guidance and discovery rules there.

## Completion Report

After changing the base, report:

- tables affected
- records created or updated
- stable record IDs
- significant links established
- any validation issue or ambiguity left unresolved
- any requested operation that was not performed

Do not claim completion for writes that failed or for asynchronous work that
was only accepted but not completed.
