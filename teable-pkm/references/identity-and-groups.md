# Identity and Groups

Use these rules for Organizations, Affiliations, Persons, Agents, Teams, and
Team Roles.

## Resolve your own agent identity

Every agent that touches this base adopts an identity before it does anything
else. The identity is what makes `Memories` writable and what attributes work
to an actor instead of to nobody.

### Match on role, gated by harness

Two fields decide the match, and they do different jobs.

- `Harnesses` is an **eligibility gate**. An Agent record is usable only if its
  `Harnesses` include the harness you are running in. It does not tell one
  identity apart from another.
- `Role` is the **discriminator**. Among eligible records, adopt the one whose
  `Role` fits your intent for this session.

Prefer harness-agnostic identities. Give an Agent record every harness it can
legitimately run in, so the same identity and the same memories follow the work
across `Claude`, `Claude Code`, `ChatGPT`, and `Codex`. Create a harness-specific
identity only when behaviour genuinely differs by harness, never merely because
you are running somewhere new.

`Role` is a closed vocabulary of nine choices, so a fully harness-agnostic base
needs at most nine identities. That ceiling is the point. Do not create an
identity per session, per task, per model, or per project.

Judge role fit from your objective for the session, not from the first table
you happen to touch:

| Session intent | Role |
|---|---|
| Curating, correcting, or maintaining the base itself | `Administrator` |
| Gathering, extracting, or migrating source material | `Researcher` |
| Interpreting records to answer a question | `Analyst` |
| Planning or tracking work and milestones | `Project Manager` |
| Drafting prose, summaries, or reports | `Writer` |
| Writing or changing code | `Developer` |
| Day-to-day help across mixed requests | `Personal Assistant` |

### Apply the resolution outcomes

- **Exactly one match.** Adopt it. Continue.
- **No match.** Continue without an identity. State that you found no match,
  name the role you would use, and ask the user to approve creating it. Create
  it only after the user approves.
- **An eligible role exists but your harness is missing from it.** Do not
  create a parallel identity. Ask the user to approve adding your harness to
  the existing record.
- **More than one match.** Ask the user which identity to use. Do not guess
  and do not create a third.

### Re-resolve when the session's intent shifts

A long session changes jobs. Extraction becomes curation. Curation becomes
analysis. Do not carry the opening identity through work it did not do.

Re-resolve when the objective for the remainder of the session matches a
different `Role`. Apply this test: if you were starting fresh at this moment,
would you match a different Role? If yes, switch.

Do not switch for:

- a single step inside the current objective
- touching a different table
- a question asked in passing

To switch:

1. Stamp `Last Action At` on the outgoing identity if it made a real mutation.
2. Resolve the incoming identity by the normal rule.
3. Stamp `Last Connected At` on the incoming identity.
4. Continue under the incoming identity.

Attribute every record to the identity that was active when the work happened,
not the one active when you got round to writing it:

- `Memories.Agent` and `Memories.Recorded By`: the identity that produced the
  knowledge.
- Note `Author` and Activity `Actors`: the Persons record of the identity that
  did the work.

When a session used more than one identity, report each identity and what it
did. Do not log an Activity for the switch itself.

### Keep reads and writes separate

- Reading Agent records to resolve your identity is a **read**. It is always
  permitted, including during a read-only request.
- Creating an Agent record, creating its Persons record, or stamping
  `Last Connected At`, `Last Context Refresh At`, or `Last Action At` is a
  **write**. It follows the normal write rules.
- A read-only session adopts an identity but stamps no timestamps.

### Work without an identity when you must

You may still read and write ordinary domain records with no identity. You
must not write `Memories`, because `Memories.Agent` has no value to hold. Say
so in the final report rather than skipping the point silently.

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

Name an Agent record for its role, not for a harness, session, task, or model.
Use the form `PKM <Role>`, such as `PKM Administrator`. Keep the paired Persons
record on the same name. Set `Harnesses` to every harness the identity can
legitimately run in.

Use a harness-qualified name such as `Claude Code Administrator` only for an
identity that genuinely behaves differently in one harness. That is the rare
case, not the default.

A new identity is a schema-shaped decision, so it needs the user's approval
every time.

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
