# Kindex import schema

The exact contract accepted by `kin import <file>`. Fields not listed here are ignored silently.

## File format

A JSON array of node objects, or JSONL with one node object per line. `kin import` auto-detects from the file extension; override with `--format json|jsonl`.

```json
[
  {
    "id": "doc-2026-08-14-atlas-standup",
    "title": "Atlas standup, 2026-08-14",
    "type": "document",
    "content": "Attendees: Jane Doe, Raj Patel. Reviewed migration cutover risk.",
    "domains": ["meeting", "atlas"],
    "audience": "private",
    "weight": 0.5
  },
  {
    "id": "person-jane-doe",
    "title": "Jane Doe",
    "type": "person",
    "content": "Engineering lead on the Atlas migration. Prefers async written updates.",
    "domains": ["people", "atlas"],
    "edges": [
      { "to": "doc-2026-08-14-atlas-standup", "type": "context_of", "weight": 0.4 }
    ]
  }
]
```

## Node fields

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | string | generated | Any stable string. Supply it; omitting it makes re-runs create duplicates. |
| `title` | string | — | Required unless `id` is present. Used as the fallback match key. |
| `type` | string | `concept` | Must be one of the node types below. Honored exactly on create. |
| `content` | string | `""` | The body. Searched by FTS5. |
| `domains` | string[] | `[]` | Stored as the node's tags. `kin list --tags` and `kin search --tags` filter on these. |
| `audience` | string | `private` | One of `private`, `team`, `org`, `public`. Governs `kin export --audience`. |
| `weight` | number | `0.5` | Starting salience. Decays over time unless the node is accessed. |
| `edges` | object[] | `[]` | Outgoing edges. See below. |

There is no `tags` field. Use `domains`; it populates the same store column that `kin show` prints as **Tags**.

There is no field for task priority, due date, effort, or status. Use `kin task add` for those.

## Edge objects

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `to` | string | — | Required. Target node ID, or its exact title. |
| `type` | string | `relates_to` | Must be one of the edge types below. |
| `weight` | number | `0.5` | Edge strength. |

Edges are declared on the source node only and point outward. `kin show` displays both directions.

## Node types

Knowledge types:

`concept` `document` `session` `person` `project` `decision` `question` `artifact` `skill` `task`

Operational types:

`constraint` `directive` `checkpoint` `watch`

Operational types carry extra behavior that `kin import` cannot set (trigger, action, owner, expiry, reset schedule). Create those with `kin add --type <op-type>` instead, which honors the flag for these four types specifically.

## Edge types

`relates_to` `answers` `contradicts` `implements` `depends_on` `spawned_from` `supersedes` `exemplifies` `context_of` `blocks`

Common choices:

| Situation | Edge |
| --- | --- |
| Node came from this source | `context_of` → the document |
| Decision governs a project | `context_of` → the project |
| Question is about a project | `relates_to` → the project |
| Question is settled by a decision | `answers`, from the decision to the question |
| Project needs a person | `depends_on` → the person |
| Task is blocked | `blocks`, from the blocker to the task |
| A newer decision replaces an older one | `supersedes` → the old decision |

## Merge behavior

For each item, `kin import` resolves an existing node by `id`, then by exact `title`.

**No match** — creates the node with every field as supplied. This is the only path where `type` takes effect.

**Match, `--mode merge` (default)** — appends new `content` to old content, separated by a blank line. Identical content is skipped. `type`, `domains`, `audience`, and `weight` are **not** updated. A node stored with the wrong type keeps that type permanently.

**Match, `--mode replace`** — overwrites `title`, `content`, and `weight`. `type` is still not changed.

To correct a mistyped node, use `kin supersede <id> "<new text>" --reason "..."`, which replaces it and preserves history. Do not attempt it through import.

Edges are processed on every pass, whether the node was created, updated, or skipped.

## Ordering and the second pass

An edge is written only if its target already exists in the store at the moment the edge is processed. A reference to a node defined further down the same array is dropped with no error; the summary simply reports a lower edge count.

Two mitigations, use both:

1. Order the array targets-first — source document, then people and projects, then decisions, questions, concepts, and tasks.
2. Run `kin import` a second time on the same file. The second pass creates nothing, updates nothing, and writes any edge whose target now exists.

The second pass is idempotent. A third pass changes nothing further.

## Dry run

`--dry-run` prints the create/update decisions without writing. It does **not** report edge outcomes, because edge resolution depends on nodes the dry run did not create. Use it to check for unintended merges, not to check edges.

## Verifying a write

```bash
kin status --profile <name>          # node and edge totals, orphan count, counts by type
kin show <id> --profile <name>       # one node with its incoming and outgoing edges
kin list --type person --profile <name>
kin list --tags atlas --profile <name>
kin graph --profile <name>           # density, components, hub node
```

A healthy ingest run raises the edge count by at least the node count, and leaves the orphan count unchanged.
