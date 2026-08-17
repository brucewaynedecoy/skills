# Table Registry

Use this registry to resolve known table and primary field IDs. Confirm the
live catalog with `teable get-node-tree` when an ID fails or the task concerns
schema maintenance. Treat the live base as authoritative.

| Table | Table ID | Primary field ID | Purpose |
|---|---|---|---|
| Organizations | `tblFog0XHRPweFh4dcj` | `fld6ErHV8hiu25h5mjM` | Companies, clients, communities, churches, agencies, households, and other durable organizations |
| Affiliations | `tbl6vy1qknKh4XZeyMC` | `fldP8Qo921J6STHBgXh` | Person-to-organization roles, departments, relationship types, and dates |
| Persons | `tblfyvECUU5Wo3QVJ9J` | `fldLsjeMgJ9VkIaq7k9` | Contacts, human users, and assignable agent identities |
| Agents | `tbljYF8abSc3WN0g08o` | `fldXnm4RC50hcaI20Ww` | Agent roles, instructions, harnesses, capabilities, and connection history |
| Teams | `tblmW5QNcOSqo24fij3` | `fldMEugQUT5Wj6kDcKR` | Purpose-driven groups within organizations |
| Team Roles | `tbl9u9E16BJAa2Ucqv1` | `fldR3m0V6Ln2b90Q8Fh` | Team duties, functions, roles, and assigned members |
| Projects | `tblpkjjYd2imTGVJspN` | `fldFvV0v7uSSXnTFQb7` | Work with objectives, owners, teams, and milestones |
| Activities | `tblsMY7UWZyRI4oA0FD` | `fldnel1ZTlq9iHgq1M7` | Tasks, messages, events, meetings, reminders, and logs |
| Notes | `tblUMuHBGXe8Hbbqapp` | `fld6xL67NAOFroWiFxj` | Notes, research, transcripts, instructions, and other unstructured knowledge |
| Bookmarks | `tbllkHoWFPATTUh4L9J` | `fldsrUuR0XElG8DTmqJ` | URLs, files, locations, internal locators, and knowledge relationships |
| Memories | `tblQ3cH90sgslLjo4KD` | `fldJ0hck9PZ3jwbHcJS` | Agent preferences, contracts, facts, decisions, and context |
| Tags | `tblh1s1NfEWrrbMiK7z` | `fldGMQ9ODpwJO1S0rbU` | Canonical cross-table subjects and hierarchical classification |
| System | `tblF5VKs7aunLGBZ7tL` | `fldIZOucDjZCTLdsuNA` | Operating guide and schema index |

Use the fixed base ID `bseWajUDRaJlY2pDgJf`.

Read the `System` row for each table involved in a task. It supplies the live
purpose, minimum fields, relationships, retrieval guidance, validation rules,
and important views.
