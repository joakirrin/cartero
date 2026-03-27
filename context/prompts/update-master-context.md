# Update Master Context

## Objective

Refresh `context/master-context.md` from validated evidence while preserving Cartero structure, priorities, tone, and product identity.

## Inputs

- current `context/master-context.md`
- validated work session summary
- validated implementation evidence

## Source Rule

`context/master-context.md` is the baseline source of truth.
Only apply changes supported by the validated inputs.

## Procedure

1. Read the current `context/master-context.md`.
2. Read the validated work session summary.
3. Read the validated implementation evidence.
4. Determine which sections require changes.
5. Update only the sections supported by evidence.
6. Preserve unchanged sections.
7. Preserve current priorities unless validated evidence requires a change.
8. Preserve the full roadmap.
9. Preserve the diff-versus-context model.
10. Preserve the structured plain-text delimiter architecture.
11. Preserve parity requirements for CLI, web, and LLM-native environments.

## Required Preservation

- Cartero is a communication system
- diff explains what changed
- context explains why it matters
- context improves quality but never overrides diff
- LLM returns structured plain-text with custom markers
- the system parses fields in-memory using regex
- the system controls final output formatting
- CLI parity with web is mandatory
- Cartero remains usable in CLI and LLM-native environments

## Forbidden Actions

- Do not add unsupported features
- Do not remove roadmap phases
- Do not rewrite entire sections unnecessarily
- Do not mark speculative work as implemented
- Do not change priorities without validated evidence

## Output

Return the full refreshed contents of `context/master-context.md`.
