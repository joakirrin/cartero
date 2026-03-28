# Regenerate Project Instructions

## Objective

Regenerate `context/llm-project-instructions.md` from `context/master-context.md`.

## Inputs

- `context/master-context.md`

## Source Rule

Use only `context/master-context.md` as the source of truth.

## Procedure

1. Read `context/master-context.md`.
2. Extract:
   - product identity
   - source model
   - hard rules
   - current implemented capabilities
   - current priorities
   - system behavior
   - architecture constraints
   - known issues and constraints
3. Convert those points into operational instructions for an LLM.
4. Keep implemented capabilities separate from roadmap work.
5. Preserve priorities exactly.

## Required Content

- what Cartero is
- diff versus context model
- hard rules
- current implemented capabilities
- current priorities
- behavior expectations
- structured plain-text delimiter architecture
- constraints
- parity requirements across CLI, web, and LLM-native environments

## Forbidden Content

- roadmap items described as available functionality
- speculative features described as implemented
- features not present in the master context

## Output

Return the full contents of `context/llm-project-instructions.md`.
