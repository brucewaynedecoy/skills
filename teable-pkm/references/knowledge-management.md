# Knowledge Management

Use these rules for Notes, Bookmarks, Memories, Tags, research, transcripts,
instructions, and knowledge relationships.

## Contents

- [Notes](#notes)
- [Bookmarks and relationships](#bookmarks-and-relationships)
- [Memories](#memories)
- [Tags](#tags)

## Notes

Use Notes as the primary store for unstructured knowledge. Keep concise
summary fields on Organizations, Persons, Teams, Projects, Activities, and
other domain records.

Use these exact Note `Type` choices:

- `Note`
- `Research`
- `Transcript`
- `Instructions`
- `Meeting Notes`
- `Journal`
- `Reference`
- `Draft`
- `Other`

Use `Draft`, `Active`, `Final`, `Superseded`, or `Archived` for Note `Status`.

Use these exact `Confidentiality` choices:

- `Private`
- `Restricted`
- `Internal`
- `Shared`
- `Public`

A Note should normally include `Title`, `Type`, `Status`, `Body`, and `Author`
when known.

Use direct links from Notes to Organizations, Teams, Projects, and Activities
for common context. Use `Supersedes` when a Note replaces an earlier version.
Link meeting notes to their Meeting Activity.

## Bookmarks and relationships

Use Bookmarks for both one-sided resources and subject-disposition-object
relationships.

Use these exact Bookmark `Kind` choices:

- `URL`
- `File`
- `Internal Record`
- `Relationship`
- `Location`
- `Other`

Use these exact endpoint `Kind` choices:

- `Internal Record`
- `URL`
- `File`
- `Location`
- `Text`
- `Other`

For a one-sided Bookmark, fill the subject endpoint. Leave `Disposition` and
all object fields empty.

For an internal endpoint, store:

- the exact table name in `Subject Table` or `Object Table`
- the stable `rec...` ID in `Subject Record ID` or `Object Record ID`
- the current readable title in the related Label field
- a navigable URL in the Locator when available

Store a relationship as:

```text
[Subject] [Disposition] [Object]
```

Example:

```text
[Jane Doe] [is friends with] [Samantha Smith]
```

Require `Kind = Relationship`, a complete subject endpoint, a Disposition,
and a complete object endpoint.

Use a short, directional Disposition. Prefer a precise term over `is related
to`. Common terms include:

- `works for`
- `is a member of`
- `depends on`
- `applies to`
- `supersedes`
- `was produced by`
- `is evidence for`
- `is related to`

Use `Relationships Missing Disposition`, `Relationships Missing Object`, and
`Needs Verification` for validation.

## Memories

Use Memories for agent-oriented retained context. Do not use a Memory as a
reminder.

Use these exact Memory `Category` choices:

- `Working`
- `Short-Term`
- `Long-Term`
- `Episodic`
- `Semantic`
- `Daydream`

Apply the categories as follows:

- `Working`: context active in current work.
- `Short-Term`: temporary context that needs review or expiry.
- `Long-Term`: durable preferences, conventions, or context.
- `Episodic`: context tied to an event or experience.
- `Semantic`: stable facts or conceptual knowledge.
- `Daydream`: speculative or not-yet-adopted ideas.

Use these exact Memory `Kind` choices:

- `Preference`
- `Contract`
- `Fact`
- `Decision`
- `Heuristic`
- `Context`
- `Reflection`

Use `Active`, `Superseded`, `Expired`, or `Archived` for Memory `Status`.

A useful Memory normally includes `Title`, `Category`, `Kind`, `Content`,
`Status`, `Agent`, `Importance`, and `Confidence`.

Use `Contract` for behavior or format rules. Do not use it for an ordinary
task or reminder.

Do not add direct Organization, Team, Project, Activity, or Note links to a
Memory. Relate a Memory to another resource with a Bookmark relationship.

```text
[Memory: Weekly reports use concise Markdown]
[applies to]
[Project: Executive Reporting]
```

Use `Supersedes` when guidance, preferences, or facts change. Preserve the old
record and set its status to `Superseded`.

Review `Working Memory`, `Long-Term Memory`, `Review Due`, and `Expiring Soon`
when loading agent context.

### Capture memories during a session

A Memory requires a resolved agent identity. Set `Agent` to your Agent record
and `Recorded By` to its paired Persons record. Without an identity, write no
Memories and say so in the final report. See
[identity-and-groups.md](identity-and-groups.md).

Capture a Memory when the session produced something that should change how a
later session behaves:

- a correction the user made to your model of their world
- a decision the user reached, and the reason behind it
- a durable fact that the records themselves do not state
- a convention, preference, or format rule the user asked you to keep
- a heuristic that saved real effort and would save it again

Do not capture:

- anything already stated by a domain record you just wrote
- the fact that you performed a task
- a reminder or a follow-up; those are Activities
- a restatement of this skill or of the `System` guidance

Prefer one precise Memory over several overlapping ones. When a new Memory
contradicts an existing one, use `Supersedes` and set the old record to
`Superseded` rather than writing a second competing claim.

Relate each Memory to the records it concerns with a Bookmark relationship,
because Memories carry no direct domain links.

## Tags

Use Tags for reusable subjects that retrieve records across tables.

Before creating a Tag:

1. Search `Name`.
2. Search `Aliases`.
3. Check the relevant `Namespace`.
4. Reuse the canonical Tag when it represents the subject.

Use singular canonical names. Use `Parent Tag` for hierarchy. Use `Aliases`
for synonyms.

Use `Active`, `Deprecated`, or `Archived` for Tag `Status`.

Do not use Tags for:

- workflow status
- assignment roles
- arbitrary relationships
- external locators
- prose that belongs in a Summary or Note

Use each substantive table's direct `Tags` link for ordinary tagging. Do not
create Bookmarks for ordinary tags.
