# System Maintenance

Use these rules after mutations and for authorized schema work.

## Validate before finishing

Inspect the validation view that applies to the changed record:

- Persons: `Agents Missing Agent Record`
- Agents: `Agents Missing Person`
- Projects: `Milestones Missing Parent`
- Activities: `Unassigned Work` and `Completed Missing Date`
- Bookmarks: `Relationships Missing Disposition` and `Relationships Missing Object`
- Memories: `Review Due` and `Expiring Soon`

A validation view can contain unrelated existing records. Report them
separately. Do not modify them unless the user included them in scope.

Read back the first affected record when Teable resolves links, collaborator
identities, choices, or parsed dates. Do not repeatedly read every record that
was written successfully.

## Archive and delete safely

Preserve historical and link value by changing lifecycle state:

- Organizations, Persons, Teams, and similar records: `Inactive` or `Archived`
- Projects and Activities: `Completed`, `Cancelled`, or `Archived`
- Notes: `Superseded` or `Archived`
- Memories: `Superseded`, `Expired`, or `Archived`
- Tags: `Deprecated` or `Archived`
- Bookmarks: `Broken` or `Archived`

Delete only when the user explicitly requests deletion and the exact scope is
confirmed. Before deleting a duplicate, inspect its links. Move required
context to the surviving record.

## Maintain System records

When the user requests a new table or a material table change:

1. Update or create its `System` row.
2. Record the exact table name and table ID.
3. Update its purpose, retrieval guidance, minimum fields, validation rules,
   relationships, and important views.
4. Increment `Schema Version` when the operating contract changes.
5. Set `Last Reviewed At` to the actual review time.
6. Keep the guidance concise enough for an unfamiliar agent to scan.

Do not duplicate the full field schema in `System`. Store operating guidance
and discovery rules there.

## Report completion

After a permitted mutation, report:

- tables affected
- records created or updated
- stable record IDs
- significant links established
- validation issues or unresolved ambiguity
- requested operations that were not performed

Do not claim completion for writes that failed. Do not claim completion for
asynchronous work that was accepted but did not finish.
