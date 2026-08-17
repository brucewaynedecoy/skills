# Identity and Groups

Use these rules for Organizations, Affiliations, Persons, Agents, Teams, and
Team Roles.

## Persons and agents

Use `Persons` as the common assignment surface for humans and agents.

Use these exact `Person Type` choices:

- `Contact`
- `User`
- `Agent`

When creating an agent:

1. Search both `Agents` and `Persons` for an existing identity.
2. Create the Agent record with its role, purpose, instructions, and status.
3. Create the Persons record with `Person Type = Agent`.
4. Link the Persons record to the Agent record through the one-to-one `Agent`
   field.
5. Assign work, team roles, project ownership, note authorship, and Activity
   parties through the Persons record.

Require exactly one Agent link when `Person Type = Agent`. Do not link an
Agent record from a Contact or User record.

Use these exact Agent `Role` choices:

- `Personal Assistant`
- `Researcher`
- `Project Manager`
- `Analyst`
- `Writer`
- `Developer`
- `Administrator`
- `Specialist`
- `Other`

Use `Active`, `Paused`, `Inactive`, or `Archived` for Agent `Status`.

`Harnesses` can contain `Claude`, `Claude Code`, `ChatGPT`, `Codex`,
`GitHub Copilot`, `Cursor`, or `Other`.

When the current agent identity is known:

- Read its Agent record when the task requires base-specific context.
- Read only the active Memories and Bookmarks that apply to the task.
- Update `Last Connected At` only during an authorized write session.
- Update `Last Context Refresh At` after an authorized reload of its
  instructions and memories.
- Update `Last Action At` after a meaningful, authorized base mutation.
- Do not create an Activity log for every CLI command.
- Log only significant events that need a durable timeline entry.

## Organizations and affiliations

Use `Organizations.Relationships` for Tyler's overall relationship with an
organization. Use these exact choices:

- `Employer`
- `Client`
- `Partner`
- `Vendor`
- `Member Of`
- `Sponsor`
- `Other`

Use an Affiliation when a person's title, department, relationship type,
primary affiliation, or effective dates matter.

## Teams and team roles

Use Team Roles for role definitions and duties. Link Team Role members to
Persons so human and agent members use the same assignment model.

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
