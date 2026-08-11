<!-- make-docs:begin -->
# Agent Instructions

- When asked to create documentation for this project that is not `README.md`, read the same-named instruction file in `docs/` before writing.
- For documentation lifecycle order or skip/reorder/revisit decisions, read `.make-docs/references/system/lifecycle.md` and surface departures from the default arc.
- Before staging or committing changes, read and follow `.make-docs/contracts/system/commit-message-convention.md`.
<!-- make-docs:end -->

This repository contains a collection of custom agent skills, and so any documentation created for this project (i.e., under `docs/`) should be **skill-specific** and not generic.  This important differentiating boundary should also be considered when applying or interpreting Make Docs contracts; for example, a new design for a skill "foo" should incorporate the skill's specific name in the file name, and should contain identifying details that will map the design to that skill's directory/implementation.

Since Make Docs explicitly states that PRD sets are authoritative and non-versionable, agents MUST interpret each document in the set (other than the fixed documents) as a PRD for a single skill (i.e., each document pertains to a single skill).
