# Validate Context Refresh

## Objective

Validate that all derived context files remain consistent with `context/master-context.md`.

## Inputs

- `context/master-context.md`
- `context/how-to-use-this-system.md`
- `context/llm-update-instructions.md`
- `context/llm-project-instructions.md`
- `context/user-instructions.candidate.md`
- `context/user-instructions.md`
- `context/validation-checklist.md`
- `context/update-history.md`
- any prompt files under `context/prompts/`

## Source Rule

`context/master-context.md` is the reference for validation.

## Procedure

1. Read `context/master-context.md`.
2. Read each derived file.
3. Compare each file against the master context.
4. Verify that implemented capabilities are described only where implemented.
5. Verify that roadmap content is preserved and not collapsed.
6. Verify that priorities match exactly.
7. Verify that the diff-versus-context model remains intact.
8. Verify that the structured plain-text delimiter architecture remains intact, including in-memory regex parsing and system-controlled final formatting.
9. Verify that parity requirements for CLI, web, and LLM-native environments are preserved.
10. Verify that user instructions remain candidate-plus-placeholder and are not auto-promoted.
11. Verify that no file describes JSON output or JSON-to-YAML conversion as the current generation architecture unless the master context still says so.
12. Record any mismatch.

## Output Format

```md
# Context Refresh Validation

Status: PASS | PASS WITH WARNINGS | FAIL

## Confirmed

## Warnings

## Failures

## Required Fixes Before Approval
```

## Failure Conditions

- invented functionality
- roadmap treated as implemented
- missing or changed priorities
- missing parity requirement
- inaccurate architecture description
- user instructions promoted automatically
- contradictions between derived files and master context

## Rule

Validation must happen before approval.
