---
name: "kindex-ingest"
description: "Extract named entities, decisions, questions, and action items from source material and write them into a Kindex knowledge graph through `kin import`. Use when a request names kindex, kin, or a knowledge graph and supplies meeting notes, a transcript, a document, a backlog, a paste, or a directory to capture; or asks to record people, projects, decisions, open questions, or tasks as graph nodes. Use instead of `kin add` and `kin learn` whenever the material names people or projects, because those commands discard the requested node type. Do not use for reading or querying an existing graph, which `kin search`, `kin context`, and `kin ask` already serve."
---

# Kindex Ingest

Turn unstructured source material into typed Kindex nodes and edges. The agent performs entity extraction; `kin import` performs the write. Never ask `kin` to identify entities on its own.

## Know why this skill exists

`kin` cannot reliably type an entity from prose. Two commands fail in ways that silently corrupt a graph:

- `kin add --type person` creates a **concept**, not a person. Its extraction pass overwrites the requested type. The same holds for every knowledge type.
- `kin add --type project` is rejected outright. `project` is not an accepted value for that flag.
- `kin learn --from-inbox` persists **concepts only**. Decisions, questions, and action items it finds are counted and then discarded.
- `kin ingest files` stores the first **4000 characters** of a file as an untyped `document`. It extracts nothing. Longer transcripts are truncated without warning.

`kin import` is the only path that honors an exact node type. Route all entity work through it.

## Establish the target graph

1. Run `command -v kin`. Stop and report if it is absent; install nothing automatically.
2. Determine the graph. Use `kin profile list` and `kin profile which` to see what is configured.
3. Pass `--profile <name>` on **every** command in the run when a profile is named, or `--data-dir <path>` for an explicit directory. A missing flag writes to the wrong graph and is tedious to undo.
4. Confirm the starting point with `kin status`. Retain the node count to verify the write later.

Treat the profile or data directory as a required parameter of the whole task, not a per-command afterthought.

## Read the source before extracting

Read the full source. Do not extract from a summary of it.

For material longer than roughly 8000 words, split it into topic-coherent sections and extract per section. Emit one JSON file per section and import each in order. Do not split mid-discussion; a decision separated from its rationale produces a decision node with no `content`.

Read [references/entity-extraction.md](references/entity-extraction.md) before the first extraction of a session and before any transcript, which carries different signals than written notes.

## Resolve against the existing graph first

Duplicate nodes are the primary failure of this skill. `kin import` matches an incoming item by `id` first, then by exact `title`. A match **merges** — and a merge never changes the existing node's type. A person already stored as a `concept` stays a `concept` forever.

Before building the JSON:

1. List what exists: `kin list --limit 500 --json`.
2. Search each candidate entity by name: `kin search "<name>" --json`.
3. For each candidate, decide one of three outcomes:
   - **New** — no match. Create it with a fresh stable ID.
   - **Same** — a match with the correct type. Reuse the existing node's real ID; add content only if it carries new information.
   - **Mistyped** — a match with the wrong type. Do **not** import over it. Report it to the user and offer `kin supersede`, which replaces a node and preserves history.

Never guess that a similar title is the same entity. "Atlas" and "Atlas Migration" may be a project and its codename, or two unrelated things. Ask when the source does not settle it.

## Assign stable IDs

A stable ID makes the whole operation idempotent. Re-running the same source must update, never duplicate.

Use `<prefix>-<slug>` in lowercase with hyphens:

| Kind | Prefix | Example |
| --- | --- | --- |
| Person | `person-` | `person-jane-doe` |
| Project | `proj-` | `proj-atlas-migration` |
| Source document | `doc-` | `doc-2026-08-14-atlas-standup` |
| Decision | `dec-` | `dec-postgres-for-atlas` |
| Question | `q-` | `q-reporting-read-replica` |
| Concept | `con-` | `con-backfill-window` |
| Task | `task-` | `task-benchmark-ingest` |

Derive a person slug from the name, never from a role. Derive a document slug from the source date and subject so a re-read of the same file lands on the same node.

## Anchor every run to a source document

Create exactly one `document` node per source and link every extracted node back to it with a `context_of` edge. This is what keeps extracted nodes out of the orphan pile, and it records where each claim came from.

Put the source document **first** in the array so later nodes can point at it.

## Build the import file

Write JSON to a scratch path such as `/tmp/kindex-ingest-<slug>.json`. Read [references/import-schema.md](references/import-schema.md) for the exact field contract and the accepted type vocabularies.

Two ordering rules govern edges:

- An edge target must already exist in the store when its edge is processed. A forward reference to a node defined later in the same array is **dropped silently** — the import reports success with a lower edge count and no error.
- Order the array targets-first: source document, then people and projects, then decisions, questions, concepts, and tasks that reference them.

Always run the import **twice** regardless of ordering. The second pass creates nothing and repairs any edge whose target did not yet exist on the first pass. It is idempotent and safe.

## Import and verify

```bash
kin import /tmp/kindex-ingest-<slug>.json --profile <name> --dry-run
kin import /tmp/kindex-ingest-<slug>.json --profile <name>
kin import /tmp/kindex-ingest-<slug>.json --profile <name>   # second pass repairs edges
```

Read the summary line: `N created, N updated, N edges, N skipped`.

- `skipped` above zero on a first pass means items lacked both `title` and `id`. Fix the file.
- `edges` lower than the number written means targets were missing. The second pass should close the gap. If it does not, a target title or ID is wrong.
- `created` above zero on a second pass means IDs are unstable. Stop and fix the ID scheme before continuing.

Verify the result, then report node IDs to the user:

```bash
kin status --profile <name>
kin show <id> --profile <name>
kin graph --profile <name>
```

Rising orphan counts in `kin status` mean the `context_of` anchors did not land.

## Route tasks and reminders correctly

`kin import` can create a `task` node, and it will appear in `kin task list`. It cannot set priority, due date, effort, or status — those fields are not in the import contract, and every imported task defaults to priority 3.

Choose by whether the action item carries scheduling detail:

- **Bare action item, no date** — import it as `type: "task"` with a `context_of` edge to its project. One file, one write.
- **Owner, due date, or priority present** — create it after the import so it can link to nodes that now exist:

```bash
kin task add "Benchmark the ingest pipeline" --priority 2 --due friday \
  --link proj-atlas-migration --profile <name>
```

- **Time-based trigger, not a work item** — use `kin remind create "..." --at "every friday at 9am"`. A reminder is not a graph node and does not belong in the import file.

Pass `--link` an existing node ID. Passing prose that does not match a node title creates an unlinked orphan task without warning.

## Report the outcome

State plainly what entered the graph: counts by type, the IDs of new people and projects, any entity that was skipped as an existing match, and any mistyped node that needs `kin supersede`. Name the profile that was written to. Do not claim a link was made without a `kin show` that displays it.
