# Transcript Capture

Use these rules when capturing a meeting recording, transcript, call, or other
time-based spoken source into the base. They apply to any transcript source.

A transcript is not one record. One meeting normally produces records in
Organizations, Persons, Affiliations, Projects, Activities, Notes, Bookmarks,
and Tags. Capturing only the transcript text loses most of the value.

## Contents

- [Check for a prior capture](#check-for-a-prior-capture)
- [Verify the source is complete](#verify-the-source-is-complete)
- [Extract in dependency order](#extract-in-dependency-order)
- [Make the meeting Activity the spine](#make-the-meeting-activity-the-spine)
- [Resolve speakers to persons](#resolve-speakers-to-persons)
- [Set the meeting clock](#set-the-meeting-clock)
- [Derive action items from the transcript](#derive-action-items-from-the-transcript)
- [Split verbatim from interpretation](#split-verbatim-from-interpretation)
- [Capture a meeting series](#capture-a-meeting-series)
- [Decide what not to extract](#decide-what-not-to-extract)
- [Record what you inferred](#record-what-you-inferred)

## Check for a prior capture

Do this before writing anything. A second capture of the same source
duplicates every record it produced, across every table.

The dedupe key is the source's own stable identifier. Store it in the meeting
Activity's `External ID`, and store the source path or URL in the transcript
Note's `Source Locator`.

Search both before extracting:

```bash
teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblsMY7UWZyRI4oA0FD" \
  --search '{"value":"<source id>","fieldId":"fldgsiYe1zjIBNtwxNh"}' \
  --take 20

teable record get \
  --base-id "$BASE_ID" \
  --table-id "tblUMuHBGXe8Hbbqapp" \
  --search '{"value":"<source path>","fieldId":"fldwhHzwhZ8yrGNUtpk"}' \
  --take 20
```

If either returns a record, the source is already captured. Update the
existing records instead of creating new ones, and say so in the report. Do
not create a parallel set.

Always write `External ID` on the meeting Activity, even when the source has
no obvious identifier. Use the most stable value available, such as a file
identifier or a normalized filename. Without it the next agent cannot dedupe.

## Verify the source is complete

Paginated exports and streamed captures often hold only the first page.

Before extracting, compare the declared total against the returned count. If
they differ, page the remainder from the source and merge before extracting.

The end of a meeting is where decisions, commitments, and next steps usually
land. A truncated transcript loses exactly the part that matters most.

If you cannot complete the source, state which part is missing in the
transcript Note `Summary`, and do not report a full extraction.

## Extract in dependency order

Links resolve upward. Write each record only after the records it links to
exist. The transcript Note is the last knowledge record, not the first.

| Order | Records | Why here |
|---|---|---|
| 1 | Tags | Everything below links to them |
| 2 | Organizations | Persons and Projects need them |
| 3 | Persons | Parties, authors, and owners |
| 4 | Affiliations | Needs both Person and Organization |
| 5 | Teams, then Team Roles | Team Roles need Teams and Persons |
| 6 | Projects, then Milestones | Milestones need a Parent Project |
| 7 | The meeting Activity | The spine for everything after |
| 8 | Child Activities | Need the parent meeting |
| 9 | Notes: transcript, then meeting notes | Link to all of the above |
| 10 | Bookmarks | Locators and relationships last |

Do not create a Note before the records it links to exist. Backfilling links
afterwards is where orphaned notes come from.

## Make the meeting Activity the spine

Every other record from the transcript attaches to it.

Set at least:

- `Type = Meeting` and a `Subtype` naming the meeting kind
- `Status = Completed` for a meeting that already happened
- `Start At`, `End At`, and `Completed At`
- `External ID` for the source identifier
- `Channel or Source` for the platform and the capture tool
- `Organization`, `Team`, and `Project` context
- `Summary`, `Details`, and `Outcome`

Use party fields by meaning:

- `Actors`: who convened or ran the meeting.
- `Participants or Audience`: everyone who attended.

Attach every action item as a child Activity through `Parent Activity`. Attach
both Notes through the Activity's `Notes` link.

## Resolve speakers to persons

Speaker labels from a transcription tool are not identities.

1. Map each label to a Person from context before writing any record.
2. Record the mapping explicitly in the transcript Note body.
3. Leave a label you cannot resolve exactly as recorded. Do not invent a
   Person for an unidentified voice.

Decide who becomes a Persons record:

- Create a record when the individual has a role in the work: an attendee, an
  owner, a decision maker, a named stakeholder.
- Keep a name that is merely mentioned in passing, or that belongs only to
  historical context, in the Note body instead.

For a partial name, create the record under the name exactly as given. State
in `Summary` that the surname is not in the source, and that any spelling
taken from a machine transcript is unverified.

## Set the meeting clock

Do not assume the source's timestamps are local time or UTC.

Confirm the zone from evidence inside the transcript, such as a stated clock
time, a stated day of the week, or a greeting that implies a time of day.
Cross-check that evidence against the declared start time and duration.

Write `Start At`, `End At`, and `Completed At` in ISO 8601 with an explicit
offset. If you cannot confirm the zone, record the date, leave the times
empty, and say why in the Note `Summary`. A wrong offset silently corrupts
every timeline view in the base.

## Derive action items from the transcript

Read the whole transcript for commitments. Treat any summary that shipped with
the source as a checklist to test your extraction against, never as the source
itself. Generated summaries routinely miss commitments, especially those made
late in a meeting or framed as an aside.

A statement is an action item when someone accepts responsibility for doing
something, even when nobody calls it a task.

For each one, capture:

- what it is, as a plain imperative title
- `Assigned To`: who is responsible
- `For`: who requested it or benefits from it
- `Status = Waiting` when it is blocked, and name the blocker in `Details`
- `Details`: any answer already given in the meeting, and any qualifier

Do not invent a `Due At` from a vague phrase such as "soon" or "as soon as
possible". Leave the field empty and quote the phrase in `Details`.

Include items a participant flagged as their own side's internal problem. They
are still commitments, and they still belong on the timeline.

## Split verbatim from interpretation

Create two Notes. Never merge them.

| Note | `Type` | Body |
|---|---|---|
| Transcript | `Transcript` | Verbatim and uncorrected |
| Meeting notes | `Meeting Notes` | Summary, decisions, and your additions |

Rules for the transcript Note:

- Do not correct the body. Machine transcripts mishear names, acronyms, and
  jargon, and the raw text is the evidence.
- State in the body that the text is uncorrected and that wording is
  approximate.
- List unresolved terms explicitly rather than guessing at them.

Rules for the meeting notes Note:

- Keep any summary that shipped with the source clearly attributed and intact.
- Put everything that summary missed in a clearly marked reviewer section.
- Put interpretation, correction, and context here, never in the transcript.

Set `Confidentiality` from the meeting's audience rather than leaving it
empty. A meeting involving an external party or client is at least
`Restricted`.

## Capture a meeting series

A transcript that refers to an earlier or later meeting belongs to a series.

- Search for the existing Project, Organizations, Persons, and Tags, and reuse
  them. Never recreate a record that already exists under another transcript.
- Point every meeting in the series at the same Project.
- Add only what this transcript contributes to an existing `Summary`. Do not
  overwrite context captured from an earlier meeting.
- When the transcript names a prior meeting, link the two meeting Activities
  through a Bookmark relationship if no direct link fits.

## Decide what not to extract

Do not create records for:

- greetings, small talk, or technical difficulties
- an aside with no owner and no consequence
- a restatement of something already recorded elsewhere
- a person mentioned once with no role in the work

This material stays in the verbatim transcript, which is where it belongs.

## Record what you inferred

Speech is imprecise. Records are precise. Do not convert one into the other
silently.

- Do not derive an exact value from an approximate statement. A claim such as
  "twenty-six years at the company" belongs in a `Notes` field as a sentence,
  not in a `Start Date`.
- Put every inference in the record itself, not only in chat: unresolved
  names, an assumed time zone, an unverified spelling, a chosen canonical name
  that differs from the spoken one.
- State what you deliberately did not create, and why.

Then capture what the session taught you as a `Memory` under your resolved
agent identity. See
[knowledge-management.md](knowledge-management.md) and
[identity-and-groups.md](identity-and-groups.md).
