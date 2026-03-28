# Regenerate User Instructions

## Objective

Regenerate `context/user-instructions.candidate.md` from `context/master-context.md`.

## Inputs

- `context/master-context.md`

## Source Rule

Use only `context/master-context.md` as the source of truth.

## Procedure

1. Read `context/master-context.md`.
2. Extract only current implemented capabilities and current workflow behavior.
3. Translate that information into a user-facing guide.
4. Include inputs, outputs, command usage, flow, and current limitations.
5. Reflect the structured plain-text delimiter architecture accurately.
6. Exclude internal maintenance process details.
7. Exclude roadmap items as available features.
8. Mark the file as a candidate.

## Required Content

- what Cartero currently does
- current commands
- required and optional inputs
- output behavior
- current workflow
- limitations
- constraints on what Cartero will not invent

## Forbidden Content

- roadmap phases presented as shipped functionality
- speculative integrations presented as available
- auto-promotion language

## Output

Return the full contents of `context/user-instructions.candidate.md`.
