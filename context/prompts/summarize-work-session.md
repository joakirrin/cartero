# Summarize Work Session

## Objective

Summarize a completed work session into a structured record that can be compared against `context/master-context.md`.

## Inputs

- `context/master-context.md`
- work session notes or transcript
- diff or change summary for the session

## Source Rule

Use `context/master-context.md` as the source of truth for current Cartero state.
Use the work session material only to describe what happened in the session.
Do not infer project state changes unless they are explicit in the work session material.

## Procedure

1. Read `context/master-context.md`.
2. Read the provided work session material.
3. Extract only explicit session outcomes.
4. Separate implemented work from proposed or pending work.
5. Compare session outcomes against the current master context.
6. Identify whether the session suggests:
   - capability changes
   - priority shifts
   - resolved issues
   - new issues
   - architecture changes
7. If a point is not explicit, omit it.

## Output

Produce a structured summary with these sections:

```md
# Work Session Summary

## Implemented Changes

## Proposed But Not Implemented

## Priority Impact

## Architecture Impact

## Constraints Or Issues

## Recommended Master Context Changes
```

## Rules

- Do not update the master context in this step
- Do not invent features
- Do not compress roadmap information
- Do not present roadmap items as completed work
- Keep language operational and precise
