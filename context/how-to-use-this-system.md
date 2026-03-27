# How To Use The Cartero Context System

## Purpose

This system keeps Cartero context files aligned with `context/master-context.md`.

## Source Of Truth

`context/master-context.md` is the only source of truth for derived context files.

## Order Of Operations

1. Update `context/master-context.md` first when validated project state changes.
2. Regenerate derived files from the master context.
3. Validate the refreshed files against the master context.
4. Review validation results.
5. Approve or reject the refresh.

## Required Inputs

- `context/master-context.md`
- validated implementation evidence when the master context changes
- the derived context files being refreshed

## Derived Files

- `context/llm-project-instructions.md`
- `context/llm-update-instructions.md`
- `context/user-instructions.candidate.md`
- `context/user-instructions.md`
- `context/validation-checklist.md`
- `context/update-history.md`
- files under `context/prompts/`

## Rules For Use

- treat `context/master-context.md` as the source of truth
- do not refresh derived files before the master context is current
- do not invent capabilities
- do not present roadmap work as implemented
- preserve current priorities exactly
- preserve Cartero product identity
- preserve the structured plain-text delimiter architecture
- preserve parity requirements across CLI, web, and LLM-native environments

## Validation Step

Validation must confirm:
- source integrity
- capability accuracy
- architecture accuracy
- roadmap preservation
- priority accuracy
- workflow rule compliance
- parity rule compliance

Validation must happen before approval.

## Approval Boundaries

- updates to the master context require review
- `context/user-instructions.candidate.md` remains the candidate file until explicitly approved
- `context/user-instructions.md` remains the approved or live placeholder unless explicitly justified by the master context
- failed validation blocks approval

## Practical Workflow

1. Read `context/master-context.md`.
2. If needed, refresh the master context from validated evidence.
3. Regenerate all derived files.
4. Run the validation prompt or checklist.
5. Fix any warnings or failures.
6. Request approval.
7. Log the refresh in `context/update-history.md`.

## Maintenance Rule

If significant work has been completed and the master context has not been updated, update it before continuing.
