# Entity extraction for Kindex

How to decide what becomes a node, which type it gets, and what its content says. Read before the first extraction of a session, and before any transcript.

## The admission test

A graph loses value faster from junk nodes than from missing ones. Admit an entity only when both hold:

1. **It is durable.** It will still mean something in six months.
2. **It is referenceable.** Some future note will point at it.

Reject a candidate that fails either test. A person mentioned once in passing, a number quoted from a dashboard, or a phrase that only makes sense inside one paragraph belongs in the source document's `content`, not in its own node.

Every node needs `content`. A node whose title is its only information cannot be retrieved usefully and inflates the orphan count. If there is nothing to write in `content`, there is no node.

## Type by type

### `person`

A named human with an ongoing relationship to the work.

- **Content:** role, what they own, how they prefer to be reached, standing context. Not what they said in one meeting.
- **Admit:** an owner, a decision-maker, a recurring collaborator, a stakeholder.
- **Reject:** a name appearing once with no role; an author cited in passing; a group ("the platform team") — that is a `project` or a `concept`.
- **Edges:** `context_of` to the source. `depends_on` from a project that needs them.

Never fold two people into one node because they share a first name. Never create a person node from an email address alone.

### `project`

A named body of work with an outcome and an end.

- **Content:** the goal, the current state, the target date if stated.
- **Admit:** anything with a name that people refer to as a thing ("the Atlas migration", "Q4 pricing review").
- **Reject:** a standing function ("support", "on-call"). That is a `concept`.
- **Edges:** `depends_on` to people. `context_of` to the source.

### `decision`

A settled choice plus the reason for it.

- **Content:** the rationale. A decision without a stated reason is worth little later; if the source gives none, record that explicitly rather than inventing one.
- **Admit:** "we decided", "we went with", "we're using X instead of Y".
- **Reject:** a preference expressed without commitment; an option still under discussion — that is a `question`.
- **Edges:** `context_of` to the project it governs. `answers` to a question it settles. `supersedes` to a decision it replaces.

Title the decision by what was chosen, not by the meeting it happened in.

### `question`

A genuinely open loop that someone must close.

- **Content:** what prompted it, what would settle it, who raised it.
- **Admit:** "we still don't know", "open question", an unresolved risk.
- **Reject:** a rhetorical question; a question the same source answers.
- **Edges:** `relates_to` the project. When it is later resolved, add an `answers` edge from the new decision.

### `task`

An action someone must take.

- **Content:** what "done" looks like, and any constraint on how.
- **Admit:** "X will do Y", "action item", "follow up on".
- **Reject:** an intention with no actor and no outcome ("we should think about caching") — that is a `question`.
- **Routing:** import it as a node when it has no date. Create it with `kin task add --priority --due --link` when it does, because the import contract carries no scheduling fields.

### `concept`

A durable idea, term of art, pattern, or piece of project jargon.

- **Content:** a plain definition, then why it matters here.
- **Admit:** vocabulary a newcomer would have to ask about; a recurring pattern; a named constraint of the domain.
- **Reject:** a common English phrase; a capitalized product name that is really a `project`.
- **Edges:** `relates_to` the concepts it touches. `context_of` to the source.

### `document`

The source itself. Exactly one per ingest run.

- **Content:** what the source is, when, who was present, and a short summary. For a truncated or chunked source, say so.
- **Title:** subject plus date, so it sorts and matches predictably.
- **Edges:** none outgoing. Everything else points at it with `context_of`.

## Written notes versus transcripts

Written notes are already curated. Extract close to the text.

Transcripts are not. Apply extra rules:

- **Discount hedging.** "Maybe we use Postgres" is not a decision. Look for the later line where it settles, and title the decision from that line.
- **Attribute action items.** A transcript names the owner in speech ("Raj, can you benchmark that?" / "Yeah, by Friday"). Capture both the owner and the date; they are usually in different turns.
- **Ignore procedural talk.** Scheduling, greetings, audio problems, and small talk produce nothing.
- **Collapse repetition.** A point restated four times is one node.
- **Resolve pronouns before extracting.** "He owns that" is useless as content. Write the resolved name, and if the referent is genuinely ambiguous, leave it out and say so in the report.
- **Never invent a rationale.** If speakers agreed without saying why, the decision's content records the agreement and notes that no reason was stated.

For a long transcript, chunk by topic shift, not by length. Keep a decision and its rationale in one chunk.

## Naming

Titles are retrieval keys, not headlines.

- Use the plainest phrase a person would search for.
- Use the full form on first creation: "Atlas Migration", not "Atlas". Record the short form with `kin alias` if the source uses both.
- Do not put dates in a title unless the node is a dated source document.
- Do not put the source name in an extracted node's title. The `context_of` edge already records it.

## Domains

Set `domains` on every node — it is the tag field, and it is how a mixed personal-and-work graph stays navigable.

Use two to four lowercase tags. Combine one broad tag and one specific tag:

- A work project: `["work", "atlas"]`
- A person: `["people", "atlas"]`
- A personal idea: `["personal", "writing"]`
- A meeting source: `["meeting", "atlas"]`

Keep the vocabulary stable across runs. Check what already exists with `kin list --limit 500 --json` before inventing a tag.

## Audience

Default is `private`. Raise it deliberately:

- `private` — personal notes, people, anything about individuals.
- `team` / `org` — shared project knowledge.
- `public` — safe to publish.

`kin export --audience public` emits only public nodes. Anything not explicitly raised stays out of an export, which is the safe failure direction. When in doubt, leave it `private`.
