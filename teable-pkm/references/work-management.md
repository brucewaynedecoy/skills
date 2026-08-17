# Work Management

Use these rules for Projects, Milestones, Activities, tasks, messages, events,
meetings, reminders, and logs.

## Projects and milestones

Give a Project a measurable `Objective` and, when possible, explicit `Success
Criteria`.

Use these exact Project `Kind` choices:

- `Project`
- `Milestone`

Use these exact Project `Status` choices:

- `Proposed`
- `Planned`
- `Active`
- `Blocked`
- `On Hold`
- `Completed`
- `Cancelled`
- `Archived`

Require `Parent Project` when `Kind = Milestone`.

Use Activities for executable work. Do not place detailed task lists in
`Objective`, `Success Criteria`, or `Summary`.

When completing a Project or Milestone, set `Status = Completed` and set
`Completed At` to the actual completion time.

## Activities

Use these exact Activity `Type` choices:

- `Task`
- `Message`
- `Event`
- `Meeting`
- `Reminder`
- `Log`

Use these exact Activity `Status` choices:

- `Inbox`
- `Planned`
- `Active`
- `Waiting`
- `Blocked`
- `Completed`
- `Cancelled`
- `Archived`

Use these exact Activity `Priority` choices:

- `None`
- `Low`
- `Normal`
- `High`
- `Urgent`

Use party fields by their meaning:

- `For`: the person who benefits from or requested the Activity.
- `Assigned To`: the person responsible for completing it.
- `Actors`: the people who started, wrote, or performed it.
- `Participants or Audience`: the people who participated or received it.

Use `Parent Activity` for task trees and related child Activities. Child
Activities should normally use the same Project as the parent.

When an Activity is complete, set `Completed At`. Record a useful `Outcome`
when the result is not clear from the title or summary.

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
